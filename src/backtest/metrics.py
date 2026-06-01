"""Backtest performance metrics.

Operates on a :class:`BacktestResult`. Returns plain dicts so the report
module can render them however it likes (Markdown, JSON, Streamlit, etc.).

All metrics avoid pandas — Polars + Python math only — to keep this
package dependency-light.
"""

from __future__ import annotations

import math
from collections import Counter

import polars as pl

from .research_engine import BacktestResult, Trade

# Bars-per-year for annualization. 252 trading days × 78 5-min bars/day = 19_656.
DEFAULT_BARS_PER_YEAR: dict[str, int] = {
    "1Min": 252 * 390,
    "5Min": 252 * 78,
    "15Min": 252 * 26,
    "30m": 252 * 13,   # 6.5-hour RTH session at 30-min bars
    "30Min": 252 * 13,
    "1Hour": 252 * 7,  # approx — RTH has ~6.5 hrs
    "1Day": 252,
}


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def trade_stats(trades: list[Trade]) -> dict:
    """Per-trade aggregate stats."""
    if not trades:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "avg_bars_held": 0.0,
            "max_consecutive_losses": 0,
            "max_consecutive_wins": 0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
        }

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    # Consecutive streaks
    max_w = max_l = cur_w = cur_l = 0
    for p in pnls:
        if p > 0:
            cur_w += 1
            cur_l = 0
        else:
            cur_l += 1
            cur_w = 0
        max_w = max(max_w, cur_w)
        max_l = max(max_l, cur_l)

    return {
        "n_trades": len(trades),
        "win_rate": _safe_div(len(wins), len(trades)),
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "profit_factor": _safe_div(sum(wins), -sum(losses)) if losses else float("inf") if wins else 0.0,
        "expectancy": sum(pnls) / len(pnls),
        "avg_bars_held": sum(t.bars_held for t in trades) / len(trades),
        "max_consecutive_losses": max_l,
        "max_consecutive_wins": max_w,
        "best_trade": max(pnls),
        "worst_trade": min(pnls),
    }


def equity_curve_stats(
    equity_curve: pl.DataFrame,
    *,
    starting_equity: float,
    bars_per_year: int,
) -> dict:
    """Returns, drawdown, Sharpe, Sortino, time-under-water."""
    if equity_curve.height < 2:
        return {
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown_pct": 0.0,
            "time_under_water_pct": 0.0,
            "n_bars": equity_curve.height,
        }

    eq = equity_curve["equity"].to_list()
    ending = eq[-1]
    total_ret = ending / starting_equity - 1.0

    # CAGR using bar-count → years
    years = max(equity_curve.height / bars_per_year, 1e-9)
    cagr = (ending / starting_equity) ** (1 / years) - 1.0

    # Bar-to-bar returns
    rets = [(eq[i] / eq[i - 1] - 1.0) for i in range(1, len(eq)) if eq[i - 1] != 0]
    mean_r = sum(rets) / len(rets) if rets else 0.0
    var_r = sum((r - mean_r) ** 2 for r in rets) / len(rets) if rets else 0.0
    std_r = math.sqrt(var_r) if var_r > 0 else 0.0
    downside = [min(r, 0.0) for r in rets]
    var_d = sum(r * r for r in downside) / len(downside) if downside else 0.0
    std_d = math.sqrt(var_d) if var_d > 0 else 0.0

    sharpe = _safe_div(mean_r * bars_per_year, std_r * math.sqrt(bars_per_year))
    sortino = _safe_div(mean_r * bars_per_year, std_d * math.sqrt(bars_per_year))

    # Drawdown
    peak = eq[0]
    max_dd = 0.0
    bars_uw = 0
    for v in eq:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
        if v < peak:
            bars_uw += 1

    return {
        "total_return_pct": total_ret * 100.0,
        "cagr_pct": cagr * 100.0,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown_pct": max_dd * 100.0,
        "time_under_water_pct": bars_uw / len(eq) * 100.0,
        "n_bars": len(eq),
    }


def regime_slice(trades: list[Trade]) -> pl.DataFrame:
    """Per-regime trade count + P&L + win rate."""
    if not trades:
        return pl.DataFrame(
            schema={
                "quant_regime": pl.String,
                "n_trades": pl.UInt32,
                "total_pnl": pl.Float64,
                "win_rate": pl.Float64,
            }
        )

    by: Counter[str] = Counter()
    pnl_by: dict[str, float] = {}
    wins_by: dict[str, int] = {}
    for t in trades:
        by[t.regime_tag] += 1
        pnl_by[t.regime_tag] = pnl_by.get(t.regime_tag, 0.0) + t.pnl
        wins_by[t.regime_tag] = wins_by.get(t.regime_tag, 0) + (1 if t.pnl > 0 else 0)

    rows = [
        {
            "quant_regime": k,
            "n_trades": v,
            "total_pnl": pnl_by[k],
            "win_rate": wins_by[k] / v,
        }
        for k, v in sorted(by.items(), key=lambda x: -x[1])
    ]
    return pl.DataFrame(rows)


def exit_reason_breakdown(trades: list[Trade]) -> dict[str, int]:
    """Count of trades by exit reason."""
    c: Counter[str] = Counter(t.exit_reason for t in trades)
    return dict(c)


def all_metrics(
    result: BacktestResult,
    *,
    timeframe: str = "5Min",
) -> dict:
    """One-shot: returns dict-of-dicts with every metric block."""
    bpy = DEFAULT_BARS_PER_YEAR.get(timeframe, 252 * 78)
    return {
        "trade_stats": trade_stats(result.trades),
        "equity_stats": equity_curve_stats(
            result.equity_curve,
            starting_equity=result.starting_equity,
            bars_per_year=bpy,
        ),
        "exit_reasons": exit_reason_breakdown(result.trades),
        "signals_generated": result.signals_generated,
        "signals_skipped_by_sizing": result.signals_skipped_by_sizing,
        "signals_skipped_by_max_notional": result.signals_skipped_by_max_notional,
        "signals_skipped_by_min_stop": result.signals_skipped_by_min_stop,
    }
