# AlphaFactory — System Design

## Goal

A modular research → paper → live trading lab for US equities. The system must make it hard to deploy unvalidated strategies, hard to violate risk policy, and easy to diagnose why any trade was taken.

## Non-goals

- Not an AI auto-trader. AI assists with code, audit, and reporting only.
- Not a universal multi-asset platform (yet). US equities first.
- Not a high-frequency or latency-sensitive system. Bar-based, end-of-bar decisions, seconds-to-minutes latency budget.

## Architectural principles

1. **Backtest = live code path.** Every strategy is a Nautilus `Strategy` subclass. The same class runs in the backtester and against the live broker. No "live wrapper" that diverges from the backtested version.
2. **Risk is enforced by the system, not by the strategy.** Strategies emit *signals*; the risk engine converts signals to orders (or rejects them). A strategy cannot bypass the risk engine.
3. **Every signal and every trade is tagged with regime.** Regime tags travel with the trade through the journal and into reports. Performance is always sliced by regime.
4. **No hidden global state.** All config comes from YAML + `.env`. All state is in the database or in-memory inside a single Nautilus `BacktestEngine` / `LiveNode`.
5. **Small files. Pure functions where possible.** Indicators and regime classifiers are pure functions over Polars DataFrames so they can be unit-tested without an engine.

## Stack rationale

| Choice                          | Why                                                                                |
|---------------------------------|-------------------------------------------------------------------------------------|
| **Nautilus Trader** (engine)    | Backtest=live equivalence. Rust core, fast event loop. Has Alpaca + IBKR adapters. |
| **Polars** (features)           | 10–50× faster than pandas on wide bar data, lazy execution, no SettingWithCopy.    |
| **DuckDB + Parquet** (storage)  | Zero-ops, fast analytical queries over historical bars. Easy to back up.           |
| **Polygon** (data)              | Reliable US equities intraday + historical. Survivorship-bias-aware on request.    |
| **Alpaca** (broker, first)      | Free paper trading API, fractional shares, decent fills. Easy to swap to IBKR.     |
| **uv** (deps)                   | 10–100× faster than pip. Reproducible lockfile. Replaces venv + pip + pip-tools.   |
| **pydantic v2 + YAML** (config) | Strict typed config with validation. Catches bad configs at boot.                  |

## Data flow

```
                         ┌──────────────┐
                         │  Polygon API │
                         └──────┬───────┘
                                │ bars (OHLCV, trade-conditions)
                                ▼
                  ┌──────────────────────────┐
                  │   data/ingestion         │
                  │  fetch_ohlcv.py          │
                  │  + data_quality_checks   │
                  └────────────┬─────────────┘
                               │ Parquet partitions (symbol/timeframe/date)
                               ▼
                  ┌──────────────────────────┐
                  │   data/storage           │
                  │  parquet_store + duckdb  │
                  └────────────┬─────────────┘
                               │ DataFrame
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
       features/     regimes/            backtest/
       (ATR/ADX/VWAP)   (quant+categorical)   (Nautilus runner)
                                              │
                                              ▼
                                        Strategy subclass
                                              │ signals
                                              ▼
                                       risk/ (sizing, caps, kill switch)
                                              │ approved orders
                                              ▼
                                       execution/ (Nautilus exec engine)
                                              │ fills
                                              ▼
                                       journal/ + monitoring/
```

## Module responsibilities

### `data/`
- **connectors/** — thin Polygon + Alpaca clients with retry, rate-limit, and auth.
- **ingestion/** — fetch_ohlcv.py is the only entry point for historical pulls. Writes to Parquet partitioned `symbol/timeframe/date.parquet`.
- **storage/** — `parquet_store.py` (writer), `duckdb_store.py` (query interface returning Polars).
- **validation/** — gap detection, duplicate timestamps, impossible OHLC (high<low, etc.), volume spikes, timezone consistency. Run after every ingestion.

### `features/`
Pure Polars functions. Input: `pl.DataFrame` with columns `[ts, open, high, low, close, volume]` (UTC, sorted). Output: input DataFrame with appended indicator column(s). **No lookahead.** Property-tested.

### `regimes/`
- **Quant classifier:** ADX bucket × ATR-percentile bucket = 9-cell regime grid per bar.
- **Categorical classifier:** one of `{consolidating, directional, chaotic}` per bar, based on structure highs/lows, range width vs ATR, slope, VWAP position.
- Both produce a `regime_tag` column that travels with every signal.

### `strategies/`
- Each strategy is two things: a **strategy spec** (Markdown, fills `docs/strategy_spec_template.md`) and a **Nautilus `Strategy` subclass** that implements it. Specs are reviewed before code.
- Strategies emit `Signal(side, entry, stop, target, invalidation, regime_required, expected_duration)` rather than orders directly.

### `risk/`
- **pre_trade_checks.py** — every order passes through here. Rejects if: open positions > cap, daily loss > cap, correlated exposure > cap, stale data, kill switch armed.
- **position_sizing.py** — ATR-based sizing such that `account_equity × max_risk_per_trade / (entry - stop)` shares.
- **kill_switch.py** — file-flag + in-memory toggle. Triggers on broker mismatch, data staleness, daily loss exceeded, duplicate orders, manual.

### `backtest/`
- Thin wrappers over Nautilus `BacktestEngine`. Hands data + strategy + risk config in, gets `BacktestResult` out.
- **walk_forward.py** — splits date range into train/test windows, runs Nautilus per window, aggregates degradation metrics.
- **reports.py** — produces per-strategy report with all metrics and regime slicing.

### `execution/`
- **order_manager.py** — single chokepoint for emitting orders to the Nautilus exec engine. Logs every emit and every fill.
- **reconciliation.py** — daily diff between expected positions (from journal) and broker positions. Mismatch → alert + kill switch.

### `monitoring/`
- **dashboard.py** — Streamlit page: equity curve, open positions, today's signals (fired + rejected), risk usage, slippage.
- **alerts.py** — log + email/push on: data staleness > N minutes, broker mismatch, kill switch armed, daily loss > 50% of cap.

### `journal/`
- **trade_logger.py** — every signal (accepted + rejected), every order, every fill, every exit, with regime tag and reason string.
- **weekly_review.py** — generates a weekly Markdown report: performance vs expected, slippage delta, override count, regime accuracy.
- **strategy_graveyard.py** — append-only Markdown log of rejected/retired strategies, with the specific reason and the data window that failed.

## Backtest correctness contract

Every backtest run must:

1. Use **next-bar execution** (signal at bar T → fill at bar T+1 open or limit/stop level inside T+1).
2. Include fees and slippage by default (slippage modeled as a fixed multiple of bar ATR or spread).
3. Refuse to run if any indicator function references future bars (enforced by `test_backtest_no_lookahead.py`).
4. Tag every trade with the regime active at the entry bar.
5. Export both a machine-readable trade log (Parquet) and a human-readable report (Markdown + HTML).

## Promotion gates

A strategy moves from research → paper → live only after:

- **Research → Paper:** ≥100 trades in backtest, walk-forward OOS degradation ≤40%, profitable after fees+slippage, regime slicing shows P&L is not concentrated in a single regime (unless explicitly gated to one), Monte Carlo trade-order reshuffle keeps Sharpe ≥50% of base case.
- **Paper → Live:** ≥30 trading days paper, no critical execution bugs, slippage within 2× backtest assumption, daily reconciliation clean, kill switches tested.
- **Live scale-up:** 30+ live trades within expected drawdown band, no manual overrides, weekly review signed off.

Strategies that fail any gate go to `journal/strategy_graveyard.md` with the failure reason — never silently dropped.

## What we explicitly delegate to Nautilus (not custom code)

- Event loop and clock
- Order book / fill simulation
- Broker adapter (Alpaca paper + live, IBKR later)
- Position tracking and P&L accounting
- Backtest engine
- Live data feed handlers

## What is explicitly custom

- Regime classifier (the most differentiated piece)
- Risk engine and kill switches (we want full control over what blocks an order)
- Strategy specs and the spec-to-code review process
- Reports and journals (we want our own format)
- Data pipeline (Polygon-specific QA)
