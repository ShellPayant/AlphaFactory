"""Walk-forward + Monte Carlo end-to-end on a chosen strategy.

Usage::

    python scripts/run_walk_forward.py --strategy intraday_momentum_spy \
        --symbol SPY --train-months 18 --test-months 6 --step-months 6 \
        --fee-model alpaca_paper

Or double-click ``scripts/run_walk_forward.bat`` for defaults.

Produces a single Markdown report combining:
1. Per-window OOS metrics (walk-forward)
2. Monte Carlo trade-order reshuffle on the aggregated OOS trades
3. Pass/fail verdict on G1.5 + G1.6 graduation gates
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import polars as pl
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest import (  # noqa: E402
    ALPACA_PAPER,
    PESSIMISTIC,
    render_monte_carlo_markdown,
    render_walk_forward_markdown,
    run_monte_carlo,
    run_walk_forward,
)
from src.config.settings import get_settings  # noqa: E402
from src.data.storage.parquet_store import read_bars  # noqa: E402
from src.features.adx import adx  # noqa: E402
from src.features.atr import atr  # noqa: E402
from src.features.vwap import session_vwap  # noqa: E402
from src.regimes.regime_classifier import classify_regimes  # noqa: E402
from src.strategies import IntradayMomentumSPY, RangeMeanReversion  # noqa: E402

STRATEGY_REGISTRY = {
    "range_mean_reversion": (RangeMeanReversion, "5Min", None),
    "intraday_momentum_spy": (IntradayMomentumSPY, "5Min", "30m"),
}

FEE_MODELS = {"alpaca_paper": ALPACA_PAPER, "pessimistic": PESSIMISTIC}


def _resample_to(bars: pl.DataFrame, period: str) -> pl.DataFrame:
    if bars.is_empty():
        return bars
    ts_local_date = pl.col("ts").dt.convert_time_zone("America/New_York").dt.date()
    return (
        bars.sort("ts")
        .with_columns(ts_local_date.alias("_session_date"))
        .group_by_dynamic(
            index_column="ts",
            every=period,
            label="left",
            closed="left",
            group_by="_session_date",
        )
        .agg(
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
            pl.col("symbol").first().alias("symbol"),
        )
        .drop("_session_date")
        .sort("ts")
    )


@click.command(context_settings={"show_default": True})
@click.option(
    "--strategy",
    type=click.Choice(list(STRATEGY_REGISTRY.keys())),
    default="intraday_momentum_spy",
)
@click.option("--symbol", default="SPY")
@click.option("--train-months", default=18, type=int)
@click.option("--test-months", default=6, type=int)
@click.option("--step-months", default=6, type=int)
@click.option("--starting-equity", default=100_000.0, type=float)
@click.option("--risk-per-trade", default=0.0025, type=float)
@click.option("--max-notional-pct", default=1.0, type=float)
@click.option("--min-stop-pct", default=0.0005, type=float)
@click.option(
    "--fee-model",
    type=click.Choice(list(FEE_MODELS.keys())),
    default="alpaca_paper",
)
@click.option("--mc-sims", default=1000, type=int, help="Monte Carlo simulations.")
@click.option("--mc-seed", default=42, type=int)
@click.option(
    "--out-dir",
    default="reports",
    type=click.Path(path_type=Path),
)
def main(
    strategy: str,
    symbol: str,
    train_months: int,
    test_months: int,
    step_months: int,
    starting_equity: float,
    risk_per_trade: float,
    max_notional_pct: float,
    min_stop_pct: float,
    fee_model: str,
    mc_sims: int,
    mc_seed: int,
    out_dir: Path,
) -> None:
    settings = get_settings()
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = out_dir / f"_walkfwd_{stamp}_{strategy}_{symbol}.log"
    logger.add(str(log_path), level="INFO")
    logger.info("Run log: {}", log_path)

    strat_cls, source_tf, target_tf = STRATEGY_REGISTRY[strategy]

    logger.info("Loading bars: {} {}", symbol, source_tf)
    bars = read_bars(
        root=settings.alpha_data_root,
        symbol=symbol,
        timeframe=source_tf,
        start=None,
        end=None,
    )
    if bars.is_empty():
        logger.error("No bars found. Run scripts/pull_data.bat first.")
        sys.exit(1)

    if "symbol" not in bars.columns:
        bars = bars.with_columns(pl.lit(symbol).alias("symbol"))

    if target_tf is not None:
        logger.info("Resampling {} → {} ({} bars in)...", source_tf, target_tf, bars.height)
        bars = _resample_to(bars, target_tf)
        logger.info("After resample: {} bars.", bars.height)

    report_tf = target_tf or source_tf

    logger.info("Computing indicators + regimes...")
    bars = atr(bars, period=14)
    bars = adx(bars, period=14)
    bars = session_vwap(bars)
    bars = classify_regimes(bars)

    logger.info(
        "Running walk-forward: train={}mo / test={}mo / step={}mo, fee={}...",
        train_months, test_months, step_months, fee_model,
    )
    wf = run_walk_forward(
        bars,
        strategy_factory=strat_cls,
        timeframe=report_tf,
        train_months=train_months,
        test_months=test_months,
        step_months=step_months,
        starting_equity=starting_equity,
        risk_per_trade=risk_per_trade,
        max_notional_pct=max_notional_pct,
        min_stop_pct=min_stop_pct,
        fee_model=FEE_MODELS[fee_model],
        symbol=symbol,
    )
    logger.info(
        "Walk-forward done: {} windows, mean Sharpe {:.2f}, worst Sharpe {:.2f}, {} OOS trades total.",
        wf.n_windows, wf.mean_sharpe, wf.worst_window_sharpe, wf.total_trades,
    )

    logger.info("Running Monte Carlo ({} sims) on aggregated OOS trades...", mc_sims)
    mc = run_monte_carlo(
        wf.all_oos_trades,
        starting_equity=starting_equity,
        n_simulations=mc_sims,
        seed=mc_seed,
    )
    logger.info(
        "Monte Carlo done: p05 final ${:,.0f}, p50 ${:,.0f}, p95 ${:,.0f}. {:.1f}% sims profitable.",
        mc.final_equity_p05, mc.final_equity_p50, mc.final_equity_p95, mc.pct_sims_profitable,
    )

    # Combined report.
    parts: list[str] = []
    parts.append(render_walk_forward_markdown(wf))
    parts.append("")
    parts.append(render_monte_carlo_markdown(mc))
    parts.append("")
    parts.append("## Combined verdict")
    parts.append("")
    g1_5_a = wf.passes_g1_5_no_negative_window()
    g1_5_b = wf.passes_g1_5_min_windows(3)
    g1_6 = mc.passes_g1_6_5th_pct_positive()
    overall = g1_5_a and g1_5_b and g1_6
    parts.append(f"- G1.5 walk-forward (no negative-Sharpe window): {'✅' if g1_5_a else '❌'}")
    parts.append(f"- G1.5 walk-forward (≥3 windows): {'✅' if g1_5_b else '❌'}")
    parts.append(f"- G1.6 Monte Carlo (5th-pctile equity positive): {'✅' if g1_6 else '❌'}")
    parts.append("")
    parts.append(
        f"**Overall walk-forward + Monte Carlo gates: "
        f"{'PASS — proceed to other G1 gates' if overall else 'FAIL — strategy does not qualify for paper trading'}**"
    )
    parts.append("")
    parts.append(f"_Fee model used: {fee_model}_")
    parts.append("")

    out_path = out_dir / f"walkfwd_{stamp}_{strategy}_{symbol}_{fee_model}.md"
    out_path.write_text("\n".join(parts), encoding="utf-8")
    logger.info("Combined report: {}", out_path)


if __name__ == "__main__":
    main()
