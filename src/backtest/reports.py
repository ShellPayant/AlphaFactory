"""Markdown report generator for a single backtest run.

Reads a ``BacktestResult`` + a metrics dict, produces a Markdown report
that includes:

* Strategy + config summary
* Headline metrics (return, Sharpe, drawdown, etc.)
* Trade stats (win rate, profit factor, expectancy)
* Per-regime P&L table
* Exit reason breakdown
* Top-5 best and worst trades
* The first 10 and last 10 trades for spot-checking

The full trade log is also written as Parquet alongside the report so it
can be re-analyzed without re-running the backtest.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from .metrics import all_metrics, regime_slice
from .research_engine import BacktestResult


def _fmt_money(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.2f}"


def _fmt_pct(v: float) -> str:
    return f"{v:+.2f}%"


def _trade_to_row(t) -> dict:  # type: ignore[no-untyped-def]
    return {
        "entry_ts": t.entry_ts,
        "exit_ts": t.exit_ts,
        "side": t.side,
        "shares": t.shares,
        "entry": round(t.entry_price, 4),
        "exit": round(t.exit_price, 4),
        "pnl": round(t.pnl, 2),
        "pnl_pct": round(t.pnl_pct, 4),
        "bars": t.bars_held,
        "exit_reason": t.exit_reason,
        "regime": t.regime_tag,
    }


def _trades_df(trades: list) -> pl.DataFrame:  # type: ignore[type-arg]
    if not trades:
        return pl.DataFrame()
    return pl.DataFrame([_trade_to_row(t) for t in trades])


def render_markdown(result: BacktestResult, *, timeframe: str = "5Min") -> str:
    """Render the full report as a Markdown string."""
    m = all_metrics(result, timeframe=timeframe)
    ts = m["trade_stats"]
    es = m["equity_stats"]
    rs = regime_slice(result.trades)

    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines: list[str] = []
    lines.append(f"# Backtest Report — `{result.strategy_name}` on `{result.symbol}`")
    lines.append("")
    lines.append(f"_Generated {now}_")
    lines.append("")
    lines.append("## Configuration")
    lines.append("")
    lines.append("| Setting | Value |")
    lines.append("|---|---|")
    lines.append(f"| Strategy | `{result.strategy_name}` |")
    lines.append(f"| Symbol | `{result.symbol}` |")
    lines.append(f"| Timeframe | `{timeframe}` |")
    lines.append(f"| Starting equity | {_fmt_money(result.starting_equity)} |")
    lines.append(f"| Ending equity | {_fmt_money(result.ending_equity)} |")
    lines.append(
        f"| Fee model | "
        f"slippage={result.fee_model.slippage_bps_per_side} bps/side, "
        f"commission/share={result.fee_model.commission_per_share} |"
    )
    for k, v in result.config_used.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Total return | {_fmt_pct(es['total_return_pct'])} |")
    lines.append(f"| CAGR | {_fmt_pct(es['cagr_pct'])} |")
    lines.append(f"| Sharpe (annualized) | {es['sharpe']:.2f} |")
    lines.append(f"| Sortino (annualized) | {es['sortino']:.2f} |")
    lines.append(f"| Max drawdown | {_fmt_pct(es['max_drawdown_pct'])} |")
    lines.append(f"| Time under water | {es['time_under_water_pct']:.1f}% |")
    lines.append(f"| Bars in backtest | {es['n_bars']:,} |")
    lines.append("")

    lines.append("## Trade statistics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Trades | {ts['n_trades']} |")
    lines.append(f"| Signals generated | {result.signals_generated} |")
    lines.append(f"| Signals skipped (sizing) | {result.signals_skipped_by_sizing} |")
    lines.append(f"| Signals skipped (max notional cap) | {result.signals_skipped_by_max_notional} |")
    lines.append(f"| Signals skipped (min stop guard) | {result.signals_skipped_by_min_stop} |")
    lines.append(f"| Win rate | {ts['win_rate']*100:.1f}% |")
    lines.append(f"| Avg win | {_fmt_money(ts['avg_win'])} |")
    lines.append(f"| Avg loss | {_fmt_money(ts['avg_loss'])} |")
    pf = ts["profit_factor"]
    pf_str = "∞" if pf == float("inf") else f"{pf:.2f}"
    lines.append(f"| Profit factor | {pf_str} |")
    lines.append(f"| Expectancy / trade | {_fmt_money(ts['expectancy'])} |")
    lines.append(f"| Avg bars held | {ts['avg_bars_held']:.1f} |")
    lines.append(f"| Max consec. wins / losses | {ts['max_consecutive_wins']} / {ts['max_consecutive_losses']} |")
    lines.append(f"| Best trade | {_fmt_money(ts['best_trade'])} |")
    lines.append(f"| Worst trade | {_fmt_money(ts['worst_trade'])} |")
    lines.append("")

    lines.append("## Exit reason breakdown")
    lines.append("")
    if m["exit_reasons"]:
        lines.append("| Reason | Count |")
        lines.append("|---|---|")
        for k, v in sorted(m["exit_reasons"].items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("_No trades._")
    lines.append("")

    lines.append("## P&L by regime")
    lines.append("")
    if rs.height > 0:
        lines.append("| Regime | Trades | Total P&L | Win rate |")
        lines.append("|---|---:|---:|---:|")
        for row in rs.iter_rows(named=True):
            lines.append(
                f"| `{row['quant_regime']}` | {row['n_trades']} | "
                f"{_fmt_money(row['total_pnl'])} | {row['win_rate']*100:.1f}% |"
            )
    else:
        lines.append("_No trades._")
    lines.append("")

    trades_df = _trades_df(result.trades)
    if trades_df.height > 0:
        lines.append("## Best 5 trades")
        lines.append("")
        best5 = trades_df.sort("pnl", descending=True).head(5)
        lines.append(_df_to_md_table(best5))
        lines.append("")
        lines.append("## Worst 5 trades")
        lines.append("")
        worst5 = trades_df.sort("pnl").head(5)
        lines.append(_df_to_md_table(worst5))
        lines.append("")
        lines.append("## First 10 trades")
        lines.append("")
        lines.append(_df_to_md_table(trades_df.head(10)))
        lines.append("")
        lines.append("## Last 10 trades")
        lines.append("")
        lines.append(_df_to_md_table(trades_df.tail(10)))
        lines.append("")

    return "\n".join(lines)


def _df_to_md_table(df: pl.DataFrame) -> str:
    if df.is_empty():
        return "_(empty)_"
    cols = df.columns
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for row in df.iter_rows():
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def write_report(
    result: BacktestResult,
    out_dir: Path,
    *,
    timeframe: str = "5Min",
    label: str | None = None,
) -> dict[str, Path]:
    """Write report + trade log + equity curve. Returns paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"{result.strategy_name}_{result.symbol}_{stamp}"
    if label:
        base = f"{base}_{label}"

    report_path = out_dir / f"{base}.md"
    trades_path = out_dir / f"{base}_trades.parquet"
    equity_path = out_dir / f"{base}_equity.parquet"

    report_path.write_text(render_markdown(result, timeframe=timeframe), encoding="utf-8")

    trades_df = _trades_df(result.trades)
    if trades_df.height > 0:
        trades_df.write_parquet(trades_path)
    if result.equity_curve.height > 0:
        result.equity_curve.write_parquet(equity_path)

    return {"report": report_path, "trades": trades_path, "equity": equity_path}
