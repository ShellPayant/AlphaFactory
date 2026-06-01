"""Macro volatility regime via GARCH(1,1) on daily returns.

This module is the **vol component** of architecture roadmap item #4
("macro regime overlay"). It does ONE narrow job:

  Given a stream of bars (intraday or daily) for a broad-market proxy
  (typically SPY), it produces a per-day tag in {"low_vol", "normal_vol",
  "high_vol"} based on GARCH(1,1) conditional volatility.

**This is NOT a trading signal.** It is an environment tag that downstream
strategies can choose to gate on (e.g. "intraday momentum only trades in
normal_vol or high_vol days"). See ``memory/project_ml_dl_decision.md`` —
GARCH is the one volatility model we keep precisely because it's a classical
statistical model that captures real vol-clustering without the overfit
risk of LSTM/Transformer/DeepAR variants.

Method:

1. Resample input bars to daily close-to-close log returns (if intraday).
2. Fit a single GARCH(1,1) model on the full available history.
   We accept a tiny bit of in-sample bias for v1 — the regime tag is
   used as a *qualifier* for strategies that are themselves validated
   walk-forward. A future v2 may switch to walk-forward GARCH refit
   (one refit per quarter) but the cost/benefit isn't worth it now.
3. Extract the daily conditional volatility series.
4. Compute an EXPANDING percentile rank of conditional vol (only past
   observations through day T contribute) — this avoids lookahead in
   the regime-cutoff decision.
5. Tag each day based on rank:
       rank < low_pct                  → "low_vol"
       low_pct ≤ rank < high_pct       → "normal_vol"
       rank ≥ high_pct                 → "high_vol"

The first ``min_warmup_days`` days are tagged ``None`` (insufficient
history to rank).

Typical use::

    from src.regimes.macro_regime import classify_volatility_regime
    daily = classify_volatility_regime(spy_5min_bars)
    # join `daily` back to intraday bars on date if you want a per-bar tag

The output is **daily-resolution** — caller is responsible for joining
it back to intraday bars on calendar date if needed (we do NOT do that
here because the join semantics depend on whether the caller wants the
regime as-of session open or as-of prior close).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_t
from typing import Literal

import numpy as np
import polars as pl
from loguru import logger

VolRegime = Literal["low_vol", "normal_vol", "high_vol"]


@dataclass(frozen=True)
class MacroRegimeConfig:
    """Tunable thresholds for the GARCH(1,1) volatility regime tagger."""

    # --- Percentile cutoffs on expanding rank of cond vol ---
    low_pct: float = 1.0 / 3.0
    high_pct: float = 2.0 / 3.0

    # --- Warmup ---
    # Need enough days to (a) fit GARCH stably and (b) have a meaningful
    # expanding percentile rank. 252 ≈ one year of trading days.
    min_warmup_days: int = 252

    # --- GARCH spec ---
    # GARCH(1,1) is the workhorse. mean='Zero' is fine for daily returns
    # at this purpose; we don't care about drift in the vol tag.
    garch_p: int = 1
    garch_q: int = 1
    mean: Literal["Zero", "Constant", "AR"] = "Zero"
    # arch_model takes returns scaled to %; we scale internally.
    return_scale: float = 100.0


def _bars_to_daily_returns(bars: pl.DataFrame, tz: str = "America/New_York") -> pl.DataFrame:
    """Resample a (possibly intraday) bars frame to daily close-to-close log returns.

    Returns a frame with columns: ``date`` (date), ``close`` (float),
    ``daily_return`` (float, log return). The first row's ``daily_return``
    is NaN by construction.
    """
    if bars.is_empty():
        return pl.DataFrame({"date": [], "close": [], "daily_return": []})

    # If we already have a 'close' per session, just use that — otherwise
    # take the last close per local calendar date.
    if "ts" not in bars.columns:
        raise ValueError("_bars_to_daily_returns requires a 'ts' column")

    local_date = pl.col("ts").dt.convert_time_zone(tz).dt.date().alias("date")
    daily = (
        bars.sort("ts")
        .with_columns(local_date)
        .group_by("date", maintain_order=True)
        .agg(pl.col("close").last().alias("close"))
        .sort("date")
    )

    daily = daily.with_columns(
        (pl.col("close") / pl.col("close").shift(1)).log().alias("daily_return"),
    )
    return daily


def _fit_garch_cond_vol(returns_pct: np.ndarray, cfg: MacroRegimeConfig) -> np.ndarray:
    """Fit GARCH(p,q) and return the conditional volatility series (same length).

    Returns are in percent units (e.g. 1.0 == 1%). The arch package wants
    them scaled this way for numerical stability.
    """
    # Lazy import: arch is an optional/macro-overlay dep, keep import here so
    # the rest of the regime module loads even if arch is missing.
    from arch import arch_model  # type: ignore[import-untyped]

    # Drop the first NaN
    clean = returns_pct[~np.isnan(returns_pct)]
    if clean.size < 50:
        raise ValueError(
            f"Need ≥50 daily returns to fit GARCH; got {clean.size}. "
            "Pull more history before computing the macro regime."
        )

    model = arch_model(
        clean,
        mean=cfg.mean,
        vol="Garch",
        p=cfg.garch_p,
        q=cfg.garch_q,
        rescale=False,
    )
    res = model.fit(disp="off", show_warning=False)
    cond_vol_clean = np.asarray(res.conditional_volatility, dtype=float)

    # Re-pad with NaN where the input had NaN (preserves length alignment)
    out = np.full(returns_pct.shape, np.nan)
    out[~np.isnan(returns_pct)] = cond_vol_clean
    return out


def _expanding_percentile_rank(x: np.ndarray) -> np.ndarray:
    """Compute the expanding percentile rank of each element.

    rank[i] = (# of x[0..i] strictly less than x[i] + 0.5 * # equal) / (i+1)
    Returns NaN where x[i] is NaN.

    O(n log n) using cumulative counts via sort would be cleaner, but at
    daily frequency (~250 obs/year × few decades), a clean O(n^2) loop is
    plenty fast and trivially correct.
    """
    n = x.shape[0]
    out = np.full(n, np.nan)
    for i in range(n):
        xi = x[i]
        if np.isnan(xi):
            continue
        # Consider only observations [0..i] that are not NaN
        window = x[: i + 1]
        valid = window[~np.isnan(window)]
        if valid.size == 0:
            continue
        less = float(np.sum(valid < xi))
        equal = float(np.sum(valid == xi))
        out[i] = (less + 0.5 * equal) / valid.size
    return out


def classify_volatility_regime(
    bars: pl.DataFrame,
    *,
    cfg: MacroRegimeConfig | None = None,
    tz: str = "America/New_York",
) -> pl.DataFrame:
    """Classify each calendar day into {low_vol, normal_vol, high_vol}.

    Parameters
    ----------
    bars : pl.DataFrame
        Bars frame with ``ts`` (datetime) and ``close`` (float). Can be
        intraday or daily; intraday is resampled to daily close-to-close
        log returns.
    cfg : MacroRegimeConfig, optional
        Tunable thresholds. Sensible defaults if None.
    tz : str
        IANA timezone used to bucket bars into calendar days.

    Returns
    -------
    pl.DataFrame
        One row per trading day. Columns:
            date              date
            close             float
            daily_return      float (log return; NaN on first day)
            cond_vol          float (GARCH(1,1) conditional vol, % units)
            cond_vol_pct_rank float (expanding rank in [0,1]; NaN during warmup)
            vol_regime        str | None  (None during warmup)
    """
    cfg = cfg or MacroRegimeConfig()

    daily = _bars_to_daily_returns(bars, tz=tz)
    if daily.is_empty():
        return daily.with_columns(
            pl.lit(None).cast(pl.Float64).alias("cond_vol"),
            pl.lit(None).cast(pl.Float64).alias("cond_vol_pct_rank"),
            pl.lit(None).cast(pl.Utf8).alias("vol_regime"),
        )

    returns = daily["daily_return"].to_numpy() * cfg.return_scale

    logger.info(
        "Fitting GARCH({}, {}) on {} daily returns ({} valid)...",
        cfg.garch_p,
        cfg.garch_q,
        returns.size,
        int(np.sum(~np.isnan(returns))),
    )
    cond_vol = _fit_garch_cond_vol(returns, cfg)
    logger.info(
        "GARCH fit done. Cond-vol range: [{:.3f}%, {:.3f}%], mean {:.3f}%.",
        float(np.nanmin(cond_vol)),
        float(np.nanmax(cond_vol)),
        float(np.nanmean(cond_vol)),
    )

    pct_rank = _expanding_percentile_rank(cond_vol)

    # Tag, but blank out warmup days where we don't have enough history
    # to make the rank meaningful.
    n = cond_vol.shape[0]
    warmup_mask = np.arange(n) < cfg.min_warmup_days

    tags: list[str | None] = []
    for i in range(n):
        if warmup_mask[i] or np.isnan(pct_rank[i]):
            tags.append(None)
        elif pct_rank[i] < cfg.low_pct:
            tags.append("low_vol")
        elif pct_rank[i] < cfg.high_pct:
            tags.append("normal_vol")
        else:
            tags.append("high_vol")

    return daily.with_columns(
        pl.Series("cond_vol", cond_vol, dtype=pl.Float64),
        pl.Series("cond_vol_pct_rank", pct_rank, dtype=pl.Float64),
        pl.Series("vol_regime", tags, dtype=pl.Utf8),
    )


def attach_vol_regime_to_bars(
    bars: pl.DataFrame,
    daily_regime: pl.DataFrame,
    *,
    tz: str = "America/New_York",
    as_of: Literal["same_day", "prior_close"] = "prior_close",
) -> pl.DataFrame:
    """Join a daily ``vol_regime`` tag back onto an intraday bars frame.

    ``as_of='prior_close'`` (default) attaches *yesterday's* regime tag to
    each intraday bar, which is the only no-lookahead choice for a
    strategy that fires at any time during the session.

    ``as_of='same_day'`` is for backtests/analytics that want to slice
    P&L by the day's own vol regime — DO NOT use this for live signal
    generation.
    """
    if bars.is_empty() or daily_regime.is_empty():
        return bars.with_columns(pl.lit(None).cast(pl.Utf8).alias("vol_regime"))

    bars = bars.with_columns(
        pl.col("ts").dt.convert_time_zone(tz).dt.date().alias("_date"),
    )

    if as_of == "prior_close":
        regime_lookup = daily_regime.select(
            (pl.col("date") + pl.duration(days=1)).alias("_date"),
            pl.col("vol_regime"),
        )
    else:
        regime_lookup = daily_regime.select(
            pl.col("date").alias("_date"),
            pl.col("vol_regime"),
        )

    return bars.join(regime_lookup, on="_date", how="left").drop("_date")


def latest_regime(daily_regime: pl.DataFrame) -> tuple[date_t, str | None]:
    """Return (date, regime) for the most recent classified day.

    Useful for live decision-making: 'what is the current vol regime?'.
    Returns regime=None if the most recent day is still in warmup.
    """
    if daily_regime.is_empty():
        raise ValueError("daily_regime is empty")
    last = daily_regime.sort("date").tail(1)
    return last["date"].item(), last["vol_regime"].item()
