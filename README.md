# AlphaFactory

![Status](https://img.shields.io/badge/status-Phase_3_·_engine_hardening-1F6FEB?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/tests-passing-238636?style=flat-square)
![Process](https://img.shields.io/badge/AI-codes·not_trades-DAA520?style=flat-square)
![License](https://img.shields.io/badge/license-Private-8B0000?style=flat-square)

A systematic algo trading **research, validation, paper-trading, risk, and execution lab** for US equities. Not a black-box AI trader. Not a strategy. A **search system** that hunts edges, kills bad ones early, and graduates the survivors through pre-defined gates.

> **Lab status:** working as designed. Two strategies tested, both correctly graveyard'd on first contact — *zero real money risked*. The fact that this repo's first two backtests both **failed** is the point: the lab kills bad specs before they kill you.

### 🔗 [Live overview — how we think, how it's built →](https://shellpayant.github.io/AlphaFactory/)

*Interactive infographic walking through the four philosophy pivots, seven non-negotiable guardrails, the five-stage pipeline with its three gates, and the bought-vs-built tech stack.*

## Philosophy

1. **Process > result.** A good trade that loses is fine. A bad trade that wins is bad process.
2. **Risk > entry.** Sizing, stops, and kill switches matter more than signal cleverness.
3. **Regime-aware.** A strategy is not universally good or bad. It is good or bad in a specific regime.
4. **Backtests lie by default.** Control for overfitting, regime drift, fees, slippage, survivorship, lookahead.
5. **AI codes. AI does not trade.** AI implements, tests, audits, summarizes. Humans approve order routing.

## Architecture (hybrid)

The execution and backtest engine is **[Nautilus Trader](https://nautilustrader.io/)** — an open-source, Rust-core, event-driven platform that runs the *same code path* in backtest and live. This eliminates an entire class of "backtest worked, live broke" bugs and saves us from building a custom backtester and broker adapter layer.

Custom code in this repo focuses on the *differentiated* parts of the system:

| Module               | What it owns                                                  |
|----------------------|---------------------------------------------------------------|
| `src/data`           | Polygon → Parquet ingestion, DuckDB query layer, QA           |
| `src/features`       | ATR, ADX, VWAP, anchored VWAP, volume profile — Polars-native |
| `src/regimes`        | Quant (ADX×ATR) + categorical regime classifiers              |
| `src/strategies`     | Strategy specs, wired as Nautilus `Strategy` subclasses       |
| `src/risk`           | Position sizing, portfolio caps, pre-trade checks, kill switch |
| `src/backtest`       | Nautilus runner wrappers, walk-forward harness, reports       |
| `src/execution`      | Order manager, broker reconciliation                          |
| `src/monitoring`     | Daily/weekly reports, alerts, Streamlit dashboard             |
| `src/journal`        | Trade log, bias detector, strategy graveyard                  |

## Stack

- Python 3.12, [uv](https://github.com/astral-sh/uv) for dependency management
- Nautilus Trader (backtest + live engine)
- Polars + pandas + DuckDB + Parquet (data)
- Polygon (US equities data, ~$200/mo Stocks Developer tier)
- Alpaca (paper trading; IBKR upgrade later)
- FastAPI + Streamlit (dashboards)
- pytest, ruff, mypy strict (code quality)

## Quick start

```bash
# 1. Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and install
cd alpha_factory
uv sync --extra dev

# 3. Configure environment
cp .env.example .env
# fill in POLYGON_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY

# 4. Run tests
make test

# 5. Quality gate (lint + typecheck + fast tests)
make check
```

## Repo layout

```
alpha_factory/
├── src/
│   ├── config/        # YAML configs + pydantic settings
│   ├── data/          # connectors, ingestion, storage, validation
│   ├── features/      # ATR, ADX, VWAP, indicators
│   ├── regimes/       # quant + categorical regime classifiers
│   ├── strategies/    # strategy specs + Nautilus Strategy subclasses
│   ├── backtest/      # walk-forward harness, reports, metrics
│   ├── risk/          # sizing, limits, kill switch, pre-trade checks
│   ├── execution/     # order manager, reconciliation
│   ├── monitoring/    # daily/weekly reports, dashboards, alerts
│   └── journal/       # trade log, bias detector, graveyard
├── tests/
├── notebooks/         # exploratory research
└── docs/
    ├── system_design.md
    ├── risk_policy.md
    └── strategy_spec_template.md
```

## Backtests & lessons

Two strategies have run end-to-end through the lab. **Both were graveyard'd.** That's not a bug — it's the design. Below: the verdicts, the key numbers, and what each failure taught us. The full reports are in [`reports/`](./reports/).

### Tested so far

| Strategy | Timeframe | Verdict | Headline | Why it died |
|---|---|---|---|---|
| **Range Mean Reversion** | 5-min SPY · 2020-2026 | ☠ Graveyard | 4 trades over 123,319 bars, Sharpe -0.16 | Spec too restrictive — fired ~0.8 signals/year. Sample too small to evaluate, let alone trade. |
| **Intraday Momentum SPY** | 30-min SPY · 2020-2026 | ☠ Graveyard | 901 trades, **-60.2%** total return, Sharpe -12.0 | Designed for leverage we don't allow (40% of signals blocked by 1× notional cap) · brutal fee sensitivity at tight stops · no regime where edge beats cost. |

Detailed reports: [Range MR full backtest](./reports/range_mean_reversion_SPY_20260525_042616.md) · [Intraday Momentum full backtest](./reports/intraday_momentum_spy_SPY_20260525_052417.md)

### What we learned

1. **Signal frequency is a pre-filter, not a discovery.** A strategy that produces 4 signals in 5 years isn't *"selective"* — it's untestable. New specs now carry an expected-signals-per-year estimate before any code gets written. If the estimate is <30, the spec gets rewritten or shelved.

2. **The fee/leverage trap is the most expensive lesson in retail quant.** Intraday Momentum was profitable *before* costs and *with* leverage — exactly the regime we don't operate in. New floor: every spec must have natural R:R ≥ 2 **or** run on daily/swing timeframes. Tight intraday stops + 1× notional = donation to the broker.

3. **Negative results carry information the report should surface.** Both backtests output regime-sliced P&L, exit-reason breakdowns, and signal-skip counters. *Why* it failed (e.g. *"1,710 signals blocked by notional cap, 194 by min-stop guard"*) is the lesson — not just the equity curve.

4. **Two kills in two attempts is the lab working, not the lab failing.** The point of validation gates is to catch broken specs *before* paper trading, and paper trading before live. Both strategies died at gate one with zero real money risked. That is the system functioning exactly as designed.

These lessons are codified in [`docs/graduation_criteria.md`](./docs/graduation_criteria.md) — the pre-defined gates a strategy must clear before paper, and before live.

## Roadmap

- **Phase 0** ✅ Charter, philosophy docs, risk policy
- **Phase 1** ✅ Data engine, regime classifier, indicators
- **Phase 2** ✅ First strategy + backtest reports + research engine
- **Phase 3** 🚧 Walk-forward harness · Monte Carlo · GARCH vol regime · IsolationForest data QA (you are here)
- **Phase 4** — Paper trading on Alpaca (≥30 trading days before live)
- **Phase 5** — Live with micro capital, kill switches armed, daily reconciliation

## What this repo deliberately does **not** do (yet)

- No custom backtester (Nautilus handles it).
- No custom broker adapter (Nautilus + Alpaca adapter).
- No crypto. US equities first.
- No multi-strategy ensembles. One strategy at a time.
- No AI auto-trading. Humans approve every live order in the first 30 trades.
- No averaging down. No martingale. No strategy that requires "perfect" exits.

## License

Private. Personal research project.
