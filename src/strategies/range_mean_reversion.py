"""Range Mean Reversion strategy.

See ``docs/strategies/range_mean_reversion.md`` for the full spec. This file
is the executable version. If they disagree, the spec wins and the code is
the bug.

Pipeline:

1. Caller pre-computes ATR, ADX, regimes, session VWAP on the bars frame.
2. ``generate_signals`` filters rows by regime gate, then evaluates the
   entry conditions at each surviving row.
3. For every accepted row T, a Signal is produced with:
     - entry  = next-bar (T+1) open price stand-in: use close[T] as the
       intended entry (the research backtester will fill at next-bar open).
     - stop   = entry ± max(0.5 * ATR[T], 0.25 * range_width[T])
     - target = session VWAP[T] (current session-anchored VWAP)
4. The research backtester takes it from there.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

import polars as pl

from .base import Signal, Strategy

LOOKBACK_BARS: Final = 20  # 20 × 5-min = 100-min range window
ENTRY_ZONE_FRACTION: Final = 0.15  # close must be within 15% of range edge
STOP_ATR_MULT: Final = 0.5
STOP_RANGE_MULT: Final = 0.25
MAX_STOP_PCT_OF_PRICE: Final = 0.005  # 0.5% absolute cap
MIN_REWARD_TO_RISK: Final = 0.8  # skip signals with R:R below this
EXPECTED_DURATION_BARS: Final = 12  # ~1 hour at 5-min bars


class RangeMeanReversion(Strategy):
    name = "range_mean_reversion"

    # Quant regimes where the strategy is allowed to fire: any range cell.
    allowed_quant_regimes = frozenset({"range_low", "range_medium"})

    # Categorical state gate.
    allowed_categorical_states = frozenset({"consolidating"})

    def __init__(
        self,
        *,
        lookback_bars: int = LOOKBACK_BARS,
        entry_zone_fraction: float = ENTRY_ZONE_FRACTION,
        stop_atr_mult: float = STOP_ATR_MULT,
        stop_range_mult: float = STOP_RANGE_MULT,
        max_stop_pct: float = MAX_STOP_PCT_OF_PRICE,
        min_reward_to_risk: float = MIN_REWARD_TO_RISK,
    ) -> None:
        if lookback_bars < 5:
            raise ValueError("lookback_bars must be >= 5")
        if not 0 < entry_zone_fraction < 0.5:
            raise ValueError("entry_zone_fraction must be in (0, 0.5)")
        self.lookback_bars = lookback_bars
        self.entry_zone_fraction = entry_zone_fraction
        self.stop_atr_mult = stop_atr_mult
        self.stop_range_mult = stop_range_mult
        self.max_stop_pct = max_stop_pct
        self.min_reward_to_risk = min_reward_to_risk

    # ------------------------------------------------------------------
    # Required input columns
    # ------------------------------------------------------------------
    REQUIRED_COLS = (
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "atr",
        "adx",
        "vwap",
        "quant_regime",
        "categorical_state",
    )

    def _check_columns(self, df: pl.DataFrame) -> None:
        missing = [c for c in self.REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"{self.name}: input frame missing columns: {missing}. "
                "Run features + regime classifier first."
            )

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------
    def generate_signals(self, df: pl.DataFrame) -> list[Signal]:
        self._check_columns(df)
        if df.height < self.lookback_bars + 1:
            return []

        symbol = df["symbol"][0] if "symbol" in df.columns else "UNKNOWN"

        # Add rolling structural columns. These use only past bars (no shift
        # of future data), so no-lookahead holds.
        w = self.lookback_bars
        enriched = df.with_columns(
            pl.col("high").rolling_max(window_size=w).alias("_range_high"),
            pl.col("low").rolling_min(window_size=w).alias("_range_low"),
        ).with_columns(
            (pl.col("_range_high") - pl.col("_range_low")).alias("_range_width"),
        )

        # Regime gate as a boolean column.
        regime_ok = (
            pl.col("quant_regime").is_in(list(self.allowed_quant_regimes))
            & pl.col("categorical_state").is_in(list(self.allowed_categorical_states))
            & pl.col("atr").is_not_null()
            & pl.col("vwap").is_not_null()
            & pl.col("_range_width").is_not_null()
            & (pl.col("_range_width") > 0)
        )

        # Entry zone: close within 15% of the lower/upper band.
        lower_threshold = pl.col("_range_low") + self.entry_zone_fraction * pl.col(
            "_range_width"
        )
        upper_threshold = pl.col("_range_high") - self.entry_zone_fraction * pl.col(
            "_range_width"
        )

        prev_close = pl.col("close").shift(1)

        long_condition = (
            regime_ok
            & (pl.col("close") <= lower_threshold)
            & (pl.col("close") > pl.col("open"))   # mildly green
            & (pl.col("close") > prev_close)        # intra-bar reversal
        )
        short_condition = (
            regime_ok
            & (pl.col("close") >= upper_threshold)
            & (pl.col("close") < pl.col("open"))
            & (pl.col("close") < prev_close)
        )

        enriched = enriched.with_columns(
            long_condition.alias("_long_sig"),
            short_condition.alias("_short_sig"),
        )

        signals: list[Signal] = []

        # Iterate over candidate rows only — vastly faster than all rows.
        candidates = enriched.filter(
            pl.col("_long_sig") | pl.col("_short_sig")
        )

        for row in candidates.iter_rows(named=True):
            side = "long" if row["_long_sig"] else "short"
            entry_price = float(row["close"])
            atr = float(row["atr"])
            rw = float(row["_range_width"])
            stop_dist = max(self.stop_atr_mult * atr, self.stop_range_mult * rw)

            # Hard cap on stop distance vs price.
            if stop_dist / entry_price > self.max_stop_pct:
                continue

            vwap_target = float(row["vwap"])

            if side == "long":
                stop = entry_price - stop_dist
                target = vwap_target
                if target <= entry_price:
                    continue  # VWAP is below entry — wrong side, skip
            else:
                stop = entry_price + stop_dist
                target = vwap_target
                if target >= entry_price:
                    continue

            # Build the signal — Signal.__post_init__ also validates ordering.
            try:
                sig = Signal(
                    ts=row["ts"],
                    symbol=symbol,
                    side=side,  # type: ignore[arg-type]
                    entry=entry_price,
                    stop=stop,
                    target=target,
                    invalidation=(
                        "categorical_state != consolidating, "
                        "or close breaks rolling range, "
                        "or ATR spikes > 2x mean"
                    ),
                    regime_tag=str(row["quant_regime"]),
                    categorical_state=str(row["categorical_state"]),
                    expected_duration_bars=EXPECTED_DURATION_BARS,
                    notes=f"range_width={rw:.4f} atr={atr:.4f}",
                )
            except ValueError:
                # Defensive — Signal validator caught a degenerate price config.
                continue

            if sig.reward_to_risk < self.min_reward_to_risk:
                continue

            signals.append(sig)

        return signals
