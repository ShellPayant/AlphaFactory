"""Smoke-test the new macro overlay + IsolationForest data-QA layers.

Runs end-to-end on real SPY bars in the local Parquet store and prints:

  1. GARCH(1,1) macro volatility regime — counts per regime, recent N days
     of tags, sanity-checks vs. raw close-to-close vol bursts.
  2. IsolationForest data-quality anomaly detection — flag rate, sample
     timestamps of the most-anomalous bars.

Run via ``scripts/run_macro_smoke.bat`` or directly::

    uv run python scripts/run_macro_smoke.py --symbol SPY --timeframe 5Min
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import polars as pl
from loguru import logger

# Force UTF-8 stdout so Polars' box-drawing chars survive the Windows console
# (default cp1252 → UnicodeEncodeError on print(df)).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---- In-Python tee so the .bat doesn't need PowerShell. ----------------
class _Tee:
    """Mirror writes to two streams (console + log file)."""

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


_REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = _REPORTS_DIR / (
    "_macro_smoke_" + datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S") + ".log"
)
_LOG_FILE = open(_LOG_PATH, "w", encoding="utf-8")  # noqa: SIM115
sys.stdout = _Tee(sys.stdout, _LOG_FILE)  # type: ignore[assignment]
sys.stderr = _Tee(sys.stderr, _LOG_FILE)  # type: ignore[assignment]
print(f"[tee] Mirroring all output to: {_LOG_PATH}")

from src.config.settings import get_settings  # noqa: E402
from src.data.storage.parquet_store import read_bars  # noqa: E402
from src.data.validation import (  # noqa: E402
    flag_anomalies_unsupervised,
    validate,
)
from src.regimes import classify_volatility_regime, latest_regime  # noqa: E402


@click.command(context_settings={"show_default": True})
@click.option("--symbol", default="SPY")
@click.option("--timeframe", default="5Min")
@click.option("--contamination", default=0.005, type=float)
def main(symbol: str, timeframe: str, contamination: float) -> None:
    settings = get_settings()

    logger.info("Loading {} {} from local store...", symbol, timeframe)
    bars = read_bars(
        root=settings.alpha_data_root,
        symbol=symbol,
        timeframe=timeframe,
        start=None,
        end=None,
    )
    if bars.is_empty():
        logger.error("No bars found for {} {}. Run pull_data.bat first.", symbol, timeframe)
        sys.exit(1)

    if "symbol" not in bars.columns:
        bars = bars.with_columns(pl.lit(symbol).alias("symbol"))

    logger.info("Loaded {} bars from {} to {}.", bars.height, bars["ts"].min(), bars["ts"].max())

    # ---- Rule-based QA (existing) ----
    rb = validate(bars, symbol=symbol, timeframe=timeframe)
    logger.info(rb.summary())

    # ---- 1. Macro volatility regime (GARCH) ----
    print()
    print("=" * 72)
    print(" MACRO VOLATILITY REGIME — GARCH(1,1)")
    print("=" * 72)

    daily_regime = classify_volatility_regime(bars)
    n_days = daily_regime.height
    print(f"Daily observations: {n_days}")
    print()
    print("Vol-regime counts (excluding warmup):")
    counts = (
        daily_regime.filter(pl.col("vol_regime").is_not_null())
        .group_by("vol_regime")
        .len()
        .sort("vol_regime")
    )
    print(counts)
    print()

    print("Last 20 trading days — date, daily_return, cond_vol, vol_regime:")
    tail = daily_regime.tail(20).select(
        "date",
        pl.col("daily_return").round(5),
        pl.col("cond_vol").round(3),
        "vol_regime",
    )
    print(tail)
    print()

    d, r = latest_regime(daily_regime)
    print(f"Latest classified day: {d} → vol_regime = {r}")
    print()

    # Sanity check: highest cond-vol days should cluster around real
    # vol events (e.g. SPX selloffs)
    print("Top 10 highest cond-vol days observed:")
    top = (
        daily_regime.filter(pl.col("cond_vol").is_not_null())
        .sort("cond_vol", descending=True)
        .head(10)
        .select(
            "date",
            pl.col("daily_return").round(5),
            pl.col("cond_vol").round(3),
            "vol_regime",
        )
    )
    print(top)
    print()

    # ---- 2. IsolationForest data-QA ----
    print("=" * 72)
    print(" UNSUPERVISED ANOMALY DETECTION — IsolationForest")
    print("=" * 72)

    tagged, anom = flag_anomalies_unsupervised(
        bars,
        symbol=symbol,
        timeframe=timeframe,
        contamination=contamination,
    )
    print(anom.summary())
    print()

    if anom.n_flagged > 0:
        print(f"Top 10 most-anomalous bars (lowest decision_function score):")
        flagged = (
            tagged.filter(pl.col("iso_anomaly"))
            .sort("iso_anomaly_score")
            .head(10)
            .select(
                "ts",
                pl.col("open").round(3),
                pl.col("high").round(3),
                pl.col("low").round(3),
                pl.col("close").round(3),
                "volume",
                pl.col("iso_anomaly_score").round(4),
            )
        )
        print(flagged)
        print()

    print("=" * 72)
    print(" SMOKE TEST DONE")
    print("=" * 72)


if __name__ == "__main__":
    main()
