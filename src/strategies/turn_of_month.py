"""Turn-of-Month seasonality — daily, long-only.

Reference: Ariel (1987), Lakonishok & Smidt (1988), extensively re-validated
since. Equity returns concentrate disproportionately around the month boundary
— roughly the last 2 trading days of one month + the first 3 of the next.

The effect has weakened post-2010 but remains positive in expectation across
liquid US equity ETFs. It's a textbook calendar anomaly, well worth re-validating
on our recent data sample.

Spec:

* **Universe:** broad US equity ETFs (SPY, QQQ, IWM).
* **Entry signal at bar T:** T is the 2nd-to-last trading day of the month
  (the "ToM-2" day) — go long at open of T+1.
* **Stop:** entry − 4 × ATR(14). Wide enough not to interfere with the
  seasonal hold; this exists for catastrophe protection.
* **Target:** entry + 10 × ATR(14). Wide; usually exited by invalidation.
* **Invalidation (time-based exit):** close after 5 bars — exits around the
  3rd trading day of the new month.

Implementation note: we identify "ToM-2" by looking 2 trading days ahead and
checking that the *next-next* bar belongs to a different calendar month. This
uses *only* the calendar (no future prices), so it's no-lookahead.
"""

from __future__ import annotations

from typing import Final

import polars as pl

from .base import Signal, Strategy

STOP_ATR_MULT: Final = 4.0
TARGET_ATR_MULT: Final = 10.0
MAX_HOLD_BARS: Final = 5
EXPECTED_DURATION_BARS: Final = 5


class TurnOfMonth(Strategy):
    name = "turn_of_month"

    allowed_quant_regimes: frozenset[str] = frozenset()
    allowed_categorical_states: frozenset[str] = frozenset()

    REQUIRED_COLS = ("ts", "open", "high", "low", "close", "atr")

    def __init__(
        self,
        *,
        stop_atr_mult: float = STOP_ATR_MULT,
        target_atr_mult: float = TARGET_ATR_MULT,
        max_hold_bars: int = MAX_HOLD_BARS,
    ) -> None:
        self.stop_atr_mult = stop_atr_mult
        self.target_atr_mult = target_atr_mult
        self.max_hold_bars = max_hold_bars

    def _check_columns(self, df: pl.DataFrame) -> None:
        missing = [c for c in self.REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{self.name}: input frame missing columns: {missing}")

    def generate_signals(self, df: pl.DataFrame) -> list[Signal]:
        self._check_columns(df)
        if df.height < 25:
            return []

        symbol = df["symbol"][0] if "symbol" in df.columns else "UNKNOWN"

        # Identify "ToM-2" day: the bar where (bar at T+2) is in a different
        # calendar month from bar at T+1 (the bar AFTER next is in next month).
        # We use the bar's own ts (date level). NO future price data is used —
        # only the trading calendar implied by the bar sequence.
        ts_month = pl.col("ts").dt.month()
        is_tom_minus_2 = (
            ts_month.shift(-2) != ts_month
        ) & (
            ts_month.shift(-1) == ts_month
        )

        enriched = df.with_columns(
            is_tom_minus_2.alias("_is_tom"),
        )

        cond = pl.col("_is_tom") & pl.col("atr").is_not_null()
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
                        invalidation=f"close after {self.max_hold_bars} bars (T+3 of new month)",
                        regime_tag="daily_no_regime",
                        categorical_state="daily_no_regime",
                        expected_duration_bars=EXPECTED_DURATION_BARS,
                        notes=f"month_end_seasonal atr={atr:.3f}",
                    )
                )
            except ValueError:
                continue
        return signals

    def check_invalidation(self, bar: dict, open_position: dict) -> bool:
        return open_position.get("bars_held", 0) >= self.max_hold_bars
