# Strategy Candidate Queue

> Auto-populated by the weekly strategy radar scheduled task. Each entry is a *hypothesis worth investigating*, not a strategy to deploy. The operator (or AI in next session) picks one, writes the full spec per `docs/strategy_spec_template.md`, and feeds it through the lab.

## Triage rules

- Move a candidate to `_investigated/` (done, decision made) once we've written its spec, regardless of outcome.
- Delete a candidate that's a duplicate of an existing investigated idea (link the dup in the existing entry instead).
- Items here that are >90 days old without action should be reviewed — either implement or delete.

## How entries are formatted

```
### YYYY-MM-DD: <Short Name>

- **Source:** <URL + author/community + recency signal>
- **One-line hypothesis:** What inefficiency / behavior does this exploit?
- **Universe + timeframe:** Symbols + bar size (must be US equities + intraday or daily per project scope)
- **Why interesting:** What about it suggests recent edge?
- **Why suspicious:** Decay signals, well-knownness, hidden assumptions
- **Initial verdict:** [investigate | shelve | duplicate of X | out-of-scope]
```

## Queue

_(empty — first radar run will populate this)_

---

## Techniques to borrow (methodology, not candidates)

> Distinct from the strategy queue above: these are *techniques* to embed in future strategy specs / engine components, not standalone strategies. Surfaced from external projects we evaluated and rejected wholesale but found method pieces worth lifting.

### 2026-05-26: Triple-barrier labeling + meta-labeling

- **Source:** TopEpic (FX scalper, EURUSD focus) — evaluated 2026-05-26, rejected for AlphaFactory (wrong asset class, scalper timeframe violates R:R ≥ 2 rule, ML-heavy direction prediction violates [[project-ml-dl-decision]]). Original technique is from López de Prado, *Advances in Financial Machine Learning* (2018).
- **Technique:** Instead of labeling trades by raw forward-return at fixed horizon, label by which of three barriers gets hit first — take-profit (N × ATR), stop-loss (M × ATR), or time (max bars). Then "meta-labeling": let a simple primary signal (e.g. MA crossover, regime gate) propose direction, and let a small filter rate trade *quality* (probability that TP is hit before SL).
- **Why useful here:** Our current engine uses point-in-time signals + ATR trail. Triple-barrier gives a cleaner label for measuring "did this setup actually have an edge" because it bakes in the R:R asymmetry. Meta-labeling lets us separate *when* to trade (primary rule) from *whether the setup is high-quality* (filter) — and the filter is exactly the narrow ML role we explicitly allowed in `project-ml-dl-decision`.
- **Where it lands in our code:** New labeling module in `src/backtest/` that takes a strategy's signal stream and emits triple-barrier labels for offline analysis. Optional `quality_filter` hook on `Strategy` ABC that takes features and returns a [0,1] confidence — strategies opt in.
- **When to do it:** After the next strategy survives G1 single-shot. Premature before that.

### 2026-05-26: Permutation entropy + Kaufman efficiency ratio as regime features

- **Source:** Same — TopEpic v3 feature set.
- **Technique:** Two scalar measures of how *predictable* and *trendy* a price window is, computed on rolling windows.
  - **Permutation entropy (PE):** Looks at the ordinal pattern of N consecutive points (e.g. 3 points → 6 possible orderings). High PE = uniform pattern distribution = random walk-like = unpredictable. Low PE = pattern concentration = structure present.
  - **Kaufman efficiency ratio (ER):** `|price[t] - price[t-N]| / sum(|price[i] - price[i-1]|)` over N. Ratio of net move to total path length. High ER = clean trend, low ER = chop.
- **Why useful here:** Our regime classifier (`src/regimes/regime_classifier.py`) currently uses ADX×ATR grid + categorical state. PE and ER are complementary — they're model-free, computable on tiny windows, and capture "is the regime predictable right now" rather than "is volatility high right now." Could be added as two additional regime dimensions, or used as a meta-gate ("only trade when ER > 0.4 and PE < 0.85").
- **Where it lands in our code:** `src/features/regime_features.py` — two new functions, unit-tested for no-lookahead per the Sprint 1 prefix-invariant pattern. Then exposed to `regime_classifier.py` as optional inputs.
- **When to do it:** Cheap, ~half a day. Could ride along with the macro overlay completion (FRED VIX/term-structure/breadth) when we get there.

### 2026-05-26: Multi-symbol forward test as a mandatory G1.7 gate

- **Source:** Same — TopEpic's multi-pair reality check chart was the most diagnostic part of the whole project (EURUSD optimized: +14%; unseen pairs avg: ~+3%).
- **Technique:** After a strategy passes G1.5 walk-forward + G1.6 Monte Carlo on its calibration symbol, replay it without re-tuning on a panel of unseen but related symbols. If the edge collapses on unseen, the original result was mostly symbol-specific overfit.
- **Why useful here:** Our graduation criteria (`docs/graduation_criteria.md`) doesn't currently have a cross-symbol robustness check. SPY → QQQ + IWM + a handful of S&P sector ETFs is a natural panel. A strategy that survives on SPY but flatlines on QQQ/IWM is almost certainly overfit.
- **Where it lands in our code:** Extension to `scripts/run_walk_forward.bat` — accept a `--panel` argument with extra tickers, run the frozen-param strategy on each, emit a comparison table in the report. A pass/fail threshold (e.g. "mean unseen-symbol Sharpe ≥ 0.5 × calibration Sharpe") becomes G1.7.
- **When to do it:** Worth doing *before* the next strategy enters G1, so the bar is in place when something looks promising. Otherwise we'll be tempted to skip it for the one that finally works.
