"""Tests for the Range Mean Reversion strategy.

Two things matter here:
1. The strategy actually fires when the regime gate says it should.
2. The strategy does NOT fire outside the gate (no signals during trends).
3. Signal generation has no lookahead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from src.features.adx import adx
from src.features.atr import atr
from src.features.vwap import session_vwap
from src.regimes.regime_classifier import classify_regimes
from src.strategies.range_mean_reversion import RangeMeanReversion


def _enrich(bars: pl.DataFrame) -> pl.DataFrame:
    """Apply the full feature + regime pipeline that the strategy expects."""
    bars = atr(bars, period=14)
    bars = adx(bars, period=14)
    bars = session_vwap(bars)
    bars = classify_regimes(bars)
    return bars


def _range_bars(n: int = 300, seed: int = 0) -> pl.DataFrame:
    """Tight range around 100 with small noise — should be consolidating."""
    rng = np.random.default_rng(seed)
    start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    closes = [100.0 + float(rng.normal(0, 0.2)) for _ in range(n)]
    opens = [closes[0]] + closes[:-1]
    return pl.DataFrame(
        {
            "ts": [start + timedelta(minutes=5 * i) for i in range(n)],
            "open": opens,
            "high": [max(o, c) + 0.2 for o, c in zip(opens, closes)],
            "low": [min(o, c) - 0.2 for o, c in zip(opens, closes)],
            "close": closes,
            "volume": [10_000.0] * n,
            "symbol": ["SPY"] * n,
        }
    )


def _trend_bars(n: int = 300) -> pl.DataFrame:
    rng = np.random.default_rng(42)
    start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    closes = [100.0 + 0.3 * i + float(rng.normal(0, 0.05)) for i in range(n)]
    opens = [closes[0]] + closes[:-1]
    return pl.DataFrame(
        {
            "ts": [start + timedelta(minutes=5 * i) for i in range(n)],
            "open": opens,
            "high": [max(o, c) + 0.1 for o, c in zip(opens, closes)],
            "low": [min(o, c) - 0.1 for o, c in zip(opens, closes)],
            "close": closes,
            "volume": [10_000.0] * n,
            "symbol": ["SPY"] * n,
        }
    )


class TestRangeMR:
    def test_fires_on_range(self) -> None:
        bars = _enrich(_range_bars(300))
        sigs = RangeMeanReversion().generate_signals(bars)
        # On a tight range we expect at least some signals over 300 bars.
        # If this fails repeatedly across seeds, our entry zone may be too tight.
        assert len(sigs) >= 1

    def test_no_signals_on_trend(self) -> None:
        bars = _enrich(_trend_bars(300))
        sigs = RangeMeanReversion().generate_signals(bars)
        # A clean uptrend should not pass the consolidating gate. Allow up to
        # a handful in case the warm-up window is misclassified.
        assert len(sigs) <= 3

    def test_signal_structure_valid(self) -> None:
        bars = _enrich(_range_bars(300))
        sigs = RangeMeanReversion().generate_signals(bars)
        for s in sigs:
            # Long: stop < entry < target. Short: target < entry < stop.
            if s.side == "long":
                assert s.stop < s.entry < s.target
            else:
                assert s.target < s.entry < s.stop
            assert s.symbol == "SPY"
            assert s.regime_tag in {"range_low", "range_medium"}
            assert s.categorical_state == "consolidating"

    def test_no_lookahead(self) -> None:
        """Signals at bar T must not change when bars > T are added later."""
        bars = _enrich(_range_bars(400))
        full_sigs = RangeMeanReversion().generate_signals(bars)
        full_ts_set = {s.ts for s in full_sigs}

        # Truncate to 300 bars, regenerate. Every signal produced on the
        # truncated frame must also appear in the full-frame signals.
        truncated = _enrich(_range_bars(400).head(300))
        trunc_sigs = RangeMeanReversion().generate_signals(truncated)

        for s in trunc_sigs:
            assert s.ts in full_ts_set, (
                f"Signal at {s.ts} on truncated data not in full data — lookahead leak"
            )

    def test_missing_columns_raises(self) -> None:
        bars = _range_bars(100)  # no enrichment
        with pytest.raises(ValueError, match="missing columns"):
            RangeMeanReversion().generate_signals(bars)

    def test_max_stop_pct_filter(self) -> None:
        """A very wide stop should cause the signal to be dropped."""
        bars = _enrich(_range_bars(300))
        # Force absurdly low max_stop_pct so every signal is rejected.
        strat = RangeMeanReversion(max_stop_pct=1e-9)
        sigs = strat.generate_signals(bars)
        assert len(sigs) == 0
