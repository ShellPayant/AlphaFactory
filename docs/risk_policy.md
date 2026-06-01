# AlphaFactory — Risk Policy

> This policy is enforced in code by `src/risk/`. Any change here must be paired with a code change and a test. **Do not edit this document to "unblock" a trade.**

## 0. Hierarchy

The risk engine ranks higher than any strategy. A strategy *requests* a trade; the risk engine *decides*. A strategy with valid signal + violated risk = no order. No exceptions, no overrides without the kill switch being deliberately re-armed.

## 1. Per-trade limits

| Limit                                  | Value     | Enforced by                          |
|----------------------------------------|-----------|--------------------------------------|
| Max account risk per trade             | **0.25%** | `position_sizing.size_for_signal()`  |
| Required: defined stop loss            | yes       | `pre_trade_checks.has_stop()`        |
| Required: defined invalidation         | yes       | `pre_trade_checks.has_invalidation()` |
| Required: defined target (R:R ≥ 1.0)   | yes       | `pre_trade_checks.has_target()`      |
| Required: regime tag on signal         | yes       | `pre_trade_checks.has_regime_tag()`  |
| Max position size (% account equity)   | 25%       | `position_sizing.cap_notional()`     |

Position size formula (long example):

```
shares = floor( account_equity * max_risk_per_trade / (entry_price - stop_price) )
```

If `shares < 1` after the formula, the trade is **skipped**, not rounded up.

## 2. Daily / weekly / monthly loss limits

| Limit                  | Value | Effect when hit                            |
|------------------------|-------|--------------------------------------------|
| Max daily loss         | 1.0%  | Kill switch armed → no new entries today   |
| Max weekly loss        | 2.5%  | Kill switch armed → no new entries this wk |
| Max monthly drawdown   | 5.0%  | Strategy paused, weekly review required    |

Realized + unrealized P&L both count. The clock is account-local timezone (America/New_York), reset at 09:30 ET.

## 3. Portfolio limits

| Limit                                          | Initial value (will tighten/loosen as we learn) |
|------------------------------------------------|--------------------------------------------------|
| Max open positions                             | 1 (Phase 1), 3 (post-paper)                      |
| Max open positions in same sector              | 1                                                |
| Max correlated exposure (|ρ| ≥ 0.7, 60-day)    | 2 names                                          |
| Max gross exposure                             | 100% of equity                                   |
| Max overnight exposure                         | 50% of equity (until proven otherwise)           |

## 4. Mandatory pre-trade checks

`pre_trade_checks.run(signal, account_state, market_state) → Approved | Rejected(reason)`

Reject if any:

1. Data is stale (latest bar > 2× expected interval old).
2. Broker connection unhealthy or position state unreconciled.
3. Open positions + this signal would exceed cap.
4. Daily / weekly / monthly loss limit already triggered.
5. Correlated-exposure cap violated.
6. Signal missing required fields (stop, invalidation, target, regime tag).
7. Signal's regime tag does not match strategy's allowed regimes.
8. Market closed or in scheduled halt.
9. Duplicate order (same symbol + side + price within last N seconds).
10. Kill switch armed.

Every rejection is logged with the reason. Rejections are reported in the daily report.

## 5. Kill switch

The kill switch is a global boolean. When armed:

- No new entries.
- Existing positions are **not** automatically closed (avoids panic exits at bad prices). Manual decision required.
- Re-arming requires editing a config flag *and* restarting the live runner. Cannot be re-armed from inside a running session.

Auto-trigger conditions:

- Daily/weekly/monthly loss limit hit.
- 3 consecutive order rejections from the broker.
- Position-state mismatch between journal and broker.
- Data feed stale > 5 minutes during market hours.
- Duplicate order detected in execution layer.
- Unhandled exception in main strategy loop.

## 6. Forbidden behaviors (system-enforced)

- **No averaging down losers.** If position is open at a loss, no orders adding to it. Period.
- **No moving stops against you.** Stops can only be tightened, never widened.
- **No martingale / size escalation after a loss.** Position sizing is a pure function of equity and signal, not of recent P&L.
- **No "I'll just take this one trade outside the system."** Manual orders during a live session require kill-switch arm + journal entry + post-mortem.
- **No trading on stale data.** If data feed gap > 2 bars, no entries until reconciled.
- **No trading during halts or first/last 60 seconds of session** (until microstructure analysis proves it's safe).

## 7. Phase-gated risk envelope

| Phase                       | Max account risk per trade | Max concurrent strategies | Max open positions | Manual approval per trade |
|-----------------------------|----------------------------|---------------------------|--------------------|---------------------------|
| Research / backtest         | n/a                        | n/a                       | n/a                | n/a                       |
| Paper trading               | 0.25%                      | 1                         | 1                  | no                        |
| Live — first 30 trades      | 0.10%                      | 1                         | 1                  | **yes**                   |
| Live — trades 31–100        | 0.25%                      | 1                         | 1                  | no                        |
| Live — post 100, good stats | 0.25–0.50%                 | up to 2                   | up to 3            | no                        |
| Live — post 500, good stats | 0.50–1.0%                  | TBD by weekly review      | TBD                | no                        |

Numbers tighten if drawdown approaches policy limit. They never loosen automatically; loosening requires explicit weekly-review sign-off recorded in the journal.

## 8. Review cadence

- **Daily** (after close): reconciliation report; flag any rejected signal, override, slippage outlier > 2× expected.
- **Weekly** (Sunday): P&L by regime, override count, slippage vs backtest, one objective for next week.
- **Monthly**: bias scan, retirement candidates, capital scaling decision.

## 9. Out of scope (for now)

- Cross-asset hedging
- Options or futures exposure
- Margin > 1×
- Holding through earnings or scheduled macro events without explicit strategy spec saying so

---

*This document is the contract between the operator and the system. The operator does not get to argue with it mid-trade.*
