# AlphaFactory — Strategy Graduation Criteria

> The gate between phases of `risk_policy.md` Section 7. A strategy is **not** ready for live trading just because someone (operator or AI) thinks it's good. It is ready when, and only when, every criterion below is checked off.
>
> **Status:** RATIFIED 2026-05-24. Operator chose a higher-risk-tolerance variant of the original draft: looser drawdown caps and a substantially shortened paper-trading period (30 days vs the recommended 90-180). See "Operator overrides" note at end of doc. Once ratified, change requires the same review cadence as `risk_policy.md`: pair every edit with a code change and a test, never edit to unblock a trade.

---

## 0. Philosophy

These criteria exist because:

- Backtests lie by default ([[project-philosophy]] rule #5).
- A strategy that worked in 2020-2024 paper can still die in 2026 live (alpha decay, regime shift, microstructure changes).
- The operator's job is to be **skeptical**, not optimistic. The AI's job is to monitor mechanically and only escalate when the gate is met.
- "I have a feeling about this one" is never a graduation criterion.

The default disposition is **don't trust the strategy yet**. Criteria below are how a strategy *earns* trust.

---

## 1. The three gates

| Gate | From → To | Approver |
|---|---|---|
| **G1 — Backtest → Paper** | Research-only → eligible for paper trading | AI auto-promotes when met |
| **G2 — Paper → Live (small)** | Paper → first-30-trades live phase | **Operator manual sign-off** |
| **G3 — Live small → Live full size** | First-30-trades phase → trades 31-100 phase | AI proposes; operator confirms |

Live phases beyond G3 (per `risk_policy.md` Section 7) are governed by ongoing performance review, not a separate graduation gate.

---

## 2. G1 — Backtest → Paper

A strategy is eligible to be moved into paper trading when **all** of:

| # | Criterion | Threshold (proposed) | Why |
|---|---|---|---|
| G1.1 | Backtest produced ≥ **100 trades** | absolute | Statistical floor — below this, any metric is noise. |
| G1.2 | In-sample Sharpe (annualized) | ≥ **1.0** | Below this, even a perfect backtest isn't worth paper-trading. |
| G1.3 | Max in-sample drawdown | ≤ **20%** | Roomier than live cap because backtests over-estimate edge. *Original draft was 15%; loosened per operator's higher risk tolerance.* |
| G1.4 | Profit factor | ≥ **1.3** | Edge after fees & slippage, not just before. |
| G1.5 | Survived **walk-forward** validation | ≥ **3 windows**, no window with Sharpe < 0 | Detects overfit to a single regime/era. |
| G1.6 | Survived **Monte Carlo** trade-reshuffle | 5th-percentile equity curve still positive | Detects reliance on lucky trade ordering. |
| G1.7 | No regime carries >60% of total P&L | unless strategy is explicitly regime-gated and the gate was set *before* seeing the regime breakdown | [[project-philosophy]] rule #3. If you find your edge by slicing, you found a fit, not an edge. |
| G1.8 | Zero `signals_skipped_by_max_notional` and zero `signals_skipped_by_min_stop` in the backtest report | absolute | A strategy producing signals that trip the engine guardrails has a spec problem, not a "we should loosen the guardrails" problem. |
| G1.9 | No-lookahead test passes for the strategy implementation | absolute | Existing prefix-invariance tests must pass on the specific strategy module. |

**Auto-promotion:** When G1.1–G1.9 are all green for a strategy, the AI updates the strategy's status in the registry from `research` to `paper_eligible` and schedules paper trading to start in the next session. No operator approval required for G1.

---

## 3. G2 — Paper → Live (small)

The high-stakes gate. **Operator must sign off in writing** (journal entry) before any real money is committed.

A strategy meets G2 when **all** of:

| # | Criterion | Threshold (proposed) | Why |
|---|---|---|---|
| G2.1 | Paper-trading duration | ≥ **30 calendar days** for first and subsequent strategies | *Original draft: 180/90 days. Operator chose 30 days for faster time-to-live. **Trade-off the operator accepted:** 30 days may not span enough regime variation to distinguish real edge from a lucky trending month — the G2.2 trade-count floor is the only remaining statistical guard, so it MUST hold.* |
| G2.2 | Paper trade count | ≥ **30 trades** during the paper period | Same statistical-floor logic as G1.1. |
| G2.3 | Paper Sharpe (annualized, out-of-sample) | ≥ **1.0** | Same bar as G1.2 but on truly unseen data. This is the real test. |
| G2.4 | Paper max drawdown | ≤ **12%** | *Original draft: 8%. Loosened per operator's higher risk tolerance. Note: live-phase 5% monthly kill-switch in `risk_policy.md` is unchanged — that's a separate hard limit, not a graduation gate.* |
| G2.5 | Paper realized slippage vs backtest-assumed | within **±50%** of backtest assumption | Catches a strategy whose backtest assumed cheap fills it isn't actually getting. |
| G2.6 | Max single-trade paper loss | ≤ **2 × `risk_per_trade`** of account equity | Catches sizing or stop-execution bugs. With `risk_per_trade=0.25%`, max single loss ≤ 0.5%. |
| G2.7 | Reconciliation: trades-recorded vs broker-confirmed | **100% match**, every day of paper period | Operational hygiene. If we can't reconcile in paper, we definitely can't in live. |
| G2.8 | Correlation with any *existing* live strategy in the portfolio | absolute Spearman ρ < **0.5** over the overlapping paper window | Only relevant once we have ≥1 live strategy. First strategy is exempt by definition. |
| G2.9 | Kill switch tested at least once during paper period | absolute | Don't find out the kill switch is broken when you actually need it. |
| G2.10 | Operator has reviewed the most recent paper-period report and signed off in `journal/graduation_<strategy>_<date>.md` | absolute | The operator is part of the system ([[project-philosophy]] rule #6). |

**On graduation:** Strategy moves to `risk_policy.md` Section 7 "Live — first 30 trades" envelope: 0.10% per-trade risk, manual approval per trade. AI sends a "READY TO REVIEW" notification with the full paper-period report attached. Operator makes the call.

---

## 4. G3 — Live small → Live full size

Promotes a strategy from "first 30 trades with manual approval" to "31-100 trades, automatic." Less consequential than G2 — we already have real-money evidence — but still a checkpoint.

A strategy meets G3 when **all** of:

| # | Criterion | Threshold (proposed) | Why |
|---|---|---|---|
| G3.1 | Live trade count | ≥ **30 trades** at the small-size envelope | Per the phase ladder. |
| G3.2 | Live realized P&L | non-negative | If we're down on the first 30, we don't double down. |
| G3.3 | Live Sharpe (annualized) | ≥ **0.3** | *Original draft: 0.5. Loosened per operator's higher risk tolerance. Tolerance for noise in small N, but signal must be there.* |
| G3.4 | Live slippage vs paper | within **±50%** | Tightens the G2.5 check now that we have live data. |
| G3.5 | No risk-policy rejection that the strategy keeps triggering | absolute | If pre-trade checks keep rejecting the strategy's signals, the spec is wrong. |
| G3.6 | Operator confirms in journal | absolute | Same as G2.10. |

---

## 5. Demotion / kill criteria (the other direction)

A strategy is **demoted one level** (live → paper, or paper → research) when any of:

- Live or paper drawdown breaches 1.5× the in-sample max DD from backtest.
- Realized Sharpe diverges from backtest Sharpe by more than 50% (e.g., backtest 2.0 → live 0.9).
- Slippage exceeds 2× backtest assumption for 5 consecutive trading days.
- Any forbidden-behavior trigger from `risk_policy.md` Section 6.
- Operator manually demotes via journal entry.

A strategy is **killed entirely** (removed from the registry) when:

- Three consecutive demotions, or
- Realized P&L over any 90-day live window < -2× max in-sample DD, or
- Operator manually kills via journal entry.

---

## 6. Monitoring

The AI runs the graduation check automatically:

- **G1 check** — on every fresh backtest report.
- **G2 check** — weekly, on every active paper-trading strategy.
- **G3 check** — weekly, on every active "Live — first 30 trades" strategy.
- **Demotion check** — daily, on every active live strategy.

When any gate flips green, the AI surfaces a "READY TO REVIEW" notification with the full evidence pack. When any demotion criterion fires, the AI surfaces it immediately (not on a weekly schedule).

The operator is not expected to remember any of these numbers. The system enforces them.

---

## 7. Override clause

The operator may override any criterion in this document, BUT:

1. The override must be recorded in `journal/overrides/<date>_<strategy>_<criterion>.md` with the rationale.
2. The override applies to one decision only — not a permanent rule change.
3. Overriding a G2 or demotion criterion requires a 24-hour cool-down between the decision to override and the actual trade — to prevent FOMO-driven overrides ([[project-philosophy]] rule #6).
4. If a criterion is overridden three times across any rolling 90-day window, the criterion itself goes up for review — either the number is wrong, or the operator is rationalizing, and either case deserves a deliberate decision.

---

## 8. What this document does not cover

- Strategy *selection* — which ideas to try. That's [[project-build-path]] + the operator's choice.
- Per-trade risk math — that's `risk_policy.md`.
- Execution mechanics — that's the engine's job.
- Capital allocation across strategies — Phase 2+ concern, separate doc.

---

## 9. Operator overrides at ratification (2026-05-24)

The operator ratified this doc with the following overrides vs the AI's recommended defaults:

| Criterion | AI default | Operator chose | Rationale operator gave |
|---|---|---|---|
| G1.3 max in-sample DD | 15% | **20%** | Higher risk tolerance |
| G2.1 paper period | 180/90 days | **30 days** | Wants faster path to live; willing to accept less regime coverage |
| G2.4 max paper DD | 8% | **12%** | Higher risk tolerance |
| G3.3 live Sharpe | ≥0.5 | **≥0.3** | Higher risk tolerance |

These overrides are recorded so future-Claude, on noticing live results that breach the original tighter thresholds, can flag them as "operator-known acceptable" rather than as alarms. If the operator later wants to revert to the stricter defaults, all four are noted as the comparison points.

The remaining criteria (Sharpe ≥1.0 quality bar, profit factor ≥1.3, ≥30-trade floor, walk-forward and Monte Carlo survival, regime concentration cap, no-engine-guardrail trips, reconciliation cleanliness, kill-switch test) are unchanged — these are quality-of-evidence bars, not risk-tolerance bars, and they don't move with risk appetite.

---

*Status: ratified by operator 2026-05-24, binding. Last edited: 2026-05-24.*
