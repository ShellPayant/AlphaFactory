"""Parameter grids for autonomous strategy search.

Design principle: each grid axis must have a defensible rationale.
Sweeping arbitrary param ranges is the easiest way to overfit and
the gauntlet will (correctly) reject everything. Each axis below has
a one-line "why this range" comment.

A "grid" here is a list of kwargs dicts. The batch runner instantiates
``StrategyCls(**kwargs)`` for each entry, runs walk-forward + Monte
Carlo, and applies a multiple-testing penalty (Bonferroni or Deflated
Sharpe) to the aggregated INDEX so we don't celebrate variants that
look good only because we tried many.

Total variants currently: ~100 (×~30 ETFs in Tier 1 ≈ 3,000 combos,
×~210 Tier 3 names ≈ 21,000 combos per nightly batch).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# rsi2_pullback (Connors RSI(2) buy-the-dip)
# ---------------------------------------------------------------------------
# - rsi_oversold: 5 (Connors original), 10 (current default), 15 (looser).
#   These bracket the published-vs-tunable range.
# - trend_sma_period: 100 (faster trend filter) vs 200 (Connors default).
# - stop_atr_mult: 2.0 (tight, more stops) vs 3.0 (default, more room).
RSI2_PULLBACK_GRID: list[dict[str, Any]] = [
    {"rsi_oversold": o, "trend_sma_period": t, "stop_atr_mult": s}
    for o in (5.0, 10.0, 15.0)
    for t in (100, 200)
    for s in (2.0, 3.0)
]  # 12 variants

# ---------------------------------------------------------------------------
# bollinger_mr (Bollinger Band mean-reversion, long-only, with trend filter)
# ---------------------------------------------------------------------------
# - bb_period: 10 (faster), 20 (default), 40 (slower) — captures different
#   timescales of the mean-reversion impulse.
# - bb_stdev: 1.5 (more signals), 2.0 (standard), 2.5 (extreme dislocations).
# - trend_sma_period: only 200 — for MR strategies the trend filter is
#   binary on/off; finer tuning here invites curve-fitting.
BOLLINGER_MR_GRID: list[dict[str, Any]] = [
    {"bb_period": p, "bb_stdev": s, "trend_sma_period": 200}
    for p in (10, 20, 40)
    for s in (1.5, 2.0, 2.5)
]  # 9 variants

# ---------------------------------------------------------------------------
# donchian_trend (Donchian channel breakout)
# ---------------------------------------------------------------------------
# - breakout_period: 20 (turtle short-term), 55 (turtle long-term), 100
#   (slower trends). These are the canonical turtle params + one slower.
# - trail_period: 10, 20, 55 (trailing stop horizon).
# - stop_atr_mult: 2.0, 3.0 — initial stop before trail tightens.
DONCHIAN_TREND_GRID: list[dict[str, Any]] = [
    {"breakout_period": b, "trail_period": t, "stop_atr_mult": s}
    for b in (20, 55, 100)
    for t in (10, 20, 55)
    for s in (2.0, 3.0)
    if t <= b  # trailing horizon can't outlast the breakout signal
]  # 12 variants

# ---------------------------------------------------------------------------
# five_day_reversal
# ---------------------------------------------------------------------------
# - low_lookback: 3, 5, 7 — the "n-day low" buy condition.
# - stop_atr_mult / target_atr_mult: kept in coupled pairs to preserve
#   sensible R:R ratios (no exploding the grid by uncoupling).
FIVE_DAY_REVERSAL_GRID: list[dict[str, Any]] = [
    {"low_lookback": lb, "stop_atr_mult": s, "target_atr_mult": t}
    for lb in (3, 5, 7)
    for (s, t) in ((2.0, 3.0), (3.0, 4.0), (3.0, 5.0))
]  # 9 variants

# ---------------------------------------------------------------------------
# internal_bar_strength (IBS)
# ---------------------------------------------------------------------------
# - ibs_threshold: 0.1 (only extreme weak closes), 0.2 (default), 0.3 (looser).
# - trend_sma_period: 100, 200.
# - stop/target: coupled pair, modest R:R because IBS is a short-horizon trade.
INTERNAL_BAR_STRENGTH_GRID: list[dict[str, Any]] = [
    {
        "ibs_threshold": th,
        "trend_sma_period": tsma,
        "stop_atr_mult": s,
        "target_atr_mult": t,
    }
    for th in (0.1, 0.2, 0.3)
    for tsma in (100, 200)
    for (s, t) in ((2.0, 2.5), (3.0, 3.5))
]  # 12 variants

# ---------------------------------------------------------------------------
# monthly_momentum (cross-sectional momentum proxy at single-name level)
# ---------------------------------------------------------------------------
# - lookback_bars: 21 (1mo), 63 (3mo), 126 (6mo), 252 (12mo) —
#   the canonical momentum horizons in the academic literature.
# - min_lookback_return: 0% (pure momentum), 2%, 5% — filter to require
#   the trend be of meaningful magnitude, not just barely positive.
MONTHLY_MOMENTUM_GRID: list[dict[str, Any]] = [
    {"lookback_bars": lb, "min_lookback_return": r, "trend_sma_period": 200}
    for lb in (21, 63, 126, 252)
    for r in (0.0, 0.02, 0.05)
]  # 12 variants

# ---------------------------------------------------------------------------
# turn_of_month
# ---------------------------------------------------------------------------
# - stop_atr_mult / target_atr_mult: coupled pairs.
# - max_hold_bars: 3 (only the turn-of-month window itself), 5, 8.
TURN_OF_MONTH_GRID: list[dict[str, Any]] = [
    {"stop_atr_mult": s, "target_atr_mult": t, "max_hold_bars": m}
    for (s, t) in ((2.0, 3.0), (3.0, 4.0))
    for m in (3, 5, 8)
]  # 6 variants


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Maps strategy_key (matches keys in scripts/run_strategy_batch.py STRATEGY_REGISTRY)
# to its parameter grid. Strategies absent from this map run with their
# default config only (single-variant).
GRIDS: dict[str, list[dict[str, Any]]] = {
    "rsi2_pullback": RSI2_PULLBACK_GRID,
    "bollinger_mr": BOLLINGER_MR_GRID,
    "donchian_trend": DONCHIAN_TREND_GRID,
    "five_day_reversal": FIVE_DAY_REVERSAL_GRID,
    "internal_bar_strength": INTERNAL_BAR_STRENGTH_GRID,
    "monthly_momentum": MONTHLY_MOMENTUM_GRID,
    "turn_of_month": TURN_OF_MONTH_GRID,
}


def grid_for(strategy_key: str) -> list[dict[str, Any]]:
    """Return the param grid for a strategy. Empty dict (default config) if absent."""
    return GRIDS.get(strategy_key, [{}])


def total_variants() -> int:
    """Total number of (strategy, params) combinations across all grids."""
    return sum(len(g) for g in GRIDS.values())


def variant_id(strategy_key: str, params: dict[str, Any]) -> str:
    """Stable, filesystem-safe ID for one (strategy, params) variant.

    Used in report filenames so each variant gets its own .md.
    Sorted by key so dict ordering doesn't change the ID.
    """
    if not params:
        return strategy_key
    parts = [f"{k}={v}" for k, v in sorted(params.items())]
    return f"{strategy_key}__{'_'.join(parts)}"
