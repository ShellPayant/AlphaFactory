"""5-day low reversal — daily, long-only.

A simpler cousin of the RSI(2) pullback that doesn't depend on a momentum
indicator. Logic: in an uptrend (close > 200-SMA), if today's close is the
LOWEST of the last 5 bars, expect a bounce over the next few days. Pure
price-action mean reversion with a trend filter.

Spec:

* **Universe:** liquid ETFs.
* **Trend filter (gate):** close > 200-day SMA.
* **Entry signal at bar T:** close[T] == min(close, 5)[T] AND close[T] is
  also below the previous close (the dip is real, not flat).
* **Stop:** entry − 2.5 × ATR(14).
* **Target:** entry + 4 × ATR(14). R:R ~1.6.
* **Invalidation:** close > 5-day SMA OR after 5 bars.

Why include this alongside RSI(2): RSI(2) is one indicator; 5-day-low is
pure price structure. Diversifying on signal source insulates the portfolio
against any single indicator's specific failure modes.
"""

from __future__ import annotations

from typing import Final

import polars as pl

from .base import Signal, Strategy

LOW_LOOKBACK: Final = 5
TREND_SMA_PERIOD: Final = 200
EXIT_SMA_PERIOD: Final = 5
STOP_ATR_MULT: Final = 2.5
TARGET_ATR_MULT: Final = 4.0
MAX_HOLD_BARS: Final = 5
EXPECTED_DURATION_BARS: Final = 3


class FiveDayReversal(Strategy):
    name = "five_day_reversal"

    allowed_quant_regimes: frozenset[str] = frozenset()
    allowed_categorical_states: frozenset[str] = frozenset()

    REQUIRED_COLS = ("ts", "open", "high", "low", "close", "atr")

    def __init__(
        self,
        *,
        low_lookback: int = LOW_LOOKBACK,
        trend_sma_period: int = TREND_SMA_PERIOD,
        exit_sma_period: int = EXIT_SMA_PERIOD,
        stop_atr_mult: float = STOP_ATR_MULT,
        target_atr_mult: float = TARGET_ATR_MULT,
        max_hold_bars: int = MAX_HOLD_BARS,
    ) -> None:
        self.low_lookback = low_lookback
        self.trend_sma_period = trend_sma_period
        self.exit_sma_period = exit_sma_period
        self.stop_atr_mult = stop_atr_mult
        self.target_atr_mult = target_atr_mult
        self.max_hold_bars = max_hold_bars
        self._exit_sma_by_ts: dict[object, float] = {}

    def _check_columns(self, df: pl.DataFrame) -> None:
        missing = [c for c in self.REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{self.name}: input frame missing columns: {missing}")

    def generate_signals(self, df: pl.DataFrame) -> list[Signal]:
        self._check_columns(df)
        if df.height < self.trend_sma_period + 1:
            return []

        symbol = df["symbol"][0] if "symbol" in df.columns else "UNKNOWN"

        rolling_min = pl.col("close").rolling_min(self.low_lookback).alias("_roll_min")
        trend_sma = pl.col("close").rolling_mean(self.trend_sma_period).alias("_trend_sma")
        exit_sma = pl.col("close").rolling_mean(self.exit_sma_period).alias("_exit_sma")

        enriched = df.with_columns(rolling_min, trend_sma, exit_sma)

        for row in enriched.select("ts", "_exit_sma").iter_rows(named=True):
            if row["_exit_sma"] is not None:
                self._exit_sma_by_ts[row["ts"]] = float(row["_exit_sma"])

        prev_close = pl.col("close").shift(1)
        cond = (
            (pl.col("close") == pl.col("_roll_min"))
            & (pl.col("close") < prev_close)
            & (pl.col("close") > pl.col("_trend_sma"))
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
                        invalidation=(
                            f"close > {self.exit_sma_period}-SMA OR after {self.max_hold_bars} bars"
                        ),
                        regime_tag="daily_no_regime",
                        categorical_state="daily_no_regime",
                        expected_duration_bars=EXPECTED_DURATION_BARS,
                        notes=f"5d_low atr={atr:.3f}",
                    )
                )
            except ValueError:
                continue
        return signals

    def check_invalidation(self, bar: dict, open_position: dict) -> bool:
        if open_position.get("bars_held", 0) >= self.max_hold_bars:
            return True
        ts = bar.get("ts")
        exit_sma = self._exit_sma_by_ts.get(ts)
        close = float(bar.get("close", 0.0))
        if exit_sma is not None and close > exit_sma:
            return True
        return False
