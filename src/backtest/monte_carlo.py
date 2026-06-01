"""Monte Carlo trade-reshuffling.

Given a list of trades from a backtest, randomly shuffle the *order* of
those trades N times and rebuild the equity curve each time. This produces
a distribution of possible equity paths that share the same set of trade
P&Ls but with the order of occurrence randomized.

What this tells you:

* If the 5th-percentile equity curve still finishes positive, the strategy
  is robust to trade-order luck — it would have made money even in
  unfavorable sequences.
* If the strategy is barely profitable on the actual path but the 95th
  percentile shows huge returns, you got lucky with the *order* of trades
  (e.g., winners clustered early, losers late, no big drawdown).
* If the max-drawdown distribution has a long tail far worse than the
  realized DD, the realized backtest is hiding sequence risk.

What this does NOT do:

* Resample trades *with replacement* (bootstrap). That's a separate test
  (sample-set robustness) that we're not running here.
* Account for path-dependent risk management (e.g. stops at 5 % equity
  drawdown). We assume sizing is independent of equity for now — fine for
  fixed-fractional sizing on the trade P&L distribution.

This module is pure-Python — no engine involvement. It's fast (1000 sims
on 1000 trades runs in well under a second).

Usage::

    from src.backtest.monte_carlo import run_monte_carlo
    mc = run_monte_carlo(backtest_result.trades, starting_equity=100_000.0)
    print(mc.summary())
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .research_engine import Trade


@dataclass
class MonteCarloResult:
    """Aggregate of N reshuffled equity curves."""

    n_sims: int
    n_trades: int
    starting_equity: float

    # Final equity distribution.
    final_equity_p05: float = 0.0
    final_equity_p25: float = 0.0
    final_equity_p50: float = 0.0
    final_equity_p75: float = 0.0
    final_equity_p95: float = 0.0

    # Max drawdown distribution (absolute % values, e.g. 12.5 for 12.5%).
    max_dd_p05: float = 0.0  # least-bad 5th percentile
    max_dd_p25: float = 0.0
    max_dd_p50: float = 0.0
    max_dd_p75: float = 0.0
    max_dd_p95: float = 0.0  # worst 95th percentile

    # Probability metrics.
    pct_sims_profitable: float = 0.0
    pct_sims_dd_over_20: float = 0.0
    pct_sims_dd_over_30: float = 0.0

    # Realized (un-shuffled) path's values, for reference.
    realized_final_equity: float = 0.0
    realized_max_dd: float = 0.0

    # Quantile curves for plotting later — length = n_trades + 1 each.
    equity_curve_p05: list[float] = field(default_factory=list)
    equity_curve_p50: list[float] = field(default_factory=list)
    equity_curve_p95: list[float] = field(default_factory=list)

    def passes_g1_6_5th_pct_positive(self) -> bool:
        """G1.6 graduation gate: 5th percentile equity curve still positive."""
        return self.final_equity_p05 > self.starting_equity

    def summary(self) -> dict:
        return {
            "n_sims": self.n_sims,
            "n_trades": self.n_trades,
            "starting_equity": self.starting_equity,
            "final_equity_p05": self.final_equity_p05,
            "final_equity_p50": self.final_equity_p50,
            "final_equity_p95": self.final_equity_p95,
            "max_dd_p05": self.max_dd_p05,
            "max_dd_p50": self.max_dd_p50,
            "max_dd_p95": self.max_dd_p95,
            "pct_sims_profitable": self.pct_sims_profitable,
            "pct_sims_dd_over_20": self.pct_sims_dd_over_20,
            "pct_sims_dd_over_30": self.pct_sims_dd_over_30,
            "realized_final_equity": self.realized_final_equity,
            "realized_max_dd": self.realized_max_dd,
            "g1_6_5th_pct_positive": self.passes_g1_6_5th_pct_positive(),
        }


def _equity_path(pnls: list[float], starting: float) -> list[float]:
    """Walk a list of PnLs into an equity series of length n+1."""
    eq = [starting]
    cur = starting
    for p in pnls:
        cur += p
        eq.append(cur)
    return eq


def _max_drawdown_pct(eq: list[float]) -> float:
    """Max % drawdown from peak. Returned as a positive number, e.g. 12.5."""
    peak = eq[0]
    worst = 0.0
    for v in eq:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100.0
            if dd > worst:
                worst = dd
    return worst


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile over a *pre-sorted* list."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = pct / 100.0 * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def run_monte_carlo(
    trades: list[Trade],
    *,
    starting_equity: float = 100_000.0,
    n_simulations: int = 1000,
    seed: int = 42,
) -> MonteCarloResult:
    """Reshuffle trade order N times and compute the distribution of paths.

    Returns a :class:`MonteCarloResult` with percentile final-equity and
    max-drawdown values, plus the actual 5th / 50th / 95th percentile
    equity curves point-by-point (for downstream plotting).
    """
    if n_simulations < 1:
        raise ValueError("n_simulations must be >= 1")

    if not trades:
        # Nothing to simulate — return a degenerate result.
        return MonteCarloResult(
            n_sims=0,
            n_trades=0,
            starting_equity=starting_equity,
            final_equity_p05=starting_equity,
            final_equity_p25=starting_equity,
            final_equity_p50=starting_equity,
            final_equity_p75=starting_equity,
            final_equity_p95=starting_equity,
            realized_final_equity=starting_equity,
        )

    rng = random.Random(seed)
    pnls = [t.pnl for t in trades]
    n_trades = len(pnls)

    # Realized (un-shuffled) reference.
    realized_eq = _equity_path(pnls, starting_equity)
    realized_final = realized_eq[-1]
    realized_dd = _max_drawdown_pct(realized_eq)

    # Run the simulations. Track per-sim final equity, per-sim max DD, and
    # all equity curves (we need them for the quantile curves at the end).
    final_equities: list[float] = []
    max_dds: list[float] = []
    curves: list[list[float]] = []

    for _ in range(n_simulations):
        shuffled = pnls[:]
        rng.shuffle(shuffled)
        eq = _equity_path(shuffled, starting_equity)
        curves.append(eq)
        final_equities.append(eq[-1])
        max_dds.append(_max_drawdown_pct(eq))

    sorted_finals = sorted(final_equities)
    sorted_dds = sorted(max_dds)

    pct_profitable = (
        sum(1 for v in final_equities if v > starting_equity) / n_simulations * 100.0
    )
    pct_dd_over_20 = sum(1 for v in max_dds if v > 20.0) / n_simulations * 100.0
    pct_dd_over_30 = sum(1 for v in max_dds if v > 30.0) / n_simulations * 100.0

    # Build percentile equity curves: at each trade index, take the
    # percentile across all simulations.
    eq_p05: list[float] = []
    eq_p50: list[float] = []
    eq_p95: list[float] = []
    curve_len = n_trades + 1
    for i in range(curve_len):
        vals = sorted(c[i] for c in curves)
        eq_p05.append(_percentile(vals, 5.0))
        eq_p50.append(_percentile(vals, 50.0))
        eq_p95.append(_percentile(vals, 95.0))

    return MonteCarloResult(
        n_sims=n_simulations,
        n_trades=n_trades,
        starting_equity=starting_equity,
        final_equity_p05=_percentile(sorted_finals, 5.0),
        final_equity_p25=_percentile(sorted_finals, 25.0),
        final_equity_p50=_percentile(sorted_finals, 50.0),
        final_equity_p75=_percentile(sorted_finals, 75.0),
        final_equity_p95=_percentile(sorted_finals, 95.0),
        max_dd_p05=_percentile(sorted_dds, 5.0),
        max_dd_p25=_percentile(sorted_dds, 25.0),
        max_dd_p50=_percentile(sorted_dds, 50.0),
        max_dd_p75=_percentile(sorted_dds, 75.0),
        max_dd_p95=_percentile(sorted_dds, 95.0),
        pct_sims_profitable=pct_profitable,
        pct_sims_dd_over_20=pct_dd_over_20,
        pct_sims_dd_over_30=pct_dd_over_30,
        realized_final_equity=realized_final,
        realized_max_dd=realized_dd,
        equity_curve_p05=eq_p05,
        equity_curve_p50=eq_p50,
        equity_curve_p95=eq_p95,
    )


def render_monte_carlo_markdown(result: MonteCarloResult) -> str:
    """Render a Monte Carlo result as a Markdown summary block."""
    if result.n_sims == 0:
        return "## Monte Carlo\n\n_No trades — nothing to simulate._\n"

    se = result.starting_equity
    lines: list[str] = []
    lines.append("## Monte Carlo trade-order reshuffle")
    lines.append("")
    lines.append(
        f"_{result.n_sims:,} simulations, {result.n_trades} trades, "
        f"starting equity ${se:,.0f}_"
    )
    lines.append("")
    lines.append("### Final equity distribution")
    lines.append("")
    lines.append("| Percentile | Final equity | Return % |")
    lines.append("|---|---:|---:|")
    for pct, name, val in [
        (5, "p05 (bear)", result.final_equity_p05),
        (25, "p25", result.final_equity_p25),
        (50, "p50 (median)", result.final_equity_p50),
        (75, "p75", result.final_equity_p75),
        (95, "p95 (bull)", result.final_equity_p95),
    ]:
        ret = (val / se - 1.0) * 100.0
        lines.append(f"| {name} | ${val:,.2f} | {ret:+.2f}% |")
    realized_ret = (result.realized_final_equity / se - 1.0) * 100.0
    lines.append(
        f"| **realized (actual order)** | "
        f"**${result.realized_final_equity:,.2f}** | **{realized_ret:+.2f}%** |"
    )
    lines.append("")

    lines.append("### Max drawdown distribution")
    lines.append("")
    lines.append("| Percentile | Max DD |")
    lines.append("|---|---:|")
    lines.append(f"| p05 (least bad) | {result.max_dd_p05:.2f}% |")
    lines.append(f"| p25 | {result.max_dd_p25:.2f}% |")
    lines.append(f"| p50 (median) | {result.max_dd_p50:.2f}% |")
    lines.append(f"| p75 | {result.max_dd_p75:.2f}% |")
    lines.append(f"| p95 (worst) | {result.max_dd_p95:.2f}% |")
    lines.append(f"| **realized** | **{result.realized_max_dd:.2f}%** |")
    lines.append("")

    lines.append("### Probabilities")
    lines.append("")
    lines.append(f"- Simulations finishing profitable: **{result.pct_sims_profitable:.1f}%**")
    lines.append(f"- Simulations with max DD > 20%: **{result.pct_sims_dd_over_20:.1f}%**")
    lines.append(f"- Simulations with max DD > 30%: **{result.pct_sims_dd_over_30:.1f}%**")
    lines.append("")

    lines.append("### G1.6 graduation gate")
    lines.append("")
    g1_6 = "✅ pass" if result.passes_g1_6_5th_pct_positive() else "❌ FAIL"
    lines.append(f"- 5th-percentile final equity > starting equity → **{g1_6}**")
    lines.append("")

    return "\n".join(lines)
