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

## Roadmap

- **Phase 0** ✅ Charter, philosophy docs, risk policy
- **Phase 1** 🚧 Data engine, regime classifier, indicators (you are here)
- **Phase 2** — First strategy implemented as Nautilus `Strategy` + backtest report
- **Phase 3** — Walk-forward harness + Monte Carlo + graveyard pipeline
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
