"""Shared OHLCV schema helpers for the features module.

Every indicator in this package expects a Polars DataFrame with at least the
columns defined in `OHLCV_COLUMNS`, sorted ascending by `ts`, in UTC.

Keeping the schema contract in one place lets us fail fast with a clear error
instead of producing wrong indicator values silently.
"""

from __future__ import annotations

import polars as pl

OHLCV_COLUMNS: tuple[str, ...] = ("ts", "open", "high", "low", "close", "volume")


def validate_ohlcv(df: pl.DataFrame, *, require_sorted: bool = True) -> None:
    """Raise if ``df`` is not a well-formed OHLCV frame.

    Checks performed:

    * Required columns present.
    * No nulls in the OHLC columns.
    * ``high >= low`` on every row (impossible-bar guard).
    * ``ts`` is monotonically increasing (when ``require_sorted=True``).

    Volume is allowed to be zero (e.g. illiquid pre-market bars) but not null.
    """
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV frame missing columns: {missing}")

    for col in ("open", "high", "low", "close", "volume"):
        if df[col].null_count() > 0:
            raise ValueError(f"OHLCV frame has nulls in column '{col}'")

    bad = df.filter(pl.col("high") < pl.col("low")).height
    if bad > 0:
        raise ValueError(f"OHLCV frame has {bad} rows where high < low")

    if require_sorted and df.height > 1:
        ts = df["ts"]
        diffs = ts.diff().drop_nulls()
        # Polars Duration → can compare to 0
        if (diffs.to_physical() < 0).any():
            raise ValueError("OHLCV frame is not sorted by ts ascending")
