"""Donchian Channel trend-follower — daily, long-only.

Reference: original Turtle Traders / Richard Dennis. Buy on a 20-day high
breakout, trail the stop at the 10-day low, exit on stop or invalidation.
This is the canonical "trend following on equities" strategy. Most variants
have decayed on indices since the late 1990s, but it's still a worthwhile
diversifier in a portfolio of mean-reverters.

Spec:

* **Universe:** liquid ETFs / individual large-cap stocks.
* **Entry signal at bar T:** close[T] > rolling_max(close, 20)[T-1] (i.e.
  today's close exceeds the previous 20-day high — we exclude today to
  avoid a same-bar tautology).
* **Stop (initial):** entry − 2 × ATR(14).
* **Trailing stop:** rolling_min(low, 10) — tightens only. Engine enforces
  the tighten-only rule.
* **Target:** entry × 1.30 (wide). Designed to NEVER hit; exits are entirely
  via the trailing stop. Set wide to satisfy the Signal validator only.
* **No time-based invalidation.** Let trends run until the trailing stop fires.

Why long-only on indices: short-side equity index trend is historically
asymmetric (sharp/short reversals make trailing-stop systems lose money on
shorts more than they win on the rare bear).
"""

from __future__ import annotations

from typing import Final

import polars as pl

from .base import Signal, Strategy

BREAKOUT_PERIOD: Final = 20
TRAIL_PERIOD: Final = 10
STOP_ATR_MULT: Final = 2.0
TARGET_MULT: Final = 1.30  # wide — exit happens via trailing stop
EXPECTED_DURATION_BARS: Final = 25


class DonchianTrend(Strategy):
    name = "donchian_trend"

    allowed_quant_regimes: frozenset[str] = frozenset()
    allowed_categorical_states: frozenset[str] = frozenset()

    REQUIRED_COLS = ("ts", "open", "high", "low", "close", "atr")

    def __init__(
        self,
        *,
        breakout_period: int = BREAKOUT_PERIOD,
        trail_period: int = TRAIL_PERIOD,
        stop_atr_mult: float = STOP_ATR_MULT,
    ) -> None:
        self.breakout_period = breakout_period
        self.trail_period = trail_period
        self.stop_atr_mult = stop_atr_mult
        # Strategy keeps trailing-stop state per entry_ts so it can compute
        # the rolling min of low on-the-fly without re-scanning the frame.
        self._trailing_lows: dict[object, float] = {}

    def _check_columns(self, df: pl.DataFrame) -> None:
        missing = [c for c in self.REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{self.name}: input frame missing columns: {missing}")

    def generate_signals(self, df: pl.DataFrame) -> list[Signal]:
        self._check_columns(df)
        if df.height < self.breakout_period + 1:
            return []

        symbol = df["symbol"][0] if "symbol" in df.columns else "UNKNOWN"

        # Use prior bar's rolling max (exclude current bar) to avoid same-bar
        # tautology: shift(1) on the rolling max.
        prior_high = pl.col("close").rolling_max(self.breakout_period).shift(1).alias("_prior_high")
        # Also store the bar's own low for the trailing-stop hook to reference
        # via _bar_state if needed. For Donchian, the trailing stop hook computes
        # rolling_min(low, trail_period) over the most recent N bars — we'll
        # precompute it on the frame and store it in a side dict keyed by ts.
        trail_low = pl.col("low").rolling_min(self.trail_period).alias("_trail_low")

        enriched = df.with_columns(prior_high, trail_low)

        # Save the trail-low per-bar so the trailing-stop hook can look it up.
        self._trail_low_by_ts = {
            row["ts"]: float(row["_trail_low"])
            for row in enriched.select("ts", "_trail_low").iter_rows(named=True)
            if row["_trail_low"] is not None
        }

        cond = (
            (pl.col("close") > pl.col("_prior_high"))
            & pl.col("atr").is_not_null()
            & pl.col("_prior_high").is_not_null()
        )

        candidates = enriched.filter(cond)
        signals: list[Signal] = []
        for row in candidates.iter_rows(named=True):
            entry = float(row["close"])
            atr = float(row["atr"])
            stop = entry - self.stop_atr_mult * atr
            target = entry * TARGET_MULT
            if stop <= 0 or stop >= entry:
                continue
            try:
                signals.append(
                    Signal(
                        ts=row["ts"],
                        symbol=symbol,
                        side="long",
                        entry=entry,
                        stop=stop,
                        target=target,
                        invalidation="trailing stop only (no time exit)",
                        regime_tag="daily_no_regime",
                        categorical_state="daily_no_regime",
                        expected_duration_bars=EXPECTED_DURATION_BARS,
                        notes=(
                            f"breakout={self.breakout_period}d "
                            f"prior_high={row['_prior_high']:.3f} atr={atr:.3f}"
                        ),
                    )
                )
            except ValueError:
                continue
        return signals

    def update_trailing_stop(self, bar: dict, open_position: dict) -> float | None:
        """Trail stop at rolling_min(low, trail_period). Engine ignores any
        proposal that would WIDEN the long stop, so this only ratchets up."""
        ts = bar.get("ts")
        return self._trail_low_by_ts.get(ts)
