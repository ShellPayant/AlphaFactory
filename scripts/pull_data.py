"""Ingest historical bars from Alpaca into the local Parquet store.

Usage::

    python scripts/pull_data.py SPY --timeframe 5Min --start 2020-01-01 --end 2025-12-31
    python scripts/pull_data.py SPY QQQ --timeframe 1Day

Or via the matching double-click .bat file: ``scripts/pull_data.bat``.

What it does:

1. Fetches bars for each symbol × timeframe from Alpaca.
2. Runs data quality checks (gaps, dupes, impossible OHLC, etc.).
3. Writes month-partitioned Parquet files under ``data/bars/SYMBOL/TIMEFRAME/``.
4. Prints a summary of what landed.

This script is the only entry point for historical pulls. Strategies and
backtests read from the Parquet store, never call Alpaca directly.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import click
from loguru import logger

# Make `src.` imports work when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import get_settings  # noqa: E402
from src.data.connectors.alpaca_client import AlpacaHistoricalClient, Timeframe  # noqa: E402
from src.data.storage.parquet_store import write_bars  # noqa: E402
from src.data.validation.data_quality_checks import validate  # noqa: E402


def _parse_date(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)


@click.command(context_settings={"show_default": True})
@click.argument("symbols", nargs=-1, required=True)
@click.option(
    "--timeframe",
    type=click.Choice(list(get_args(Timeframe))),
    default="5Min",
    help="Bar timeframe.",
)
@click.option(
    "--start",
    type=str,
    default="2020-01-01",
    help="Inclusive start date, YYYY-MM-DD (UTC).",
)
@click.option(
    "--end",
    type=str,
    default=None,
    help="Inclusive end date, YYYY-MM-DD (UTC). Defaults to today.",
)
@click.option(
    "--feed",
    type=click.Choice(["iex", "sip"]),
    default="iex",
    help="iex is free; sip needs a paid market data subscription.",
)
@click.option(
    "--fail-on-qa",
    is_flag=True,
    default=False,
    help="If set, abort write when QA fails. Default: write anyway and warn.",
)
def main(
    symbols: tuple[str, ...],
    timeframe: str,
    start: str,
    end: str | None,
    feed: str,
    fail_on_qa: bool,
) -> None:
    """Pull bars for SYMBOLS (one or more tickers) into the Parquet store."""
    settings = get_settings()
    settings.require_alpaca_paper_keys()

    start_dt = _parse_date(start)
    end_dt = _parse_date(end) if end else datetime.now(tz=timezone.utc)

    client = AlpacaHistoricalClient(settings)
    root = settings.alpha_data_root

    overall_ok = True
    for symbol in symbols:
        symbol_u = symbol.upper()
        logger.info("=== {} {} {} → {} ===", symbol_u, timeframe, start, end or "today")

        try:
            df = client.get_bars(
                symbol_u, timeframe, start_dt, end_dt,  # type: ignore[arg-type]
                feed=feed,  # type: ignore[arg-type]
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Fetch failed for {}: {}", symbol_u, e)
            overall_ok = False
            continue

        if df.is_empty():
            logger.warning("No bars returned for {}", symbol_u)
            continue

        report = validate(df, symbol=symbol_u, timeframe=timeframe)
        logger.info(report.summary())
        if not report.passed:
            overall_ok = False
            if fail_on_qa:
                logger.error("QA failed and --fail-on-qa set; skipping write for {}", symbol_u)
                continue

        written = write_bars(df, root=root, symbol=symbol_u, timeframe=timeframe)
        logger.info("Wrote {} monthly partitions for {}", len(written), symbol_u)

    if not overall_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
