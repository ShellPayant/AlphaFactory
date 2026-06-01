"""Walk-forward backtesting harness.

The single most important defense against curve-fitting: instead of running
a strategy on the full history and trusting the headline Sharpe, we split
the history into rolling (train, test) windows and report OOS metrics per
window.

For v0.1 we do **param-fixed walk-forward** — the strategy's parameters
are not re-tuned per window; we only re-run the same strategy on each test
slice. This catches:

* Regime dependence — a strategy that works only in 2020-2022 will show
  great early windows and dead later ones.
* Stability — does the OOS Sharpe stay positive across windows, or does
  it swing wildly?

What this version deliberately does NOT do (deferred to v0.2):

* Parameter optimization during the train phase. That requires strategies
  to expose tunable params and a search method. Adds significant scope.
* Combinatorial purged k-fold (López de Prado). Standard rolling walk-
  forward is sufficient for a v0.1 sanity check.

Usage::

    from src.backtest.walk_forward import run_walk_forward
    from src.strategies import IntradayMomentumSPY

    result = run_walk_forward(
        bars=enriched_bars,
        strategy_factory=IntradayMomentumSPY,   # zero-arg callable
        train_months=18,
        test_months=6,
        step_months=6,
        fee_model=ALPACA_PAPER,
    )
    print(result.summary())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

import polars as pl

from src.strategies.base import Strategy

from .fees import ALPACA_PAPER, FeeModel
from .metrics import DEFAULT_BARS_PER_YEAR, equity_curve_stats
from .research_engine import BacktestResult, Trade, run_backtest


@dataclass
class WindowResult:
    """OOS metrics for a single walk-forward window."""

    window_idx: int
    train_start: datetime
    train_end: datetime  # == test_start
    test_start: datetime
    test_end: datetime
    n_trades: int
    starting_equity: float
    ending_equity: float
    total_return_pct: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    time_under_water_pct: float
    win_rate: float
    profit_factor: float
    oos_trades: list[Trade] = field(default_factory=list)


@dataclass
class WalkForwardResult:
    """Aggregate of all per-window OOS metrics."""

    strategy_name: str
    symbol: str
    train_months: int
    test_months: int
    step_months: int
    windows: list[WindowResult] = field(default_factory=list)

    @property
    def n_windows(self) -> int:
        return len(self.windows)

    @property
    def n_positive_sharpe_windows(self) -> int:
        return sum(1 for w in self.windows if w.sharpe > 0)

    @property
    def n_positive_return_windows(self) -> int:
        return sum(1 for w in self.windows if w.total_return_pct > 0)

    @property
    def mean_sharpe(self) -> float:
        if not self.windows:
            return 0.0
        return sum(w.sharpe for w in self.windows) / len(self.windows)

    @property
    def median_sharpe(self) -> float:
        if not self.windows:
            return 0.0
        s = sorted(w.sharpe for w in self.windows)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    @property
    def worst_window_sharpe(self) -> float:
        return min((w.sharpe for w in self.windows), default=0.0)

    @property
    def best_window_sharpe(self) -> float:
        return max((w.sharpe for w in self.windows), default=0.0)

    @property
    def sharpe_std(self) -> float:
        if len(self.windows) < 2:
            return 0.0
        m = self.mean_sharpe
        v = sum((w.sharpe - m) ** 2 for w in self.windows) / (len(self.windows) - 1)
        return v ** 0.5

    @property
    def total_trades(self) -> int:
        return sum(w.n_trades for w in self.windows)

    @property
    def all_oos_trades(self) -> list[Trade]:
        """Flat list of every OOS trade across all windows — for Monte Carlo."""
        return [t for w in self.windows for t in w.oos_trades]

    def passes_g1_5_no_negative_window(self) -> bool:
        """G1.5 sub-criterion: no walk-forward window with Sharpe < 0."""
        return self.worst_window_sharpe >= 0.0

    def passes_g1_5_min_windows(self, min_windows: int = 3) -> bool:
        """G1.5 sub-criterion: survived at least N windows."""
        return self.n_windows >= min_windows

    def summary(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "n_windows": self.n_windows,
            "total_trades": self.total_trades,
            "mean_sharpe": self.mean_sharpe,
            "median_sharpe": self.median_sharpe,
            "sharpe_std": self.sharpe_std,
            "worst_window_sharpe": self.worst_window_sharpe,
            "best_window_sharpe": self.best_window_sharpe,
            "n_positive_sharpe_windows": self.n_positive_sharpe_windows,
            "n_positive_return_windows": self.n_positive_return_windows,
            "g1_5_no_negative_window": self.passes_g1_5_no_negative_window(),
            "g1_5_min_3_windows": self.passes_g1_5_min_windows(3),
        }


def _add_months(dt: datetime, months: int) -> datetime:
    """Add `months` to a datetime, rolling over years cleanly."""
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    # Clamp day to month's last day to avoid Feb 30 problems.
    import calendar
    d = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=d)


def _slice_bars(bars: pl.DataFrame, start: datetime, end: datetime) -> pl.DataFrame:
    """Slice bars where start <= ts <= end."""
    return bars.filter((pl.col("ts") >= start) & (pl.col("ts") <= end))


def _filter_trades_to_window(
    trades: list[Trade], test_start: datetime, test_end: datetime
) -> list[Trade]:
    """Keep trades whose entry_ts falls inside the OOS test window."""
    return [t for t in trades if test_start <= t.entry_ts <= test_end]


def _slice_equity_curve_to_window(
    equity_curve: pl.DataFrame, test_start: datetime, test_end: datetime
) -> pl.DataFrame:
    if equity_curve.is_empty():
        return equity_curve
    return equity_curve.filter(
        (pl.col("ts") >= test_start) & (pl.col("ts") <= test_end)
    )


def run_walk_forward(
    bars: pl.DataFrame,
    strategy_factory: Callable[[], Strategy],
    *,
    timeframe: str = "30m",
    train_months: int = 18,
    test_months: int = 6,
    step_months: int = 6,
    starting_equity: float = 100_000.0,
    risk_per_trade: float = 0.0025,
    max_notional_pct: float = 1.0,
    min_stop_pct: float = 0.0005,
    fee_model: FeeModel = ALPACA_PAPER,
    symbol: str | None = None,
) -> WalkForwardResult:
    """Run a rolling walk-forward backtest.

    Each window: bars are sliced to ``[train_start, test_end]`` (so the
    strategy's indicators get train-period warmup), the backtest runs on
    the full slice, then trades and the equity curve are filtered to the
    test period only. Per-window metrics are computed from the filtered
    slices, with the equity curve re-anchored to ``starting_equity`` at
    ``test_start`` (each window is independent — no equity carry-over).

    The first window starts at ``bars[0].ts + train_months``. Windows
    advance by ``step_months`` until ``test_end`` exceeds ``bars[-1].ts``.
    """
    if bars.is_empty():
        raise ValueError("Cannot walk-forward on empty bars frame.")
    if train_months < 1 or test_months < 1 or step_months < 1:
        raise ValueError("train_months, test_months, step_months must each be >= 1")

    sym = symbol or (bars["symbol"][0] if "symbol" in bars.columns else "UNKNOWN")
    # Get first/last ts as timezone-aware UTC datetimes.
    first_ts: datetime = bars["ts"][0]
    last_ts: datetime = bars["ts"][-1]
    if first_ts.tzinfo is None:
        first_ts = first_ts.replace(tzinfo=timezone.utc)
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)

    bpy = DEFAULT_BARS_PER_YEAR.get(timeframe, 252 * 78)

    # Build the schedule of windows.
    windows: list[tuple[datetime, datetime, datetime, datetime]] = []
    train_start = first_ts
    while True:
        test_start = _add_months(train_start, train_months)
        test_end = _add_months(test_start, test_months)
        if test_end > last_ts:
            break
        windows.append((train_start, test_start, test_start, test_end))
        train_start = _add_months(train_start, step_months)

    result = WalkForwardResult(
        strategy_name="",  # filled after first window
        symbol=sym,
        train_months=train_months,
        test_months=test_months,
        step_months=step_months,
    )

    for idx, (tr_start, tr_end, te_start, te_end) in enumerate(windows):
        window_bars = _slice_bars(bars, tr_start, te_end)
        if window_bars.is_empty():
            continue

        strategy = strategy_factory()
        if not result.strategy_name:
            result.strategy_name = strategy.name

        # Run full-slice backtest so indicators warm up across the train
        # period. Trades/equity are then filtered to the OOS test window.
        bt = run_backtest(
            window_bars,
            strategy,
            starting_equity=starting_equity,
            risk_per_trade=risk_per_trade,
            max_notional_pct=max_notional_pct,
            min_stop_pct=min_stop_pct,
            fee_model=fee_model,
        )

        oos_trades = _filter_trades_to_window(bt.trades, te_start, te_end)
        oos_equity = _slice_equity_curve_to_window(bt.equity_curve, te_start, te_end)

        # Re-anchor: each window starts fresh from starting_equity. The
        # engine's accumulated equity from the train period doesn't count
        # as OOS performance.
        if not oos_equity.is_empty():
            first_eq = oos_equity["equity"][0]
            shift = starting_equity - first_eq
            oos_equity = oos_equity.with_columns(
                (pl.col("equity") + shift).alias("equity")
            )

        eq_stats = equity_curve_stats(
            oos_equity, starting_equity=starting_equity, bars_per_year=bpy
        )

        # Per-window trade stats — inline here so we don't depend on the
        # full all_metrics for a partial result.
        n = len(oos_trades)
        wins = [t.pnl for t in oos_trades if t.pnl > 0]
        losses = [t.pnl for t in oos_trades if t.pnl <= 0]
        win_rate = (len(wins) / n) if n else 0.0
        profit_factor = (
            (sum(wins) / -sum(losses))
            if losses
            else (float("inf") if wins else 0.0)
        )

        ending_eq = (
            float(oos_equity["equity"][-1]) if not oos_equity.is_empty() else starting_equity
        )

        result.windows.append(
            WindowResult(
                window_idx=idx,
                train_start=tr_start,
                train_end=tr_end,
                test_start=te_start,
                test_end=te_end,
                n_trades=n,
                starting_equity=starting_equity,
                ending_equity=ending_eq,
                total_return_pct=eq_stats["total_return_pct"],
                sharpe=eq_stats["sharpe"],
                sortino=eq_stats["sortino"],
                max_drawdown_pct=eq_stats["max_drawdown_pct"],
                time_under_water_pct=eq_stats["time_under_water_pct"],
                win_rate=win_rate,
                profit_factor=profit_factor,
                oos_trades=oos_trades,
            )
        )

    return result


def render_walk_forward_markdown(result: WalkForwardResult) -> str:
    """Render a walk-forward result as a Markdown table + summary block."""
    lines: list[str] = []
    lines.append(f"# Walk-Forward Report — `{result.strategy_name}` on `{result.symbol}`")
    lines.append("")
    lines.append(
        f"_train={result.train_months}mo, test={result.test_months}mo, "
        f"step={result.step_months}mo, n_windows={result.n_windows}_"
    )
    lines.append("")

    lines.append("## Per-window OOS metrics")
    lines.append("")
    lines.append(
        "| # | Test start | Test end | Trades | Ret % | Sharpe | Sortino | MaxDD % | WinRate | PF |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for w in result.windows:
        pf = "∞" if w.profit_factor == float("inf") else f"{w.profit_factor:.2f}"
        lines.append(
            f"| {w.window_idx} | {w.test_start.date()} | {w.test_end.date()} | "
            f"{w.n_trades} | {w.total_return_pct:+.2f} | {w.sharpe:.2f} | "
            f"{w.sortino:.2f} | {w.max_drawdown_pct:.2f} | {w.win_rate*100:.1f}% | {pf} |"
        )
    lines.append("")

    s = result.summary()
    lines.append("## Aggregate")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Windows | {s['n_windows']} |")
    lines.append(f"| Total OOS trades | {s['total_trades']} |")
    lines.append(f"| Mean Sharpe | {s['mean_sharpe']:.2f} |")
    lines.append(f"| Median Sharpe | {s['median_sharpe']:.2f} |")
    lines.append(f"| Sharpe std-dev | {s['sharpe_std']:.2f} |")
    lines.append(f"| Best window Sharpe | {s['best_window_sharpe']:.2f} |")
    lines.append(f"| Worst window Sharpe | {s['worst_window_sharpe']:.2f} |")
    lines.append(
        f"| Windows with positive Sharpe | {s['n_positive_sharpe_windows']} / {s['n_windows']} |"
    )
    lines.append(
        f"| Windows with positive return | {s['n_positive_return_windows']} / {s['n_windows']} |"
    )
    lines.append("")

    lines.append("## G1.5 graduation gate")
    lines.append("")
    no_neg = "✅ pass" if s["g1_5_no_negative_window"] else "❌ FAIL"
    min_3 = "✅ pass" if s["g1_5_min_3_windows"] else "❌ FAIL"
    lines.append(f"- No window with Sharpe < 0 → **{no_neg}**")
    lines.append(f"- ≥ 3 walk-forward windows tested → **{min_3}**")
    lines.append("")

    return "\n".join(lines)
