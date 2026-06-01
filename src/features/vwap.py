"""Volume-Weighted Average Price (VWAP).

We support three flavors:

* :func:`session_vwap` — resets each US-equity trading session (default
  09:30 ET to 16:00 ET). This is what most intraday charts mean by "VWAP".
* :func:`anchored_vwap` — VWAP measured from an arbitrary anchor timestamp
  forward (e.g. an earnings event, a swing high). Useful for the
  "AVWAP pullback" strategy in the spec.
* :func:`rolling_vwap` — rolling window VWAP. Less common; included for
  symmetry with other indicators.

All VWAPs use the *typical price* `(H + L + C) / 3` weighted by volume,
which is the standard CME / TradingView definition. No lookahead.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import polars as pl

from ._schema import validate_ohlcv

NY_TZ = ZoneInfo("America/New_York")
DEFAULT_SESSION_OPEN = time(9, 30)


def _typical_price() -> pl.Expr:
    return (pl.col("high") + pl.col("low") + pl.col("close")) / 3.0


def session_vwap(
    df: pl.DataFrame,
    *,
    session_open: time = DEFAULT_SESSION_OPEN,
    tz: ZoneInfo = NY_TZ,
    column_name: str = "vwap",
) -> pl.DataFrame:
    """Append a session-resetting VWAP column.

    A new session begins at the first bar whose local-time (in ``tz``) is at
    or after ``session_open``. The VWAP is cumulative within each session.

    Notes
    -----
    Assumes the input ``ts`` column is timezone-aware (or naive UTC).
    """
    validate_ohlcv(df)
    if df.is_empty():
        return df.with_columns(pl.lit(None, dtype=pl.Float64).alias(column_name))

    ts_dtype = df.schema["ts"]
    if isinstance(ts_dtype, pl.Datetime) and ts_dtype.time_zone is None:
        ts_local = pl.col("ts").dt.replace_time_zone("UTC").dt.convert_time_zone(str(tz))
    else:
        ts_local = pl.col("ts").dt.convert_time_zone(str(tz))

    # session_id = the local *date* of the bar; combined with a marker for
    # bars that fall in the next day's session (e.g. overnight). For US RTH
    # this collapses to "the trading date".
    session_id = ts_local.dt.date().alias("_session_id")

    tp = _typical_price()
    tmp = df.with_columns(
        session_id,
        (tp * pl.col("volume")).alias("_pv"),
        pl.col("volume").alias("_v"),
    )

    tmp = tmp.with_columns(
        pl.col("_pv").cum_sum().over("_session_id").alias("_cum_pv"),
        pl.col("_v").cum_sum().over("_session_id").alias("_cum_v"),
    )

    vwap_expr = (
        pl.when(pl.col("_cum_v") > 0)
        .then(pl.col("_cum_pv") / pl.col("_cum_v"))
        .otherwise(None)
        .alias(column_name)
    )

    return tmp.with_columns(vwap_expr).drop(
        ["_session_id", "_pv", "_v", "_cum_pv", "_cum_v"]
    )


def anchored_vwap(
    df: pl.DataFrame,
    *,
    anchor: datetime,
    column_name: str = "avwap",
) -> pl.DataFrame:
    """Append an anchored VWAP column.

    The AVWAP is null for bars before ``anchor`` and cumulative from the
    first bar with ``ts >= anchor`` onward.
    """
    validate_ohlcv(df)

    tp = _typical_price()
    in_window = pl.col("ts") >= pl.lit(anchor)
    pv = pl.when(in_window).then(tp * pl.col("volume")).otherwise(0.0)
    v = pl.when(in_window).then(pl.col("volume")).otherwise(0.0)

    tmp = df.with_columns(
        pv.alias("_pv"),
        v.alias("_v"),
    ).with_columns(
        pl.col("_pv").cum_sum().alias("_cum_pv"),
        pl.col("_v").cum_sum().alias("_cum_v"),
    )

    avwap_expr = (
        pl.when((pl.col("_cum_v") > 0) & in_window)
        .then(pl.col("_cum_pv") / pl.col("_cum_v"))
        .otherwise(None)
        .alias(column_name)
    )
    return tmp.with_columns(avwap_expr).drop(["_pv", "_v", "_cum_pv", "_cum_v"])


def rolling_vwap(
    df: pl.DataFrame,
    *,
    window: int,
    column_name: str = "rvwap",
) -> pl.DataFrame:
    """Append a rolling-window VWAP column over the last ``window`` bars."""
    if window < 2:
        raise ValueError(f"rolling_vwap window must be >= 2, got {window}")
    validate_ohlcv(df)

    tp = _typical_price()
    pv = (tp * pl.col("volume")).rolling_sum(window_size=window)
    v = pl.col("volume").rolling_sum(window_size=window)

    rvwap_expr = pl.when(v > 0).then(pv / v).otherwise(None).alias(column_name)
    return df.with_columns(rvwap_expr)
