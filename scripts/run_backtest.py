"""Run a strategy backtest end-to-end and write the report.

Usage::

    python scripts/run_backtest.py --strategy range_mean_reversion --symbol SPY \
        --timeframe 5Min --start 2023-01-01 --end 2024-12-31

    python scripts/run_backtest.py --strategy intraday_momentum_spy --symbol SPY \
        --fee-model pessimistic

Or via the double-click ``scripts/run_backtest.bat`` (uses defaults).
"""

from __future__ import annotations

import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import click
import polars as pl
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest import ALPACA_PAPER, run_backtest, write_report  # noqa: E402
from src.backtest.fees import PESSIMISTIC  # noqa: E402
from src.config.settings import get_settings  # noqa: E402
from src.data.storage.parquet_store import read_bars  # noqa: E402
from src.features.adx import adx  # noqa: E402
from src.features.atr import atr  # noqa: E402
from src.features.vwap import session_vwap  # noqa: E402
from src.regimes.regime_classifier import classify_regimes  # noqa: E402
from src.strategies import IntradayMomentumSPY, RangeMeanReversion  # noqa: E402

# (strategy_name) -> (strategy_class, source_timeframe, target_timeframe_for_resample_or_None)
# source_timeframe is what we read from the Parquet store; target is what the
# strategy actually wants. None means "use bars as-is, no resample."
STRATEGY_REGISTRY = {
    "range_mean_reversion": (RangeMeanReversion, "5Min", None),
    "intraday_momentum_spy": (IntradayMomentumSPY, "5Min", "30m"),
}

FEE_MODELS = {
    "alpaca_paper": ALPACA_PAPER,
    "pessimistic": PESSIMISTIC,
}


def _resample_to(bars: pl.DataFrame, period: str) -> pl.DataFrame:
    """Resample OHLCV bars to a larger period, aligned per US session.

    Uses NY session date as the group boundary so 30-min bars never span
    across days. Within a session, ``group_by_dynamic`` with the requested
    period aligns to the first bar of the session (i.e. 09:30 ET for RTH).
    """
    if bars.is_empty():
        return bars
    ts_local_date = (
        pl.col("ts").dt.convert_time_zone("America/New_York").dt.date()
    )
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
    default="range_mean_reversion",
)
@click.option("--symbol", default="SPY")
@click.option(
    "--timeframe",
    default=None,
    help="Override source timeframe to load from Parquet. Default: per-strategy.",
)
@click.option("--start", default=None, help="YYYY-MM-DD (inclusive). Default: all data.")
@click.option("--end", default=None, help="YYYY-MM-DD (inclusive). Default: all data.")
@click.option("--starting-equity", default=100_000.0, type=float)
@click.option("--risk-per-trade", default=0.0025, type=float, help="Fraction of equity (0.0025 = 0.25%).")
@click.option(
    "--fee-model",
    type=click.Choice(list(FEE_MODELS.keys())),
    default="alpaca_paper",
    help="alpaca_paper = 1bp slippage, free commission. pessimistic = 3bps + $0.005/share.",
)
@click.option(
    "--max-notional-pct",
    default=1.0,
    type=float,
    help="Position size cap as fraction of equity. 1.0 = no leverage.",
)
@click.option(
    "--min-stop-pct",
    default=0.0005,
    type=float,
    help="Minimum stop distance as fraction of entry price. Default 5 bps.",
)
@click.option(
    "--out-dir",
    default="reports",
    type=click.Path(path_type=Path),
    help="Directory for report + trade log + equity curve.",
)
def main(
    strategy: str,
    symbol: str,
    timeframe: str | None,
    start: str | None,
    end: str | None,
    starting_equity: float,
    risk_per_trade: float,
    fee_model: str,
    max_notional_pct: float,
    min_stop_pct: float,
    out_dir: Path,
) -> None:
    settings = get_settings()

    # Persist a per-run log file alongside the report so we never lose
    # terminal output when the .bat window closes on keypress (see gotcha
    # in PROJECT_CONTEXT.md Section 7).
    from datetime import datetime as _dt
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"_run_{_dt.utcnow().strftime('%Y%m%d_%H%M%S')}_{strategy}_{symbol}.log"
    logger.add(str(log_path), level="INFO")
    logger.info("Run log: {}", log_path)

    strat_cls, source_tf, target_tf = STRATEGY_REGISTRY[strategy]
    load_tf = timeframe or source_tf

    logger.info("Loading bars: {} {} {} → {}", symbol, load_tf, start or "*", end or "*")
    bars = read_bars(
        root=settings.alpha_data_root,
        symbol=symbol,
        timeframe=load_tf,
        start=start,
        end=end,
    )
    if bars.is_empty():
        logger.error(
            "No bars found for {} {} in {}. Did you run scripts/pull_data.py?",
            symbol,
            load_tf,
            settings.alpha_data_root / "bars",
        )
        sys.exit(1)

    if "symbol" not in bars.columns:
        bars = bars.with_columns(pl.lit(symbol).alias("symbol"))

    if target_tf is not None:
        logger.info("Resampling {} → {} ({} bars in)...", load_tf, target_tf, bars.height)
        bars = _resample_to(bars, target_tf)
        logger.info("After resample: {} bars.", bars.height)

    logger.info("Loaded {} bars. Computing indicators + regimes...", bars.height)
    bars = atr(bars, period=14)
    bars = adx(bars, period=14)
    bars = session_vwap(bars)
    bars = classify_regimes(bars)

    report_timeframe = target_tf or load_tf

    logger.info("Running backtest...")
    result = run_backtest(
        bars,
        strat_cls(),
        starting_equity=starting_equity,
        risk_per_trade=risk_per_trade,
        max_notional_pct=max_notional_pct,
        min_stop_pct=min_stop_pct,
        fee_model=FEE_MODELS[fee_model],
    )

    logger.info(
        "Done. {} trades, ending equity {:.2f} ({:+.2f}%).",
        result.n_trades,
        result.ending_equity,
        result.total_return_pct,
    )

    paths = write_report(result, out_dir, timeframe=report_timeframe)
    logger.info("Report:  {}", paths["report"])
    if "trades" in paths and paths["trades"].exists():
        logger.info("Trades:  {}", paths["trades"])
    if "equity" in paths and paths["equity"].exists():
        logger.info("Equity:  {}", paths["equity"])


if __name__ == "__main__":
    main()
