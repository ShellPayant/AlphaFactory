# Strategy Spec — `<strategy_name>`

> **Mandatory.** Every strategy must have a filled spec before code is written. Specs live in `docs/strategies/<strategy_name>.md`. A strategy without a spec does not enter the backtester.

## 1. Identity

- **Name:** `<strategy_name>` (snake_case)
- **Author:** <name>
- **Date:** YYYY-MM-DD
- **Status:** `draft | in_backtest | in_paper | live | graveyard`
- **Version:** v0.1.0

## 2. Hypothesis

One sentence. What inefficiency or behavior does this strategy exploit?

> Example: "When SPY consolidates inside a 1-ATR range during the NY session, price tends to mean-revert from range extremes back toward the session VWAP within 2 hours, more often than it breaks out."

## 3. Universe & timeframe

- **Instruments:** e.g. `[SPY, QQQ]`
- **Primary timeframe:** e.g. `5m`
- **Higher timeframe context (if any):** e.g. `1h` (for regime gate)
- **Session restrictions:** e.g. `09:45–15:30 ET, skip first 15 min and last 30 min`

## 4. Regime gate

The strategy is *only* allowed to fire when:

- Quant regime in: `{<list of allowed cells from the 9-cell grid>}`
- Categorical state in: `{consolidating | directional | chaotic}`
- Other conditions (volatility floor/ceiling, news flag, etc.)

Outside these regimes the strategy must produce **no signal**, not just lose.

## 5. Entry

- **Long entry condition (precise, testable):**
  > Example: "Close of bar T touches lower band of session range AND close > prior close AND ADX(14) < 25."
- **Short entry condition:** ...
- **Entry order type:** `market | limit | stop` (and price if limit/stop)
- **Time-in-force:** `day | GTC | IOC`

## 6. Stop loss

- **Initial stop placement:** e.g. "1.0 × ATR(14) beyond range extreme"
- **Stop adjustment rules:** e.g. "Move to breakeven after price reaches 1R in profit. Never widen."
- **Maximum stop distance allowed:** as % of price, to avoid pathological cases

## 7. Target / exit

- **Primary target:** e.g. "Session VWAP" or "+2R"
- **Partial exits (if any):** e.g. "50% at 1R, runner to VWAP"
- **Time-based exit:** e.g. "Force-close at 15:55 ET regardless of P&L"

## 8. Invalidation (separate from stop)

Conditions under which the *thesis* is broken, even if stop has not been hit. Examples:

- Categorical state flips to `chaotic` mid-trade.
- Range is broken and price closes outside on 2 consecutive bars (consolidation thesis dead).
- Higher-timeframe trend flips against the position.

When invalidation triggers, exit immediately at market.

## 9. Sizing

- **Risk per trade:** uses default 0.25% (set by risk policy; do not override here).
- **Special sizing rules (if any):** e.g. "Half-size in high-volatility bucket."

## 10. Forbidden setups

Explicitly enumerated. Examples:

- "No entries within 30 minutes of FOMC."
- "No entries when spread > 2 bps."
- "No entries when range width < 0.5 × ATR (too tight to mean-revert profitably)."

## 11. Expected behavior

These are *expectations*, not constraints. Used by the journal to flag drift.

- Expected win rate: ___ %
- Expected R:R: ___
- Expected trades per week: ___
- Expected max consecutive losses (95% CI): ___
- Expected max drawdown: ___ %
- Expected dominant regime cells: ___

## 12. Failure modes (pre-mortem)

Before backtesting, write down what would make this strategy fail. The backtest report later checks each.

- "Could fail if range definition is too generous → too many false consolidations."
- "Could fail if NY-session-only is overfit to a specific year."
- "Could fail if VWAP target is unreliable when volume is low."

## 13. Validation plan

- Backtest window: from YYYY-MM-DD to YYYY-MM-DD
- Walk-forward windows: train __ months / test __ months, step __ months
- Required: ≥100 trades in OOS, OOS Sharpe ≥ 60% of IS, profitable after fees+slippage
- Required: P&L not concentrated in one regime (unless this strategy is single-regime by design)
- Required: parameter sensitivity check — performance stable within ±20% of each parameter

## 14. Graveyard criteria (kill conditions)

In paper or live, the strategy is paused and reviewed if:

- Drawdown > expected max drawdown × 1.5
- Win rate deviates from expected by > 20 percentage points over 30 trades
- Slippage > 2× backtest assumption sustained for a week
- Average trade duration deviates > 2× from expected

## 15. Sign-off

- [ ] Spec complete and reviewed
- [ ] Backtest passed all validation gates
- [ ] Walk-forward passed
- [ ] Paper trading ≥30 days
- [ ] Risk Officer review
- [ ] Promoted to live (date: ______)
