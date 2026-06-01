"""Tests for the data quality checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from src.data.validation.data_quality_checks import raise_if_failed, validate


def _good_bars(n: int = 100) -> pl.DataFrame:
    start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    return pl.DataFrame(
        {
            "ts": [start + timedelta(minutes=5 * i) for i in range(n)],
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.5] * n,
            "volume": [1000.0] * n,
        }
    )


class TestValidate:
    def test_good_bars_pass(self) -> None:
        report = validate(_good_bars(), symbol="SPY", timeframe="5Min")
        assert report.passed
        assert report.duplicates == 0
        assert report.impossible_ohlc == 0

    def test_detects_duplicates(self) -> None:
        bars = _good_bars(10)
        dup = pl.concat([bars, bars.head(3)]).sort("ts")
        report = validate(dup, symbol="SPY", timeframe="5Min")
        assert report.duplicates == 3
        assert not report.passed

    def test_detects_impossible_ohlc(self) -> None:
        bars = _good_bars(10)
        # Make one row have high < low.
        bars = bars.with_columns(
            pl.when(pl.col("ts") == bars["ts"][5])
            .then(95.0)
            .otherwise(pl.col("high"))
            .alias("high")
        )
        report = validate(bars, symbol="SPY", timeframe="5Min")
        assert report.impossible_ohlc >= 1
        assert not report.passed

    def test_detects_out_of_order(self) -> None:
        bars = _good_bars(10).reverse()
        report = validate(bars, symbol="SPY", timeframe="5Min")
        assert report.out_of_order > 0

    def test_raise_if_failed(self) -> None:
        bars = pl.concat([_good_bars(5), _good_bars(5).head(2)]).sort("ts")
        report = validate(bars, symbol="SPY", timeframe="5Min")
        with pytest.raises(RuntimeError):
            raise_if_failed(report)

    def test_empty_passes(self) -> None:
        report = validate(pl.DataFrame({"ts": [], "open": [], "high": [], "low": [], "close": [], "volume": []}), symbol="SPY", timeframe="5Min")
        assert report.passed
        assert report.n_bars == 0
