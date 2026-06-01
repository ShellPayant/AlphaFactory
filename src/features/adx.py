"""Average Directional Index (ADX) — trend strength measure.

ADX answers "how strong is the trend?" regardless of direction. We follow
Welles Wilder's original formulation:

1. +DM / -DM (directional movements):
    +DM_T = max(H_T - H_{T-1}, 0) if (H_T - H_{T-1}) > (L_{T-1} - L_T) else 0
    -DM_T = max(L_{T-1} - L_T, 0) if (L_{T-1} - L_T) > (H_T - H_{T-1}) else 0

2. Wilder-smooth TR, +DM, -DM over ``period``.
3. +DI = 100 * smoothed(+DM) / smoothed(TR)
   -DI = 100 * smoothed(-DM) / smoothed(TR)
4. DX = 100 * |+DI - -DI| / (+DI + -DI)
5. ADX = Wilder-smoothed DX over ``period``.

Reading guide we'll use in `regime_classifier.py`:
  ADX < 20–25  → range / no trend
  ADX 25–40    → weak / developing trend
  ADX > 40     → strong trend

No lookahead: ADX at bar T depends only on bars ``<= T``.
"""

from __future__ import annotations

import polars as pl

from ._schema import validate_ohlcv
from .atr import true_range


def adx(
    df: pl.DataFrame,
    *,
    period: int = 14,
    column_prefix: str = "",
) -> pl.DataFrame:
    """Append ``adx``, ``plus_di``, ``minus_di`` columns to ``df``.

    Parameters
    ----------
    df : pl.DataFrame
        OHLCV frame, sorted ascending by ts.
    period : int, default 14
        Wilder smoothing period.
    column_prefix : str, default ""
        Optional prefix for the output columns (e.g. ``"h1_"``).

    Returns
    -------
    pl.DataFrame
        ``df`` with three new columns appended. Roughly the first
        ``2 * period`` rows are null (one period to seed DI, another to seed
        ADX).
    """
    if period < 2:
        raise ValueError(f"ADX period must be >= 2, got {period}")

    validate_ohlcv(df)

    high = pl.col("high")
    low = pl.col("low")

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = (
        pl.when((up_move > down_move) & (up_move > 0))
        .then(up_move)
        .otherwise(0.0)
    )
    minus_dm = (
        pl.when((down_move > up_move) & (down_move > 0))
        .then(down_move)
        .otherwise(0.0)
    )

    tr = true_range(df)

    alpha = 1.0 / period
    tmp = df.with_columns(
        plus_dm.alias("_plus_dm"),
        minus_dm.alias("_minus_dm"),
        tr.alias("_tr"),
    ).with_columns(
        pl.col("_plus_dm")
        .ewm_mean(alpha=alpha, adjust=False, min_periods=period)
        .alias("_sm_plus_dm"),
        pl.col("_minus_dm")
        .ewm_mean(alpha=alpha, adjust=False, min_periods=period)
        .alias("_sm_minus_dm"),
        pl.col("_tr")
        .ewm_mean(alpha=alpha, adjust=False, min_periods=period)
        .alias("_sm_tr"),
    )

    tmp = tmp.with_columns(
        (100.0 * pl.col("_sm_plus_dm") / pl.col("_sm_tr")).alias("_plus_di"),
        (100.0 * pl.col("_sm_minus_dm") / pl.col("_sm_tr")).alias("_minus_di"),
    )

    di_sum = pl.col("_plus_di") + pl.col("_minus_di")
    di_diff = (pl.col("_plus_di") - pl.col("_minus_di")).abs()
    dx_expr = pl.when(di_sum > 0).then(100.0 * di_diff / di_sum).otherwise(0.0)

    tmp = tmp.with_columns(dx_expr.alias("_dx"))

    tmp = tmp.with_columns(
        pl.col("_dx")
        .ewm_mean(alpha=alpha, adjust=False, min_periods=period * 2)
        .alias("_adx"),
    )

    p = column_prefix
    return tmp.select(
        *[pl.col(c) for c in df.columns],
        pl.col("_plus_di").alias(f"{p}plus_di"),
        pl.col("_minus_di").alias(f"{p}minus_di"),
        pl.col("_adx").alias(f"{p}adx"),
    )
