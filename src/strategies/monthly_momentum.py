"""Cross-sectional / time-series momentum — daily, long-only.

The most studied factor in equity markets after value. Long-run academic
evidence (Jegadeesh & Titman 1993, Asness/Moskowitz/Pedersen 2013) shows
positive 1-12 month momentum in nearly every developed market. The effect
is weaker on broad-index ETFs than on individual stocks but still positive
on average.

Single-asset version (what we run here): only hold the ETF when its trailing
N-month return is positive AND it's above its long-term moving average.
Exit when momentum turns or trend filter breaks.

Spec:

* **Universe:** broad ETFs (SPY, QQQ).
* **Entry signal at bar T:**
    - lookback_return(63 bars ≈ 3 months) > 2% AND
    - close[T] > 200-day SMA AND
    - no position currently open (since this is a "ride the trend" pattern)
* **Stop:** entry − 5 × ATR(14). Generous — momentum needs room.
* **Target:** entry × 1.25. Wide — exits are usually via invalidation.
* **Invalidation:** lookback_return turns negative OR close < 200-SMA.
"""

from __future__ import annotations

from typing import Final

import polars as pl

from .base import Signal, Strategy

LOOKBACK_BARS: Final = 63  # ~3 trading months
MIN_LOOKBACK_RETURN: Final = 0.02  # require ≥2% trailing return
TREND_SMA_PERIOD: Final = 200
STOP_ATR_MULT: Final = 5.0
TARGET_MULT: Final = 1.25
EXPECTED_DURATION_BARS: Final = 30


class MonthlyMomentum(Strategy):
    name = "monthly_momentum"

    allowed_quant_regimes: frozenset[str] = frozenset()
    allowed_categorical_states: frozenset[str] = frozenset()

    REQUIRED_COLS = ("ts", "open", "high", "low", "close", "atr")

    def __init__(
        self,
        *,
        lookback_bars: int = LOOKBACK_BARS,
        min_lookback_return: float = MIN_LOOKBACK_RETURN,
        trend_sma_period: int = TREND_SMA_PERIOD,
        stop_atr_mult: float = STOP_ATR_MULT,
    ) -> None:
        self.lookback_bars = lookback_bars
        self.min_lookback_return = min_lookback_return
        self.trend_sma_period = trend_sma_period
        self.stop_atr_mult = stop_atr_mult
        # cache lookback-return + trend-SMA per bar for the invalidation hook
        self._lookback_ret_by_ts: dict[object, float] = {}
        self._trend_sma_by_ts: dict[object, float] = {}

    def _check_columns(self, df: pl.DataFrame) -> None:
        missing = [c for c in self.REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{self.name}: input frame missing columns: {missing}")

    def generate_signals(self, df: pl.DataFrame) -> list[Signal]:
        self._check_columns(df)
        if df.height < max(self.lookback_bars, self.trend_sma_period) + 1:
            return []

        symbol = df["symbol"][0] if "symbol" in df.columns else "UNKNOWN"

        lookback_ret = (
            (pl.col("close") / pl.col("close").shift(self.lookback_bars) - 1.0)
            .alias("_lb_ret")
        )
        trend_sma = pl.col("close").rolling_mean(self.trend_sma_period).alias("_trend_sma")

        enriched = df.with_columns(lookback_ret, trend_sma)

        # Cache for invalidation hook
        for row in enriched.select("ts", "_lb_ret", "_trend_sma").iter_rows(named=True):
            if row["_lb_ret"] is not None:
                self._lookback_ret_by_ts[row["ts"]] = float(row["_lb_ret"])
            if row["_trend_sma"] is not None:
                self._trend_sma_by_ts[row["ts"]] = float(row["_trend_sma"])

        cond = (
            (pl.col("_lb_ret") > self.min_lookback_return)
            & (pl.col("close") > pl.col("_trend_sma"))
            & pl.col("atr").is_not_null()
            & pl.col("_lb_ret").is_not_null()
            & pl.col("_trend_sma").is_not_null()
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
                        invalidation="lookback return turns negative OR close < 200-SMA",
                        regime_tag="daily_no_regime",
                        categorical_state="daily_no_regime",
                        expected_duration_bars=EXPECTED_DURATION_BARS,
                        notes=f"lb_ret={row['_lb_ret']:.3f} atr={atr:.3f}",
                    )
                )
            except ValueError:
                continue
        return signals

    def check_invalidation(self, bar: dict, open_position: dict) -> bool:
        ts = bar.get("ts")
        lb_ret = self._lookback_ret_by_ts.get(ts)
        trend_sma = self._trend_sma_by_ts.get(ts)
        close = float(bar.get("close", 0.0))
        if lb_ret is not None and lb_ret < 0:
            return True
        if trend_sma is not None and close < trend_sma:
            return True
        return False
