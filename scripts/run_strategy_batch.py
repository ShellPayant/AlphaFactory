"""Batch run a portfolio of strategy candidates through walk-forward + Monte Carlo.

This is the "leave it running overnight, ranked report in the morning" script.

Runs each (strategy, symbol) pair through:
  1. Walk-forward (18mo train / 6mo test / 6mo step, default)
  2. Monte Carlo trade-reshuffle (1000 sims) on aggregated OOS trades
  3. Writes a combined per-pair Markdown report under
     reports/_batch_<timestamp>/<strategy>_<symbol>.md
  4. Writes reports/_batch_<timestamp>/INDEX.md ranking all pairs by G1 gates

Usage::

    uv run python scripts/run_strategy_batch.py

Optional flags::

    --fee-model alpaca_paper | pessimistic
    --train-months 18 --test-months 6 --step-months 6
    --mc-sims 1000
    --only internal_bar_strength,turn_of_month     (filter strategies)
    --symbols SPY,QQQ                              (override default universe)

A single batch run on 7 strategies × 2 symbols × full 5y history takes
roughly 5-15 minutes on a laptop, depending on signal density.
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import click
import polars as pl
from loguru import logger

# Force UTF-8 stdout so Polars' Unicode chars render cleanly on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# In-Python tee — keeps log file alongside the per-strategy reports.
_REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
_STAMP = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
_BATCH_DIR = _REPORTS_DIR / f"_batch_{_STAMP}"
_BATCH_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = _BATCH_DIR / "run.log"
_LOG_FILE = open(_LOG_PATH, "w", encoding="utf-8")  # noqa: SIM115


class _Tee:
    def __init__(self, *streams: object) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for s in self._streams:
            try:
                s.write(data)  # type: ignore[attr-defined]
                s.flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return len(data)

    def flush(self) -> None:
        for s in self._streams:
            try:
                s.flush()  # type: ignore[attr-defined]
            except Exception:
                pass


sys.stdout = _Tee(sys.stdout, _LOG_FILE)  # type: ignore[assignment]
sys.stderr = _Tee(sys.stderr, _LOG_FILE)  # type: ignore[assignment]
print(f"[tee] Mirroring all output to: {_LOG_PATH}")
print(f"[batch] Reports will be written under: {_BATCH_DIR}")


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
from src.features.atr import atr  # noqa: E402
from src.strategies import (  # noqa: E402
    BollingerMR,
    DonchianTrend,
    FiveDayReversal,
    InternalBarStrength,
    MonthlyMomentum,
    RSI2Pullback,
    TurnOfMonth,
)

FEE_MODELS = {"alpaca_paper": ALPACA_PAPER, "pessimistic": PESSIMISTIC}

# Default batch: 7 strategies × 2 symbols = 14 runs.
# Each tuple = (strategy_key, strategy_class, source_timeframe, target_timeframe).
STRATEGY_REGISTRY: dict[str, tuple[type, str, str | None]] = {
    "internal_bar_strength": (InternalBarStrength, "5Min", "1d"),
    "turn_of_month": (TurnOfMonth, "5Min", "1d"),
    "bollinger_mr": (BollingerMR, "5Min", "1d"),
    "donchian_trend": (DonchianTrend, "5Min", "1d"),
    "monthly_momentum": (MonthlyMomentum, "5Min", "1d"),
    "rsi2_pullback": (RSI2Pullback, "5Min", "1d"),
    "five_day_reversal": (FiveDayReversal, "5Min", "1d"),
}

DEFAULT_SYMBOLS = ("SPY", "QQQ")


@dataclass
class PairResult:
    strategy: str
    symbol: str
    n_windows: int
    mean_sharpe: float
    worst_window_sharpe: float
    total_oos_trades: int
    mc_p05_final: float
    mc_p50_final: float
    mc_pct_profitable: float
    g1_5_no_neg_window: bool
    g1_5_min_3_windows: bool
    g1_6_p05_positive: bool
    overall_pass: bool
    report_path: Path
    error: str | None = None

    @property
    def status(self) -> str:
        if self.error is not None:
            return "ERROR"
        return "PASS" if self.overall_pass else "FAIL"


def _resample_to(bars: pl.DataFrame, period: str) -> pl.DataFrame:
    """Resample intraday bars to a coarser timeframe using NY session-date grouping."""
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


def _run_one(
    *,
    strategy_key: str,
    strategy_cls: type,
    symbol: str,
    source_tf: str,
    target_tf: str | None,
    train_months: int,
    test_months: int,
    step_months: int,
    starting_equity: float,
    risk_per_trade: float,
    max_notional_pct: float,
    min_stop_pct: float,
    fee_model_name: str,
    mc_sims: int,
    mc_seed: int,
    data_root: Path,
) -> PairResult:
    """Run walk-forward + MC on one (strategy, symbol) pair."""
    logger.info("=" * 60)
    logger.info(f"BATCH RUN: {strategy_key} on {symbol}")
    logger.info("=" * 60)

    report_path = _BATCH_DIR / f"{strategy_key}_{symbol}.md"

    try:
        bars = read_bars(
            root=data_root, symbol=symbol, timeframe=source_tf, start=None, end=None
        )
        if bars.is_empty():
            raise RuntimeError(f"No bars found for {symbol} {source_tf}")
        if "symbol" not in bars.columns:
            bars = bars.with_columns(pl.lit(symbol).alias("symbol"))

        if target_tf is not None:
            logger.info(f"Resampling {source_tf} → {target_tf} ({bars.height} bars in)...")
            bars = _resample_to(bars, target_tf)
            logger.info(f"After resample: {bars.height} bars.")

        report_tf = target_tf or source_tf

        logger.info("Computing ATR(14)...")
        bars = atr(bars, period=14)

        logger.info(
            f"Walk-forward: train={train_months}mo / test={test_months}mo / step={step_months}mo, "
            f"fee={fee_model_name}..."
        )
        wf = run_walk_forward(
            bars,
            strategy_factory=strategy_cls,
            timeframe=report_tf,
            train_months=train_months,
            test_months=test_months,
            step_months=step_months,
            starting_equity=starting_equity,
            risk_per_trade=risk_per_trade,
            max_notional_pct=max_notional_pct,
            min_stop_pct=min_stop_pct,
            fee_model=FEE_MODELS[fee_model_name],
            symbol=symbol,
        )
        logger.info(
            f"WF done: {wf.n_windows} windows, mean Sharpe {wf.mean_sharpe:.2f}, "
            f"worst {wf.worst_window_sharpe:.2f}, {wf.total_trades} OOS trades."
        )

        logger.info(f"Monte Carlo ({mc_sims} sims) on aggregated OOS trades...")
        mc = run_monte_carlo(
            wf.all_oos_trades,
            starting_equity=starting_equity,
            n_simulations=mc_sims,
            seed=mc_seed,
        )
        logger.info(
            f"MC done: p05 ${mc.final_equity_p05:,.0f}, p50 ${mc.final_equity_p50:,.0f}, "
            f"p95 ${mc.final_equity_p95:,.0f}. {mc.pct_sims_profitable:.1f}% profitable."
        )

        # Combined per-pair report
        parts: list[str] = []
        parts.append(f"# {strategy_key} on {symbol}\n")
        parts.append(render_walk_forward_markdown(wf))
        parts.append("")
        parts.append(render_monte_carlo_markdown(mc))
        parts.append("")
        parts.append("## Combined verdict")
        g1_5_a = wf.passes_g1_5_no_negative_window()
        g1_5_b = wf.passes_g1_5_min_windows(3)
        g1_6 = mc.passes_g1_6_5th_pct_positive()
        overall = g1_5_a and g1_5_b and g1_6
        parts.append("")
        parts.append(f"- G1.5 walk-forward (no negative-Sharpe window): {'PASS' if g1_5_a else 'FAIL'}")
        parts.append(f"- G1.5 walk-forward (>=3 windows): {'PASS' if g1_5_b else 'FAIL'}")
        parts.append(f"- G1.6 Monte Carlo (5th-pctile final equity positive): {'PASS' if g1_6 else 'FAIL'}")
        parts.append("")
        parts.append(
            "**Overall G1.5 + G1.6: "
            + ("PASS — proceed to paper trading**" if overall else "FAIL — graveyard candidate**")
        )
        parts.append(f"\n_Fee model: {fee_model_name}_\n")

        report_path.write_text("\n".join(parts), encoding="utf-8")
        logger.info(f"Per-pair report: {report_path}")

        return PairResult(
            strategy=strategy_key,
            symbol=symbol,
            n_windows=wf.n_windows,
            mean_sharpe=wf.mean_sharpe,
            worst_window_sharpe=wf.worst_window_sharpe,
            total_oos_trades=wf.total_trades,
            mc_p05_final=mc.final_equity_p05,
            mc_p50_final=mc.final_equity_p50,
            mc_pct_profitable=mc.pct_sims_profitable,
            g1_5_no_neg_window=g1_5_a,
            g1_5_min_3_windows=g1_5_b,
            g1_6_p05_positive=g1_6,
            overall_pass=overall,
            report_path=report_path,
        )

    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        logger.error(f"FAILED: {strategy_key} on {symbol}: {exc}\n{tb}")
        report_path.write_text(
            f"# {strategy_key} on {symbol}\n\n**RUN FAILED**\n\n```\n{tb}\n```\n",
            encoding="utf-8",
        )
        return PairResult(
            strategy=strategy_key,
            symbol=symbol,
            n_windows=0,
            mean_sharpe=0.0,
            worst_window_sharpe=0.0,
            total_oos_trades=0,
            mc_p05_final=0.0,
            mc_p50_final=0.0,
            mc_pct_profitable=0.0,
            g1_5_no_neg_window=False,
            g1_5_min_3_windows=False,
            g1_6_p05_positive=False,
            overall_pass=False,
            report_path=report_path,
            error=str(exc),
        )


def _write_index(results: list[PairResult], *, fee_model_name: str) -> Path:
    """Write the ranked INDEX.md summarising all pairs."""
    index_path = _BATCH_DIR / "INDEX.md"

    # Sort: passing first, then by mean_sharpe desc
    ranked = sorted(
        results,
        key=lambda r: (-int(r.overall_pass), -r.mean_sharpe if r.error is None else 0),
    )

    lines: list[str] = []
    lines.append("# Strategy Batch Run — Ranked Index\n")
    lines.append(f"- Run timestamp: `{_STAMP}` UTC")
    lines.append(f"- Fee model: `{fee_model_name}`")
    lines.append(f"- Total pairs: {len(results)}")
    n_pass = sum(1 for r in results if r.overall_pass)
    n_err = sum(1 for r in results if r.error is not None)
    lines.append(f"- Passing G1.5 + G1.6: **{n_pass}**")
    lines.append(f"- Errored: {n_err}")
    lines.append("")
    lines.append("## Summary table\n")
    lines.append(
        "| # | Status | Strategy | Symbol | Windows | Mean Sharpe | Worst Sharpe | "
        "OOS Trades | MC p05 ($) | MC p50 ($) | % MC Profit | Report |"
    )
    lines.append(
        "|---|--------|----------|--------|---------|-------------|--------------|-"
        "-----------|------------|------------|-------------|--------|"
    )
    for i, r in enumerate(ranked, start=1):
        if r.error is not None:
            lines.append(
                f"| {i} | ERROR | {r.strategy} | {r.symbol} | - | - | - | - | - | - | - | "
                f"[log]({r.report_path.name}) |"
            )
        else:
            status_label = "PASS" if r.overall_pass else "FAIL"
            lines.append(
                f"| {i} | {status_label} | {r.strategy} | {r.symbol} | {r.n_windows} | "
                f"{r.mean_sharpe:.2f} | {r.worst_window_sharpe:.2f} | {r.total_oos_trades} | "
                f"{r.mc_p05_final:,.0f} | {r.mc_p50_final:,.0f} | {r.mc_pct_profitable:.1f}% | "
                f"[md]({r.report_path.name}) |"
            )

    lines.append("")
    lines.append("## What to do next\n")
    if n_pass == 0:
        lines.append(
            "**No candidate survived G1.5 + G1.6.** Expected outcome for the first batch — "
            "most well-documented retail strategies have decayed. Next steps:\n"
            "1. Look at the highest mean-Sharpe candidates (top of table). Even FAIL rows can "
            "tell us which patterns at least produce non-noise.\n"
            "2. Decide whether to (a) widen the candidate universe (more strategies / params / "
            "symbols), (b) loosen graduation criteria within reason, or (c) accept that this batch "
            "did not find tradeable edge and move to a different research direction.\n"
            "3. The lab DID work as designed — it caught {n_fail} strategies before any money "
            "moved.\n".format(n_fail=len(results) - n_err)
        )
    elif n_pass == 1:
        passer = next(r for r in ranked if r.overall_pass)
        lines.append(
            f"**One candidate survived: `{passer.strategy}` on `{passer.symbol}`.** Recommend:\n"
            f"1. Open `{passer.report_path.name}` and inspect the per-window detail.\n"
            f"2. Sanity-check: does the strategy logic actually make sense? Does the Sharpe come "
            f"from a few outlier trades or is it consistent?\n"
            f"3. If both check out → paper-trade for 30 days per ratified graduation criteria.\n"
        )
    else:
        lines.append(
            f"**{n_pass} candidates survived G1.5 + G1.6.** Recommend:\n"
            f"1. Review each passing report individually — pay attention to trade count "
            f"(too few = lucky), Sharpe consistency, drawdown profile.\n"
            f"2. Be skeptical: multiple-comparison correction would penalize {len(results)} tests. "
            f"Expect 1-2 false positives by chance alone.\n"
            f"3. Pick the most-defensible 1-2 to paper-trade. Don't deploy all of them at once.\n"
        )

    lines.append("")
    lines.append("## Per-pair report files\n")
    for r in ranked:
        lines.append(f"- [{r.strategy} on {r.symbol}]({r.report_path.name}) — {r.status}")

    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path


@click.command(context_settings={"show_default": True})
@click.option(
    "--fee-model",
    type=click.Choice(list(FEE_MODELS.keys())),
    default="alpaca_paper",
)
@click.option("--train-months", default=18, type=int)
@click.option("--test-months", default=6, type=int)
@click.option("--step-months", default=6, type=int)
@click.option("--starting-equity", default=100_000.0, type=float)
@click.option("--risk-per-trade", default=0.005, type=float)
@click.option("--max-notional-pct", default=1.0, type=float)
@click.option("--min-stop-pct", default=0.0005, type=float)
@click.option("--mc-sims", default=1000, type=int)
@click.option("--mc-seed", default=42, type=int)
@click.option("--only", default=None, type=str, help="Comma-separated strategy keys")
@click.option("--symbols", default=",".join(DEFAULT_SYMBOLS), type=str)
def main(
    fee_model: str,
    train_months: int,
    test_months: int,
    step_months: int,
    starting_equity: float,
    risk_per_trade: float,
    max_notional_pct: float,
    min_stop_pct: float,
    mc_sims: int,
    mc_seed: int,
    only: str | None,
    symbols: str,
) -> None:
    settings = get_settings()
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    if only:
        keep = {k.strip() for k in only.split(",")}
        registry = {k: v for k, v in STRATEGY_REGISTRY.items() if k in keep}
        if not registry:
            logger.error(f"--only filter matched no strategies. Available: {list(STRATEGY_REGISTRY)}")
            sys.exit(1)
    else:
        registry = STRATEGY_REGISTRY

    pairs = [(k, v[0], sym, v[1], v[2]) for k, v in registry.items() for sym in symbol_list]
    logger.info(f"Batch: {len(pairs)} pairs ({len(registry)} strategies × {len(symbol_list)} symbols)")
    logger.info(f"Symbols: {symbol_list}")
    logger.info(f"Strategies: {list(registry.keys())}")

    results: list[PairResult] = []
    for strategy_key, strategy_cls, symbol, source_tf, target_tf in pairs:
        result = _run_one(
            strategy_key=strategy_key,
            strategy_cls=strategy_cls,
            symbol=symbol,
            source_tf=source_tf,
            target_tf=target_tf,
            train_months=train_months,
            test_months=test_months,
            step_months=step_months,
            starting_equity=starting_equity,
            risk_per_trade=risk_per_trade,
            max_notional_pct=max_notional_pct,
            min_stop_pct=min_stop_pct,
            fee_model_name=fee_model,
            mc_sims=mc_sims,
            mc_seed=mc_seed,
            data_root=settings.alpha_data_root,
        )
        results.append(result)
        logger.info(f"  → {result.status}: mean_sharpe={result.mean_sharpe:.2f}")

    index_path = _write_index(results, fee_model_name=fee_model)
    logger.info("=" * 60)
    logger.info(f"BATCH COMPLETE. {sum(1 for r in results if r.overall_pass)}/{len(results)} passed.")
    logger.info(f"Ranked index: {index_path}")
    logger.info(f"All reports under: {_BATCH_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
