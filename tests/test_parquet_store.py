"""Round-trip tests for the Parquet bar store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

from src.data.storage.duckdb_store import describe_store, query
from src.data.storage.parquet_store import list_months, read_bars, write_bars


def _make_bars(symbol: str, n: int = 100, start_year: int = 2024) -> pl.DataFrame:
    start = datetime(start_year, 1, 2, 14, 30, tzinfo=timezone.utc)
    ts = [start + timedelta(minutes=5 * i) for i in range(n)]
    return pl.DataFrame(
        {
            "ts": ts,
            "open": [100.0 + i * 0.1 for i in range(n)],
            "high": [100.5 + i * 0.1 for i in range(n)],
            "low": [99.5 + i * 0.1 for i in range(n)],
            "close": [100.0 + i * 0.1 for i in range(n)],
            "volume": [1000.0] * n,
            "symbol": [symbol] * n,
        }
    )


class TestParquetStore:
    def test_write_then_read_roundtrip(self, tmp_path: Path) -> None:
        bars = _make_bars("SPY", n=200)
        write_bars(bars, root=tmp_path, symbol="SPY", timeframe="5Min")
        back = read_bars(root=tmp_path, symbol="SPY", timeframe="5Min")
        assert back.height == bars.height
        assert back["close"][0] == pytest.approx(bars["close"][0])

    def test_writes_monthly_partitions(self, tmp_path: Path) -> None:
        # 100 bars × 5 min ≈ 8 hours → all in Jan 2024.
        bars = _make_bars("SPY", n=100)
        write_bars(bars, root=tmp_path, symbol="SPY", timeframe="5Min")
        months = list_months(tmp_path, "SPY", "5Min")
        assert months == ["2024-01"]

    def test_dedup_on_re_ingest(self, tmp_path: Path) -> None:
        bars = _make_bars("SPY", n=100)
        write_bars(bars, root=tmp_path, symbol="SPY", timeframe="5Min")
        # Re-ingest overlapping data — should NOT double-count.
        write_bars(bars, root=tmp_path, symbol="SPY", timeframe="5Min")
        back = read_bars(root=tmp_path, symbol="SPY", timeframe="5Min")
        assert back.height == 100

    def test_date_filter_applied(self, tmp_path: Path) -> None:
        bars = _make_bars("SPY", n=500)
        write_bars(bars, root=tmp_path, symbol="SPY", timeframe="5Min")
        back = read_bars(
            root=tmp_path,
            symbol="SPY",
            timeframe="5Min",
            start="2024-01-02",
            end="2024-01-03",
        )
        assert back.height > 0
        assert back.height < bars.height

    def test_empty_read_returns_empty(self, tmp_path: Path) -> None:
        back = read_bars(root=tmp_path, symbol="NOPE", timeframe="5Min")
        assert back.is_empty()


class TestDuckDBStore:
    def test_describe_store(self, tmp_path: Path) -> None:
        write_bars(
            _make_bars("SPY", n=100),
            root=tmp_path, symbol="SPY", timeframe="5Min",
        )
        write_bars(
            _make_bars("QQQ", n=50),
            root=tmp_path, symbol="QQQ", timeframe="5Min",
        )
        inv = describe_store(tmp_path)
        assert inv.height == 2
        spy_row = inv.filter(pl.col("symbol") == "SPY")
        assert int(spy_row["n_bars"][0]) == 100

    def test_query_macro(self, tmp_path: Path) -> None:
        write_bars(
            _make_bars("SPY", n=100),
            root=tmp_path, symbol="SPY", timeframe="5Min",
        )
        out = query(
            "SELECT COUNT(*) AS n FROM bars('SPY', '5Min')",
            root=tmp_path,
        )
        assert int(out["n"][0]) == 100
