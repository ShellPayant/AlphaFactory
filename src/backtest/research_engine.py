"""Research backtester — single-position, bar-by-bar, no-lookahead.

Design constraints (deliberately strict):

1. **One open position at a time.** The whole point of v0.1 is to validate
   strategy logic, not portfolio construction. The risk policy also caps
   concurrent positions at 1 in Phase 1.

2. **Next-bar execution.** A signal generated at bar T is filled at the
   *open* of bar T+1. This is the only way to be honest about lookahead.

3. **Three exit triggers, evaluated bar-by-bar inside the position:**
       - Stop hit (intrabar: low ≤ stop for longs / high ≥ stop for shorts).
       - Target hit (intrabar: high ≥ target for longs / low ≤ target for shorts).
       - Time-based force-close at a configurable cutoff (default 15:30 ET).
   If both stop and target are touched in the same bar, we assume the *stop*
   fires first — the pessimistic assumption is the correct one for honest
   backtests, since intrabar order is unknowable from OHLC data.

4. **Position sizing is risk-based.** ``equity * risk_per_trade / risk_per_share``.
   The strategy doesn't size; the backtester does.

5. **Equity curve marks-to-market on close of every bar** while a position is
   open. This drives drawdown and time-under-water metrics.

This engine is fast (vectorized signal generation, then a small Python loop
for position management) and produces a trade log + equity curve that the
report module turns into a Markdown summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

import polars as pl

from src.strategies.base import Signal, Strategy

from .fees import ALPACA_PAPER, FeeModel

NY_TZ = ZoneInfo("America/New_York")
DEFAULT_FORCE_CLOSE_LOCAL = time(15, 30)


@dataclass(slots=True)
class Trade:
    """A round-trip trade — entry to exit."""

    symbol: str
    side: Literal["long", "short"]
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    pnl_pct: float
    bars_held: int
    exit_reason: Literal["target", "stop", "force_close", "invalidation"]
    regime_tag: str
    categorical_state: str
    fees_paid: float
    risk_per_share: float


@dataclass
class BacktestResult:
    """Full result of a single backtest run."""

    strategy_name: str
    symbol: str
    starting_equity: float
    ending_equity: float
    trades: list[Trade]
    equity_curve: pl.DataFrame   # cols: ts, equity, open_position (bool)
    signals_generated: int
    signals_skipped_by_sizing: int = 0
    signals_skipped_by_max_notional: int = 0  # blocked because share count would breach max_notional_pct
    signals_skipped_by_min_stop: int = 0      # blocked because stop distance is below min_stop_pct
    fee_model: FeeModel = field(default_factory=lambda: ALPACA_PAPER)
    config_used: dict = field(default_factory=dict)

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def total_return_pct(self) -> float:
        return (self.ending_equity / self.starting_equity - 1.0) * 100.0


def _to_local_time(ts: datetime, tz: ZoneInfo = NY_TZ) -> time:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ZoneInfo("UTC"))
    return ts.astimezone(tz).time()


def run_backtest(
    bars: pl.DataFrame,
    strategy: Strategy,
    *,
    starting_equity: float = 100_000.0,
    risk_per_trade: float = 0.0025,
    max_notional_pct: float = 1.0,
    min_stop_pct: float = 0.0005,
    fee_model: FeeModel = ALPACA_PAPER,
    force_close_local: time = DEFAULT_FORCE_CLOSE_LOCAL,
    tz: ZoneInfo = NY_TZ,
) -> BacktestResult:
    """Run one strategy on one symbol over one bars frame.

    The bars frame must already have indicator + regime columns appended
    (see ``src/features`` and ``src/regimes``). The strategy's
    ``generate_signals`` is invoked once on the full frame; the engine
    then walks bars in order, opening positions on the bar *after* each
    signal and closing them when stop/target/force-close fires.

    Risk guardrails (in addition to ``risk_per_trade``):

    * ``max_notional_pct`` — cap on position notional as a fraction of
      current equity. Default 1.0 = no leverage. Signals whose share count
      would breach the cap are skipped (counted in
      ``signals_skipped_by_max_notional``) rather than clamped, because
      clamping would silently break the ``risk_per_trade`` promise.

    * ``min_stop_pct`` — minimum stop distance as a fraction of the entry
      fill price. Default 0.0005 (5 bps). Below this, the stop is tighter
      than typical 5-min-bar noise and the trade will often exit on the
      entry bar — symptomatic of a broken signal. Such signals are skipped
      (counted in ``signals_skipped_by_min_stop``).
    """
    if max_notional_pct <= 0:
        raise ValueError("max_notional_pct must be > 0")
    if min_stop_pct < 0:
        raise ValueError("min_stop_pct must be >= 0")
    if bars.is_empty():
        return BacktestResult(
            strategy_name=strategy.name,
            symbol="UNKNOWN",
            starting_equity=starting_equity,
            ending_equity=starting_equity,
            trades=[],
            equity_curve=pl.DataFrame(
                {"ts": [], "equity": [], "open_position": []}
            ),
            signals_generated=0,
        )

    symbol = bars["symbol"][0] if "symbol" in bars.columns else "UNKNOWN"

    # Generate all candidate signals up front.
    all_signals = strategy.generate_signals(bars)
    signals_by_ts: dict[datetime, Signal] = {s.ts: s for s in all_signals}

    # Pre-extract bar rows as plain dicts → faster than iter_rows in a hot loop.
    rows = bars.to_dicts()
    n = len(rows)

    equity = starting_equity
    equity_pts: list[tuple[datetime, float, bool]] = []
    trades: list[Trade] = []
    skipped_sizing = 0
    skipped_max_notional = 0
    skipped_min_stop = 0

    # Position state ----------------------------------------------------
    open_pos: dict | None = None  # holds dict with side, shares, entry_price, stop, target, sig, entry_idx

    for i in range(n):
        bar = rows[i]
        bar_ts: datetime = bar["ts"]

        # --- 1. If a position is open, check exits on THIS bar ---
        if open_pos is not None:
            # Expose bars_held so strategies' trailing-stop and invalidation
            # hooks can implement time-based logic without needing the loop index.
            open_pos["bars_held"] = i - open_pos["entry_idx"]
            # --- 1a. Strategy's trailing-stop callback, with 'tighten-only' guard. ---
            proposed_stop = strategy.update_trailing_stop(bar, open_pos)
            if proposed_stop is not None:
                if open_pos["side"] == "long":
                    # Long: tightening = raising the stop. Reject any lowering.
                    if proposed_stop > open_pos["stop"]:
                        open_pos["stop"] = float(proposed_stop)
                else:  # short
                    # Short: tightening = lowering the stop. Reject any raising.
                    if proposed_stop < open_pos["stop"]:
                        open_pos["stop"] = float(proposed_stop)

            side = open_pos["side"]
            stop = open_pos["stop"]
            target = open_pos["target"]
            shares = open_pos["shares"]

            high = float(bar["high"])
            low = float(bar["low"])
            close = float(bar["close"])
            local_t = _to_local_time(bar_ts, tz)

            exit_price: float | None = None
            exit_reason: str | None = None

            # --- 1b. Strategy's invalidation callback — wins over stop/target/EOD. ---
            if strategy.check_invalidation(bar, open_pos):
                exit_price = close
                exit_reason = "invalidation"

            if exit_price is None:
                if side == "long":
                    if low <= stop:
                        exit_price = stop  # pessimistic assumption: stop fills at stop
                        exit_reason = "stop"
                    elif high >= target:
                        exit_price = target
                        exit_reason = "target"
                else:  # short
                    if high >= stop:
                        exit_price = stop
                        exit_reason = "stop"
                    elif low <= target:
                        exit_price = target
                        exit_reason = "target"

            # Force-close at session cutoff.
            if exit_price is None and local_t >= force_close_local:
                exit_price = close
                exit_reason = "force_close"

            if exit_price is not None:
                # Apply slippage to the exit fill price (always against us).
                opposite_side = "short" if side == "long" else "long"
                exit_fill = fee_model.adjust_fill_price(exit_price, opposite_side)
                fees_exit = fee_model.fill_cost(shares, exit_fill)

                gross = (
                    (exit_fill - open_pos["entry_fill"]) * shares
                    if side == "long"
                    else (open_pos["entry_fill"] - exit_fill) * shares
                )
                net = gross - fees_exit  # entry fees already deducted at entry
                equity += net

                trades.append(
                    Trade(
                        symbol=symbol,
                        side=side,  # type: ignore[arg-type]
                        entry_ts=open_pos["entry_ts"],
                        exit_ts=bar_ts,
                        entry_price=open_pos["entry_fill"],
                        exit_price=exit_fill,
                        shares=shares,
                        pnl=net,
                        pnl_pct=net / (open_pos["entry_fill"] * shares) * 100.0,
                        bars_held=i - open_pos["entry_idx"],
                        exit_reason=exit_reason,  # type: ignore[arg-type]
                        regime_tag=open_pos["sig"].regime_tag,
                        categorical_state=open_pos["sig"].categorical_state,
                        fees_paid=open_pos["entry_fees"] + fees_exit,
                        risk_per_share=open_pos["sig"].risk_per_share,
                    )
                )
                open_pos = None

        # --- 2. If no position, see if THIS bar's signal opens one at NEXT bar's open ---
        # We pull the signal at bar T but open the trade at bar T+1's open.
        if open_pos is None and bar_ts in signals_by_ts and i + 1 < n:
            sig = signals_by_ts[bar_ts]
            next_bar = rows[i + 1]
            next_open = float(next_bar["open"])

            # Apply slippage to entry fill.
            entry_fill = fee_model.adjust_fill_price(next_open, sig.side)

            # Position sizing — fixed-fractional risk.
            # Use the *realized* stop distance from the actual fill, not from sig.entry.
            realized_risk_per_share = (
                entry_fill - sig.stop if sig.side == "long" else sig.stop - entry_fill
            )
            if realized_risk_per_share <= 0:
                # Stop on the wrong side of the entry fill — slippage pushed us
                # past our own stop. Not a viable trade.
                skipped_sizing += 1
            elif realized_risk_per_share / entry_fill < min_stop_pct:
                # Guardrail: stop tighter than min_stop_pct of price. On 5-min
                # bars this almost always means same-bar exit / broken signal.
                skipped_min_stop += 1
            else:
                shares = (equity * risk_per_trade) / realized_risk_per_share
                shares = float(int(shares))  # floor — no fractional shares for now
                if shares < 1:
                    skipped_sizing += 1
                elif shares * entry_fill > equity * max_notional_pct:
                    # Guardrail: required notional exceeds max_notional_pct of
                    # equity. Skip rather than clamp — clamping silently breaks
                    # the risk_per_trade promise. A strategy that keeps tripping
                    # this is producing signals with too-tight stops.
                    skipped_max_notional += 1
                else:
                    entry_fees = fee_model.fill_cost(shares, entry_fill)
                    equity -= entry_fees  # pay entry cost immediately

                    open_pos = {
                        "sig": sig,
                        "side": sig.side,
                        "entry_idx": i + 1,
                        "entry_ts": next_bar["ts"],
                        "entry_fill": entry_fill,
                        "stop": sig.stop,
                        "target": sig.target,
                        "shares": shares,
                        "entry_fees": entry_fees,
                    }

        # --- 3. Record mark-to-market equity at this bar's close ---
        if open_pos is not None:
            close = float(bar["close"])
            side = open_pos["side"]
            shares = open_pos["shares"]
            unrealized = (
                (close - open_pos["entry_fill"]) * shares
                if side == "long"
                else (open_pos["entry_fill"] - close) * shares
            )
            equity_pts.append((bar_ts, equity + unrealized, True))
        else:
            equity_pts.append((bar_ts, equity, False))

    # If a position is somehow still open at the end of the data, close it at the last close.
    if open_pos is not None:
        last = rows[-1]
        close = float(last["close"])
        side = open_pos["side"]
        shares = open_pos["shares"]
        opposite_side = "short" if side == "long" else "long"
        exit_fill = fee_model.adjust_fill_price(close, opposite_side)
        fees_exit = fee_model.fill_cost(shares, exit_fill)
        gross = (
            (exit_fill - open_pos["entry_fill"]) * shares
            if side == "long"
            else (open_pos["entry_fill"] - exit_fill) * shares
        )
        net = gross - fees_exit
        equity += net
        trades.append(
            Trade(
                symbol=symbol,
                side=side,  # type: ignore[arg-type]
                entry_ts=open_pos["entry_ts"],
                exit_ts=last["ts"],
                entry_price=open_pos["entry_fill"],
                exit_price=exit_fill,
                shares=shares,
                pnl=net,
                pnl_pct=net / (open_pos["entry_fill"] * shares) * 100.0,
                bars_held=n - 1 - open_pos["entry_idx"],
                exit_reason="force_close",
                regime_tag=open_pos["sig"].regime_tag,
                categorical_state=open_pos["sig"].categorical_state,
                fees_paid=open_pos["entry_fees"] + fees_exit,
                risk_per_share=open_pos["sig"].risk_per_share,
            )
        )

    equity_curve = pl.DataFrame(
        {
            "ts": [p[0] for p in equity_pts],
            "equity": [p[1] for p in equity_pts],
            "open_position": [p[2] for p in equity_pts],
        }
    )

    return BacktestResult(
        strategy_name=strategy.name,
        symbol=symbol,
        starting_equity=starting_equity,
        ending_equity=equity,
        trades=trades,
        equity_curve=equity_curve,
        signals_generated=len(all_signals),
        signals_skipped_by_sizing=skipped_sizing,
        signals_skipped_by_max_notional=skipped_max_notional,
        signals_skipped_by_min_stop=skipped_min_stop,
        fee_model=fee_model,
        config_used={
            "risk_per_trade": risk_per_trade,
            "max_notional_pct": max_notional_pct,
            "min_stop_pct": min_stop_pct,
            "force_close_local": str(force_close_local),
        },
    )
