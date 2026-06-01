"""Intraday momentum on SPY (Zarattini / Aziz / Barbon 2024).

See ``docs/strategies/intraday_momentum_spy.md`` for the full spec. This is
the executable version. If they disagree, the spec wins and the code is
the bug.

Pipeline:

1. Caller provides 30-min bars with ATR, ADX, session-VWAP, and regime
   columns already computed. (Use ``src.features.*`` + ``src.regimes.*``.)
2. ``generate_signals`` pre-computes per-day metrics (today's open, prev
   close, 14-day rolling average of intraday absolute deviation) and bands,
   stashes them in ``self._bar_state``, then evaluates entry conditions.
3. The research backtester calls ``update_trailing_stop`` and
   ``check_invalidation`` on every bar while a position is open — those
   methods look up the precomputed values in ``self._bar_state`` rather
   than recomputing per bar.

Notes:

* This strategy expects **30-min** bars. The Parquet store has 5-min bars
  for SPY/QQQ; the caller (run_backtest.py) is responsible for resampling
  before passing the frame to this strategy.
* Position sizing is the engine's standard fixed-fractional. The paper uses
  a 2 % volatility target; we deliberately don't, to keep risk consistent
  across all strategies in the portfolio.
* All trailing-stop / invalidation hooks are pure functions of the bar +
  precomputed state — no hidden mutation across bars.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

import polars as pl

from .base import Signal, Strategy

NY_TZ = ZoneInfo("America/New_York")

DEVIATION_WINDOW: Final = 14         # rolling-window days
MAX_STOP_PCT_OF_PRICE: Final = 0.01  # 1 % cap on initial stop distance
ATR_STOP_CAP_MULT: Final = 2.0       # trailing stop never wider than 2 × ATR
MIN_DEVIATION_PCTILE: Final = 0.05   # skip days where deviation_14d is in bottom 5 %

# Momentum strategies need at least some directional energy *or* a vol spike.
# We allow: any weak/strong trend bucket, plus range_high (vol spike inside a
# range). We forbid: range_low and range_medium (the consolidation regimes
# where Range MR would belong).
_ALLOWED_QUANT_REGIMES = frozenset(
    {
        "weak_trend_low",
        "weak_trend_medium",
        "weak_trend_high",
        "strong_trend_low",
        "strong_trend_medium",
        "strong_trend_high",
        "range_high",
    }
)
# Per risk_policy.md, chaotic is a system-wide no-trade gate. So only
# 'directional' is allowed. 'consolidating' is wrong regime for momentum.
_ALLOWED_CATEGORICAL_STATES = frozenset({"directional"})


class IntradayMomentumSPY(Strategy):
    name = "intraday_momentum_spy"

    allowed_quant_regimes = _ALLOWED_QUANT_REGIMES
    allowed_categorical_states = _ALLOWED_CATEGORICAL_STATES

    REQUIRED_COLS = (
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "symbol",
        "atr",
        "vwap",
        "quant_regime",
        "categorical_state",
    )

    def __init__(
        self,
        *,
        deviation_window: int = DEVIATION_WINDOW,
        max_stop_pct: float = MAX_STOP_PCT_OF_PRICE,
        atr_stop_cap_mult: float = ATR_STOP_CAP_MULT,
        min_deviation_pctile: float = MIN_DEVIATION_PCTILE,
        tz: ZoneInfo = NY_TZ,
    ) -> None:
        if deviation_window < 2:
            raise ValueError("deviation_window must be >= 2")
        if not 0 < max_stop_pct < 0.1:
            raise ValueError("max_stop_pct must be in (0, 0.1)")
        if atr_stop_cap_mult <= 0:
            raise ValueError("atr_stop_cap_mult must be > 0")
        if not 0 <= min_deviation_pctile < 0.5:
            raise ValueError("min_deviation_pctile must be in [0, 0.5)")

        self.deviation_window = deviation_window
        self.max_stop_pct = max_stop_pct
        self.atr_stop_cap_mult = atr_stop_cap_mult
        self.min_deviation_pctile = min_deviation_pctile
        self.tz = tz

        # Per-ts cache populated during generate_signals and consumed during
        # update_trailing_stop / check_invalidation. Keyed by the bar's ts
        # (timezone-aware datetime) → dict of precomputed values for that bar.
        self._bar_state: dict[datetime, dict] = {}

    # ------------------------------------------------------------------
    # Schema check
    # ------------------------------------------------------------------
    def _check_columns(self, df: pl.DataFrame) -> None:
        missing = [c for c in self.REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"{self.name}: input frame missing columns: {missing}. "
                "Run features + regime classifier first, and resample to 30-min."
            )

    # ------------------------------------------------------------------
    # Indicator pipeline — pure, no lookahead
    # ------------------------------------------------------------------
    def _enrich(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add per-bar columns: open_today, prev_close, deviation_14d, bands.

        No lookahead: every column at row T uses only data <= T. In
        particular, ``deviation_14d`` is built from *prior* days only
        (today's own intraday deviation is excluded — that would peek into
        the future of today's close from inside today).
        """
        if df.is_empty():
            return df

        # 1. Session date in NY tz — used as the grouping key.
        ts_dtype = df.schema["ts"]
        if isinstance(ts_dtype, pl.Datetime) and ts_dtype.time_zone is None:
            ts_local = (
                pl.col("ts").dt.replace_time_zone("UTC").dt.convert_time_zone(str(self.tz))
            )
        else:
            ts_local = pl.col("ts").dt.convert_time_zone(str(self.tz))

        df = df.with_columns(ts_local.dt.date().alias("_session_date"))

        # 2. Per-day metrics: today's open, today's last close, intraday
        #    average absolute deviation from today's open.
        df = df.sort("ts").with_columns(
            # First-bar open of the day, broadcast to every bar in the day.
            pl.col("open").first().over("_session_date").alias("_open_today"),
            # Per-bar intraday deviation magnitude.
            (
                (pl.col("close") - pl.col("open").first().over("_session_date")).abs()
                / pl.col("open").first().over("_session_date")
            ).alias("_intraday_dev"),
        )

        # 3. Daily aggregates → one row per day.
        daily = (
            df.group_by("_session_date")
            .agg(
                pl.col("_intraday_dev").mean().alias("_daily_avg_dev"),
                pl.col("close").last().alias("_day_close"),
            )
            .sort("_session_date")
        )

        # 4. Lagged rolling deviation (no lookahead) + prev_close (yesterday's close).
        daily = daily.with_columns(
            pl.col("_daily_avg_dev")
            .shift(1)
            .rolling_mean(window_size=self.deviation_window)
            .alias("_deviation_14d"),
            pl.col("_day_close").shift(1).alias("_prev_close"),
        )

        # 5. Quantile floor on deviation (skip days where typical intraday
        #    move is in the bottom 5 % of history — markets too quiet to
        #    expect a real breakout).
        if self.min_deviation_pctile > 0:
            # Compute the historical quantile threshold *up to but not
            # including* today, by sorting + cumulative quantile. Simpler
            # approximation: use the rolling quantile over a generous window
            # (e.g. 100 days) of the lagged daily_avg_dev. This is a
            # reasonable proxy; perfect "all of history" quantile would
            # require a global pass.
            daily = daily.with_columns(
                pl.col("_daily_avg_dev")
                .shift(1)
                .rolling_quantile(
                    quantile=self.min_deviation_pctile,
                    window_size=100,
                    min_periods=20,
                )
                .alias("_deviation_quiet_floor"),
            )
        else:
            daily = daily.with_columns(
                pl.lit(0.0, dtype=pl.Float64).alias("_deviation_quiet_floor"),
            )

        # 6. Join the daily metrics back onto the bar-level frame.
        df = df.join(
            daily.select(
                "_session_date", "_deviation_14d", "_prev_close", "_deviation_quiet_floor"
            ),
            on="_session_date",
            how="left",
        )

        # 7. Bands. Null-safe: if any input is null, the band is null and
        #    the entry condition below will fail naturally.
        df = df.with_columns(
            (
                pl.max_horizontal("_open_today", "_prev_close")
                * (1.0 + pl.col("_deviation_14d"))
            ).alias("_upper_band"),
            (
                pl.min_horizontal("_open_today", "_prev_close")
                * (1.0 - pl.col("_deviation_14d"))
            ).alias("_lower_band"),
        )

        # 8. "Is this the first bar of the day?" flag — used to forbid
        #    entries on the bar that establishes today's open.
        df = df.with_columns(
            (pl.col("ts") == pl.col("ts").first().over("_session_date")).alias(
                "_is_first_bar"
            ),
            (pl.col("ts") == pl.col("ts").last().over("_session_date")).alias(
                "_is_last_bar"
            ),
        )

        return df

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------
    def generate_signals(self, df: pl.DataFrame) -> list[Signal]:
        self._check_columns(df)
        if df.height < self.deviation_window + 2:
            return []

        self._bar_state = {}  # reset for this run

        symbol = df["symbol"][0] if "symbol" in df.columns else "UNKNOWN"
        enriched = self._enrich(df)

        # Populate _bar_state for ALL bars (the engine may call our hooks on
        # any bar while a position is open, not just signal bars).
        for row in enriched.iter_rows(named=True):
            self._bar_state[row["ts"]] = {
                "vwap": row.get("vwap"),
                "upper_band": row.get("_upper_band"),
                "lower_band": row.get("_lower_band"),
                "atr": row.get("atr"),
                "quant_regime": row.get("quant_regime"),
                "categorical_state": row.get("categorical_state"),
                "deviation_14d": row.get("_deviation_14d"),
            }

        # Entry conditions, vectorized.
        regime_ok = (
            pl.col("quant_regime").is_in(list(self.allowed_quant_regimes))
            & pl.col("categorical_state").is_in(list(self.allowed_categorical_states))
            & pl.col("vwap").is_not_null()
            & pl.col("atr").is_not_null()
            & pl.col("_upper_band").is_not_null()
            & pl.col("_lower_band").is_not_null()
            & pl.col("_deviation_14d").is_not_null()
            & (pl.col("_deviation_14d") > pl.col("_deviation_quiet_floor"))
            & ~pl.col("_is_first_bar")
            & ~pl.col("_is_last_bar")
        )

        long_condition = (
            regime_ok
            & (pl.col("close") > pl.col("_upper_band"))
            & (pl.col("close") > pl.col("vwap"))
        )
        short_condition = (
            regime_ok
            & (pl.col("close") < pl.col("_lower_band"))
            & (pl.col("close") < pl.col("vwap"))
        )

        enriched = enriched.with_columns(
            long_condition.alias("_long_sig"),
            short_condition.alias("_short_sig"),
        )

        candidates = enriched.filter(pl.col("_long_sig") | pl.col("_short_sig"))

        signals: list[Signal] = []
        for row in candidates.iter_rows(named=True):
            side = "long" if row["_long_sig"] else "short"
            entry_price = float(row["close"])
            vwap = float(row["vwap"])
            upper = float(row["_upper_band"])
            lower = float(row["_lower_band"])
            atr = float(row["atr"])

            # Initial stop = the trailing stop level for this bar.
            if side == "long":
                stop = max(vwap, upper)
                # Cap to never be wider than ATR_STOP_CAP_MULT × ATR.
                stop = max(stop, entry_price - self.atr_stop_cap_mult * atr)
                # Stop must be below entry for a long.
                if stop >= entry_price:
                    continue
            else:
                stop = min(vwap, lower)
                stop = min(stop, entry_price + self.atr_stop_cap_mult * atr)
                if stop <= entry_price:
                    continue

            stop_dist = abs(entry_price - stop)
            if stop_dist / entry_price > self.max_stop_pct:
                continue  # initial stop too wide; pathological vol day

            # Target: we don't run a fixed target — this strategy rides the
            # trail. We set a far-out target so the engine's target-hit logic
            # essentially never fires; exits happen via trailing stop,
            # invalidation, or force-close.
            target_far = (
                entry_price * 100.0 if side == "long" else entry_price / 100.0
            )

            try:
                sig = Signal(
                    ts=row["ts"],
                    symbol=symbol,
                    side=side,  # type: ignore[arg-type]
                    entry=entry_price,
                    stop=stop,
                    target=target_far,
                    invalidation=(
                        "VWAP crosses against position, or regime flips out of "
                        "{weak_trend_*, strong_trend_*, range_high} × {directional}"
                    ),
                    regime_tag=str(row["quant_regime"]),
                    categorical_state=str(row["categorical_state"]),
                    expected_duration_bars=6,  # roughly 3 hours
                    notes=(
                        f"upper={upper:.2f} lower={lower:.2f} "
                        f"vwap={vwap:.2f} atr={atr:.4f}"
                    ),
                )
            except ValueError:
                continue

            signals.append(sig)

        return signals

    # ------------------------------------------------------------------
    # Mid-trade hooks
    # ------------------------------------------------------------------
    def update_trailing_stop(
        self,
        bar: dict,
        open_position: dict,
    ) -> float | None:
        """Recompute the trailing stop from the bar's vwap and band level.

        Engine enforces the 'tighten only' guarantee, so we can propose
        freely and let the engine reject any proposal that would loosen.
        """
        state = self._bar_state.get(bar["ts"])
        if state is None or state["vwap"] is None:
            return None

        side = open_position["side"]
        close = float(bar["close"])
        atr = state.get("atr")

        if side == "long":
            upper = state["upper_band"]
            if upper is None:
                return None
            proposed = max(float(state["vwap"]), float(upper))
            if atr is not None:
                # Cap: never wider than ATR_STOP_CAP_MULT × ATR below close.
                proposed = max(proposed, close - self.atr_stop_cap_mult * float(atr))
        else:
            lower = state["lower_band"]
            if lower is None:
                return None
            proposed = min(float(state["vwap"]), float(lower))
            if atr is not None:
                proposed = min(proposed, close + self.atr_stop_cap_mult * float(atr))

        return float(proposed)

    def check_invalidation(
        self,
        bar: dict,
        open_position: dict,
    ) -> bool:
        """Exit immediately if VWAP crosses against the position or the
        regime flips out of the allowed set."""
        state = self._bar_state.get(bar["ts"])
        if state is None:
            return False

        side = open_position["side"]
        close = float(bar["close"])
        vwap = state.get("vwap")

        # VWAP cross against the position.
        if vwap is not None:
            if side == "long" and close < float(vwap):
                return True
            if side == "short" and close > float(vwap):
                return True

        # Regime flipped out.
        quant = state.get("quant_regime")
        cat = state.get("categorical_state")
        if quant is not None and quant not in self.allowed_quant_regimes:
            return True
        if cat is not None and cat not in self.allowed_categorical_states:
            return True

        return False
