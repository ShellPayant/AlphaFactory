"""Average True Range (ATR) — volatility measure.

True Range for bar T is:
    TR_T = max( H_T - L_T, |H_T - C_{T-1}|, |L_T - C_{T-1}|)

ATR is a smoothed average of TR. We support two smoothings:

* ``"wilder"`` — the original Welles Wilder recursive smoothing
  (equivalent to an EMA with ``alpha = 1/n``). This is what most charting
  platforms call "ATR" by default.
* ``"sma"`` — a simple moving average. Easier to reason about for tests.

No lookahead: ATR at bar T depends only on bars ``<= T``. The first
``n-1`` bars produce nulls.
"""

from __future__ import annotations

from typing import Literal

import polars as pl

from ._schema import validate_ohlcv

ATRSmoothing = Literal["wilder", "sma"]


def true_range(df: pl.DataFrame) -> pl.Series:
    """Compute per-bar True Range.

    Returns a Series aligned to ``df`` rows. The first bar's TR is
    ``high - low`` (no prior close available).
    """
    validate_ohlcv(df)
    prev_close = pl.col("close").shift(1)
    tr_expr = pl.max_horizontal(
        pl.col("high") - pl.col("low"),
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs(),
    )
    # On the first row prev_close is null → max_horizontal yields null. Fall
    # back to the high-low range so we never emit a null TR.
    tr = df.select(
        pl.coalesce(tr_expr, pl.col("high") - pl.col("low")).alias("tr")
    )["tr"]
    return tr


def atr(
    df: pl.DataFrame,
    *,
    period: int = 14,
    smoothing: ATRSmoothing = "wilder",
    column_name: str = "atr",
) -> pl.DataFrame:
    """Append an ATR column to ``df``.

    Parameters
    ----------
    df : pl.DataFrame
        OHLCV frame, sorted ascending by ts (see ``validate_ohlcv``).
    period : int, default 14
        Lookback period. Must be >= 2.
    smoothing : {"wilder", "sma"}, default "wilder"
        Smoothing method.
    column_name : str, default "atr"
        Name of the output column.

    Returns
    -------
    pl.DataFrame
        ``df`` with one new column appended. The first ``period - 1`` rows
        will be null (no full lookback yet).
    """
    if period < 2:
        raise ValueError(f"ATR period must be >= 2, got {period}")

    tr = true_range(df)

    if smoothing == "sma":
        atr_series = tr.rolling_mean(window_size=period)
    elif smoothing == "wilder":
        # Wilder smoothing = EMA with alpha = 1/period, seeded by the SMA of
        # the first `period` TR values.
        atr_series = tr.ewm_mean(alpha=1.0 / period, adjust=False, min_periods=period)
    else:  # pragma: no cover — exhausted by Literal
        raise ValueError(f"Unknown ATR smoothing: {smoothing}")

    return df.with_columns(atr_series.alias(column_name))
