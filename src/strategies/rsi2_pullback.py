"""Connors RSI(2) pullback — daily, long-only.

Reference: Larry Connors, "Short Term Trading Strategies That Work" (2008).
The original Connors RSI(2) buy-the-dip system: in an established uptrend,
look for an extreme short-term oversold reading, then ride the bounce.

This pattern has been one of the more durable retail-tradeable patterns on
liquid US ETFs since publication, though edge has thinned post-2015.
Still worth re-validating on recent data.

Spec:

* **Universe:** liquid ETFs.
* **Trend filter (gate):** close > 200-day SMA. Only buy dips in confirmed
  uptrends.
* **Entry signal at bar T:** RSI(2)[T] < 10. (Connors original uses < 5; we
  use < 10 to get more signals; tunable.)
* **Stop:** entry − 3 × ATR(14).
* **Target:** entry + 4 × ATR(14). Moderate R:R ~1.3; usually exited by
  invalidation as the bounce develops over a few days.
* **Invalidation:** RSI(2) > 70 OR close > 5-day SMA (the bounce target)
  OR after 8 bars.

RSI(2) is computed using the Wilder smoothing convention (alpha = 1/period).
"""

from __future__ import annotations

from typing import Final

import polars as pl

from .base import Signal, Strategy

RSI_PERIOD: Final = 2
RSI_OVERSOLD: Final = 10.0
RSI_OVERBOUGHT: Final = 70.0
TREND_SMA_PERIOD: Final = 200
EXIT_SMA_PERIOD: Final = 5
STOP_ATR_MULT: Final = 3.0
TARGET_ATR_MULT: Final = 4.0
MAX_HOLD_BARS: Final = 8
EXPECTED_DURATION_BARS: Final = 4


def _rsi_expr(period: int) -> pl.Expr:
    """Wilder-smoothed RSI(N) expression on the 'close' column."""
    delta = pl.col("close").diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    # Wilder smoothing = EMA with alpha = 1/N. Polars ewm_mean with alpha.
    avg_gain = gain.ewm_mean(alpha=1.0 / period, adjust=False)
    avg_loss = loss.ewm_mean(alpha=1.0 / period, adjust=False)
    rs = avg_gain / avg_loss
    return (100.0 - 100.0 / (1.0 + rs)).alias("_rsi")


class RSI2Pullback(Strategy):
    name = "rsi2_pullback"

    allowed_quant_regimes: frozenset[str] = frozenset()
    allowed_categorical_states: frozenset[str] = frozenset()

    REQUIRED_COLS = ("ts", "open", "high", "low", "close", "atr")

    def __init__(
        self,
        *,
        rsi_period: int = RSI_PERIOD,
        rsi_oversold: float = RSI_OVERSOLD,
        rsi_overbought: float = RSI_OVERBOUGHT,
        trend_sma_period: int = TREND_SMA_PERIOD,
        exit_sma_period: int = EXIT_SMA_PERIOD,
        stop_atr_mult: float = STOP_ATR_MULT,
        target_atr_mult: float = TARGET_ATR_MULT,
        max_hold_bars: int = MAX_HOLD_BARS,
    ) -> None:
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.trend_sma_period = trend_sma_period
        self.exit_sma_period = exit_sma_period
        self.stop_atr_mult = stop_atr_mult
        self.target_atr_mult = target_atr_mult
        self.max_hold_bars = max_hold_bars
        self._rsi_by_ts: dict[object, float] = {}
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

        trend_sma = pl.col("close").rolling_mean(self.trend_sma_period).alias("_trend_sma")
        exit_sma = pl.col("close").rolling_mean(self.exit_sma_period).alias("_exit_sma")

        enriched = df.with_columns(
            _rsi_expr(self.rsi_period),
            trend_sma,
            exit_sma,
        )

        # Cache RSI + exit SMA per bar for the invalidation hook.
        for row in enriched.select("ts", "_rsi", "_exit_sma").iter_rows(named=True):
            if row["_rsi"] is not None:
                self._rsi_by_ts[row["ts"]] = float(row["_rsi"])
            if row["_exit_sma"] is not None:
                self._exit_sma_by_ts[row["ts"]] = float(row["_exit_sma"])

        cond = (
            (pl.col("_rsi") < self.rsi_oversold)
            & (pl.col("close") > pl.col("_trend_sma"))
            & pl.col("atr").is_not_null()
            & pl.col("_trend_sma").is_not_null()
            & pl.col("_rsi").is_not_null()
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
                            f"RSI({self.rsi_period}) > {self.rsi_overbought} OR "
                            f"close > {self.exit_sma_period}-SMA OR after {self.max_hold_bars} bars"
                        ),
                        regime_tag="daily_no_regime",
                        categorical_state="daily_no_regime",
                        expected_duration_bars=EXPECTED_DURATION_BARS,
                        notes=f"rsi={row['_rsi']:.2f} atr={atr:.3f}",
                    )
                )
            except ValueError:
                continue
        return signals

    def check_invalidation(self, bar: dict, open_position: dict) -> bool:
        bars_held = open_position.get("bars_held", 0)
        if bars_held >= self.max_hold_bars:
            return True
        ts = bar.get("ts")
        rsi = self._rsi_by_ts.get(ts)
        exit_sma = self._exit_sma_by_ts.get(ts)
        close = float(bar.get("close", 0.0))
        if rsi is not None and rsi > self.rsi_overbought:
            return True
        if exit_sma is not None and close > exit_sma:
            return True
        return False
