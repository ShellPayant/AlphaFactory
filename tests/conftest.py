"""Shared fixtures and synthetic-data helpers for the test suite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest


def _make_bars(
    closes: list[float],
    *,
    start: datetime | None = None,
    freq_minutes: int = 5,
    volume: float = 1_000.0,
    spread: float = 0.5,
) -> pl.DataFrame:
    """Build a deterministic OHLCV frame from a list of closes.

    Each bar's high/low are placed +/- ``spread`` around the close, and the
    open is the prior close (so the bars are 'connected'). This is enough
    structure for indicator tests without dragging in random data.
    """
    if start is None:
        start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)  # 09:30 ET
    n = len(closes)
    ts = [start + timedelta(minutes=freq_minutes * i) for i in range(n)]
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) + spread for o, c in zip(opens, closes)]
    lows = [min(o, c) - spread for o, c in zip(opens, closes)]
    return pl.DataFrame(
        {
            "ts": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [volume] * n,
        }
    )


@pytest.fixture
def make_bars():
    """Factory fixture for building OHLCV frames in tests."""
    return _make_bars


@pytest.fixture
def trending_bars() -> pl.DataFrame:
    """200 bars of a clean uptrend: close = 100 + 0.5*i + tiny noise."""
    rng = np.random.default_rng(seed=42)
    closes = [100.0 + 0.5 * i + float(rng.normal(0, 0.05)) for i in range(200)]
    return _make_bars(closes)


@pytest.fixture
def ranging_bars() -> pl.DataFrame:
    """200 bars oscillating tightly in [99, 101]."""
    rng = np.random.default_rng(seed=7)
    closes = [100.0 + float(rng.normal(0, 0.3)) for _ in range(200)]
    return _make_bars(closes)


@pytest.fixture
def chaotic_bars() -> pl.DataFrame:
    """200 bars with growing volatility and direction flips."""
    rng = np.random.default_rng(seed=13)
    closes: list[float] = [100.0]
    for i in range(199):
        # Volatility grows linearly with bar index; sign flips often.
        step = float(rng.normal(0, 0.1 + i * 0.02)) * (1 if rng.random() > 0.5 else -1)
        closes.append(closes[-1] + step)
    return _make_bars(closes)
