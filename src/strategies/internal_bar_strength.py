"""Internal Bar Strength (IBS) mean reversion — daily, long-only.

Reference: Larry Connors / various practitioner sources. IBS measures where
today's close sits inside today's range:

    IBS(T) = (close[T] - low[T]) / (high[T] - low[T])

Empirical observation on liquid ETFs: when IBS is very low (close near the
low), there's a small mean-reverting bias on the next day. The edge has
decayed since the early literature but it's still one of the more robust
*long-only ETF* patterns and worth re-validating.

Spec:

* **Universe:** any liquid ETF / large-cap (we run on SPY by default).
* **Trend filter (gate):** only fire when close > 200-day SMA. We don't
  buy weakness in a bear market.
* **Entry signal at bar T:** IBS(T) ≤ 0.20.
* **Order:** long at open of T+1 (engine handles next-bar fill).
* **Stop:** entry − 2 × ATR(14). Comfortably wide for daily bars.
* **Target:** entry + 6 × ATR(14). Wide — usually exited by invalidation.
* **Invalidation (time-based exit):** close position after 5 bars (≈ 1
  trading week) regardless of price.

Why long-only: short-side IBS extensions (IBS ≥ 0.80) historically have
*negative* edge — going against the daily up-bias is a fee trap for retail.
"""

from __future__ import annotations

from typing import Final

import polars as pl

from .base import Signal, Strategy

IBS_THRESHOLD: Final = 0.20
TREND_SMA_PERIOD: Final = 200
STOP_ATR_MULT: Final = 2.0
TARGET_ATR_MULT: Final = 6.0
EXPECTED_DURATION_BARS: Final = 5
MAX_HOLD_BARS: Final = 5
MIN_BAR_RANGE_PCT: Final = 0.0005  # skip degenerate inside bars (range < 5 bps)


class InternalBarStrength(Strategy):
    name = "internal_bar_strength"

    allowed_quant_regimes: frozenset[str] = frozenset()
    allowed_categorical_states: frozenset[str] = frozenset()

    REQUIRED_COLS = ("ts", "open", "high", "low", "close", "atr")

    def __init__(
        self,
        *,
        ibs_threshold: float = IBS_THRESHOLD,
        trend_sma_period: int = TREND_SMA_PERIOD,
        stop_atr_mult: float = STOP_ATR_MULT,
        target_atr_mult: float = TARGET_ATR_MULT,
        max_hold_bars: int = MAX_HOLD_BARS,
    ) -> None:
        if not 0 < ibs_threshold < 1:
            raise ValueError("ibs_threshold must be in (0, 1)")
        self.ibs_threshold = ibs_threshold
        self.trend_sma_period = trend_sma_period
        self.stop_atr_mult = stop_atr_mult
        self.target_atr_mult = target_atr_mult
        self.max_hold_bars = max_hold_bars

    def _check_columns(self, df: pl.DataFrame) -> None:
        missing = [c for c in self.REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{self.name}: input frame missing columns: {missing}")

    def generate_signals(self, df: pl.DataFrame) -> list[Signal]:
        self._check_columns(df)
        if df.height < self.trend_sma_period + 1:
            return []

        symbol = df["symbol"][0] if "symbol" in df.columns else "UNKNOWN"

        bar_range = pl.col("high") - pl.col("low")
        ibs = ((pl.col("close") - pl.col("low")) / bar_range).alias("_ibs")
        trend_sma = pl.col("close").rolling_mean(self.trend_sma_period).alias("_trend_sma")
        range_pct = (bar_range / pl.col("close")).alias("_range_pct")

        enriched = df.with_columns(ibs, trend_sma, range_pct)

        cond = (
            (pl.col("_ibs") <= self.ibs_threshold)
            & (pl.col("close") > pl.col("_trend_sma"))
            & (pl.col("_range_pct") > MIN_BAR_RANGE_PCT)
            & pl.col("atr").is_not_null()
            & pl.col("_trend_sma").is_not_null()
        )

        candidates = enriched.filter(cond)
        signals: list[Signal] = []
        for row in candidates.iter_rows(named=True):
            entry = float(row["close"])
            atr = float(row["atr"])
            stop = entry - self.stop_atr_mult * atr
            target = entry + self.target_atr_mult * atr
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
                        invalidation=f"close position after {self.max_hold_bars} bars",
                        regime_tag="daily_no_regime",
                        categorical_state="daily_no_regime",
                        expected_duration_bars=EXPECTED_DURATION_BARS,
                        notes=f"ibs={row['_ibs']:.3f} atr={atr:.3f}",
                    )
                )
            except ValueError:
                continue
        return signals

    def check_invalidation(self, bar: dict, open_position: dict) -> bool:
        """Time-based exit: close after max_hold_bars."""
        bars_held = open_position.get("bars_held", 0)
        return bars_held >= self.max_hold_bars
