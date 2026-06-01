"""Bollinger Band mean reversion — daily, long-only.

Classic textbook mean reverter. When price closes below the lower Bollinger
band (2σ below the 20-day SMA), expect a reversion to the middle band.
Combined with a long-only trend filter (close > 200-SMA) to avoid catching
falling knives in bear markets.

Spec:

* **Universe:** liquid ETFs / large-caps.
* **Trend filter (gate):** only fire when close > 200-day SMA.
* **Entry signal at bar T:** close[T] < (SMA20[T] − 2 × stdev20[T]).
* **Stop:** entry − 2.5 × ATR(14).
* **Target:** SMA20[T] (the band middle) — natural mean-reversion target,
  produces R:R typically 1.5–2.5 depending on band width.
* **Invalidation:** close after 10 bars regardless.

Why long-only: same logic as IBS — short BB extensions on liquid ETFs have
poor edge due to the long-run drift. Stay aligned with the asset's bias.
"""

from __future__ import annotations

from typing import Final

import polars as pl

from .base import Signal, Strategy

BB_PERIOD: Final = 20
BB_STDEV: Final = 2.0
TREND_SMA_PERIOD: Final = 200
STOP_ATR_MULT: Final = 2.5
MAX_HOLD_BARS: Final = 10
EXPECTED_DURATION_BARS: Final = 5
MIN_TARGET_DISTANCE_PCT: Final = 0.003  # require target > entry by ≥30 bps


class BollingerMR(Strategy):
    name = "bollinger_mr"

    allowed_quant_regimes: frozenset[str] = frozenset()
    allowed_categorical_states: frozenset[str] = frozenset()

    REQUIRED_COLS = ("ts", "open", "high", "low", "close", "atr")

    def __init__(
        self,
        *,
        bb_period: int = BB_PERIOD,
        bb_stdev: float = BB_STDEV,
        trend_sma_period: int = TREND_SMA_PERIOD,
        stop_atr_mult: float = STOP_ATR_MULT,
        max_hold_bars: int = MAX_HOLD_BARS,
    ) -> None:
        self.bb_period = bb_period
        self.bb_stdev = bb_stdev
        self.trend_sma_period = trend_sma_period
        self.stop_atr_mult = stop_atr_mult
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

        bb_sma = pl.col("close").rolling_mean(self.bb_period).alias("_bb_sma")
        bb_std = pl.col("close").rolling_std(self.bb_period).alias("_bb_std")
        trend_sma = pl.col("close").rolling_mean(self.trend_sma_period).alias("_trend_sma")

        enriched = df.with_columns(bb_sma, bb_std, trend_sma).with_columns(
            (pl.col("_bb_sma") - self.bb_stdev * pl.col("_bb_std")).alias("_bb_lower"),
        )

        cond = (
            (pl.col("close") < pl.col("_bb_lower"))
            & (pl.col("close") > pl.col("_trend_sma"))
            & pl.col("atr").is_not_null()
            & pl.col("_bb_sma").is_not_null()
            & pl.col("_trend_sma").is_not_null()
        )

        candidates = enriched.filter(cond)
        signals: list[Signal] = []
        for row in candidates.iter_rows(named=True):
            entry = float(row["close"])
            atr = float(row["atr"])
            target = float(row["_bb_sma"])
            stop = entry - self.stop_atr_mult * atr

            # Sanity gates
            if stop <= 0 or stop >= entry:
                continue
            if target <= entry * (1 + MIN_TARGET_DISTANCE_PCT):
                continue  # target too close — won't beat costs

            try:
                signals.append(
                    Signal(
                        ts=row["ts"],
                        symbol=symbol,
                        side="long",
                        entry=entry,
                        stop=stop,
                        target=target,
                        invalidation=f"close after {self.max_hold_bars} bars",
                        regime_tag="daily_no_regime",
                        categorical_state="daily_no_regime",
                        expected_duration_bars=EXPECTED_DURATION_BARS,
                        notes=f"bb_lower={row['_bb_lower']:.3f} atr={atr:.3f}",
                    )
                )
            except ValueError:
                continue
        return signals

    def check_invalidation(self, bar: dict, open_position: dict) -> bool:
        return open_position.get("bars_held", 0) >= self.max_hold_bars
