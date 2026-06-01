"""Backtesting — research engine, fees/slippage, metrics, reports.

The Nautilus-backed engine will go in a sibling module ``nautilus_runner.py``
in Sprint 3, sharing the same Strategy interface from ``src/strategies/base.py``.
"""

from .fees import ALPACA_PAPER, PESSIMISTIC, ZERO_COST, FeeModel
from .metrics import all_metrics, equity_curve_stats, regime_slice, trade_stats
from .monte_carlo import MonteCarloResult, render_monte_carlo_markdown, run_monte_carlo
from .reports import render_markdown, write_report
from .research_engine import BacktestResult, Trade, run_backtest
from .walk_forward import (
    WalkForwardResult,
    WindowResult,
    render_walk_forward_markdown,
    run_walk_forward,
)

__all__ = [
    "ALPACA_PAPER",
    "BacktestResult",
    "FeeModel",
    "MonteCarloResult",
    "PESSIMISTIC",
    "Trade",
    "WalkForwardResult",
    "WindowResult",
    "ZERO_COST",
    "all_metrics",
    "equity_curve_stats",
    "regime_slice",
    "render_markdown",
    "render_monte_carlo_markdown",
    "render_walk_forward_markdown",
    "run_backtest",
    "run_monte_carlo",
    "run_walk_forward",
    "trade_stats",
    "write_report",
]
