# Strategy Spec — `intraday_momentum_spy`

> Implementation of the "Beat the Market" intraday momentum strategy by Zarattini, Aziz, Barbon (2024). Adapted for AlphaFactory's regime gate and risk policy.

## 1. Identity

- **Name:** `intraday_momentum_spy` (snake_case)
- **Author:** AlphaFactory AI, picked per [[project-strategy-selection]] preference for recent-edge ideas
- **Date:** 2026-05-24
- **Status:** `draft` (will move to `in_backtest` once code is written)
- **Version:** v0.1.0
- **Source:** Zarattini, C., Aziz, A., Barbon, A. (2024). *Beat the Market: An Effective Intraday Momentum Strategy for S&P 500 ETF (SPY)*. SSRN 4824172.
- **Evidence of recent edge:** Paper published 2024. Active QuantConnect community discussion 2024–2026. **Caveat (load-bearing):** One independent live trader reports 6 months of poor live results during 2025; the paper's author has admitted that their own live implementation uses *more sophisticated trailing methods than those described in the paper*. This means we are testing a strategy whose published version is known to underperform live. Result: we treat this as a **specimen with skepticism**, not a strategy with prior validation.

## 2. Hypothesis

When SPY's intraday move from the day's open exceeds its typical 14-day average intraday deviation, the move is more likely to continue in that direction than to mean-revert — *provided the move agrees with the intraday VWAP direction*. The strategy buys above the upper deviation band and shorts below the lower one, trailing with the more conservative of (VWAP, band) to lock in gains as the trend unfolds.

## 3. Universe & timeframe

- **Instruments:** `[SPY]` initially. `[QQQ]` as a robustness check in a separate run (not portfolio).
- **Primary timeframe:** `30m` bars. **We will resample our existing 5-min Parquet store to 30-min in the strategy's data prep step — no new data pull needed.**
- **Higher timeframe context:** Daily (for prev_close and 14-day deviation rolling).
- **Session restrictions:** US regular trading hours, 09:30 ET to 15:55 ET. First 30-min bar (09:30–10:00 ET) is used to establish session VWAP and capture today's open; entries start with the bar closing at 10:00 ET. Force close at 15:55 ET (one bar before close).

## 4. Regime gate

The strategy is *only* allowed to fire when:

- **Quant regime in:** `{weak_trend_low, weak_trend_medium, weak_trend_high, strong_trend_low, strong_trend_medium, strong_trend_high, range_high}` — this is a momentum strategy, so it needs at least some directional energy (weak_trend / strong_trend buckets) OR a vol spike inside a range (range_high). We deliberately **forbid** `range_low` and `range_medium` (low-vol consolidation regimes) where mean reversion dominates. *Regime names corrected from spec draft after reading `src/regimes/regime_classifier.py` — the actual trend buckets are `range`, `weak_trend`, `strong_trend`, not `trend_low/medium/high`.*
- **Categorical state in:** `{directional}` only. *Not* `consolidating` (a momentum strategy will get whipsawed inside ranges) and *not* `chaotic` (`chaotic` is a system-wide hard gate per `risk_policy.md` — no strategy may trade in chaotic state, period).
- **Other conditions:** None at the regime layer — the band-based entry condition is its own filter.

Outside these regimes the strategy must produce **no signal**, not just lose. Implementation: in `generate_signals`, every candidate row must pass the regime gate before any band check.

## 5. Entry

Compute at every 30-min bar close after 10:00 ET:

- `open_today` = open price of the first 30-min bar of the day (10:00 ET bar's open = market open at 09:30 ET).
- `prev_close` = previous trading day's close.
- `deviation_14d` = rolling 14-day average of *intraday average absolute deviation*. For each historical day D, compute the mean of `|price_t − open_D| / open_D` over all 30-min closes in day D, then average that scalar over the last 14 days.
- `vwap_today` = session-anchored VWAP starting at 09:30 ET (we already have this as a feature column).
- `upper_band = max(open_today, prev_close) × (1 + deviation_14d)`
- `lower_band = min(open_today, prev_close) × (1 − deviation_14d)`

**Long entry condition:**
- bar close `>` upper_band AND
- bar close `>` vwap_today AND
- regime gate (Section 4) passes AND
- no current position open (single-position engine).

**Short entry condition:**
- bar close `<` lower_band AND
- bar close `<` vwap_today AND
- regime gate passes AND
- no current position open.

- **Entry order type:** market at next bar's open (matches our engine's standard next-bar-fill convention).
- **Time-in-force:** day.

## 6. Stop loss

Trailing stop, updated each 30-min bar while position is open:

- **Long initial and trailing stop:** `max(vwap_today, upper_band)`. **Only tightens, never widens** (we take the highest stop level seen so far). If this stop level ever falls below the current price by more than 2 × ATR(14, 30m bars), we cap it at price − 2 × ATR to avoid pathological wide stops.
- **Short trailing stop:** `min(vwap_today, lower_band)`, only tightens (lowest level seen so far). Same 2 × ATR cap on the other side.
- **Maximum stop distance allowed:** 1% of entry price. Signals where the implied initial stop would be wider than 1% of entry are skipped — this protects against pathological vol days and complements the engine-level `min_stop_pct` guardrail.

## 7. Target / exit

This strategy does not have a fixed target — it rides the trend until either the trailing stop fires or the session ends.

- **Primary exit:** trailing stop fires (Section 6).
- **Time-based exit:** force-close at 15:55 ET (one 30-min bar before close) regardless of P&L. Already enforced by the research engine's `force_close_local` parameter.
- **No partial exits in v0.1.** Add later if backtest shows long winners give back significant unrealized gain.

## 8. Invalidation (separate from stop)

- VWAP crosses against the position (e.g., long position but price closes below vwap_today on the most recent 30-min bar): exit immediately. This is the strategy's core thesis breaking.
- Regime flips out of allowed set mid-trade (e.g., shifts from `directional` to `consolidating`): exit immediately.

These are stricter than the trailing stop and prevent us from holding a position whose hypothesis has broken even if the stop hasn't been touched yet.

## 9. Sizing

- **Risk per trade:** uses default 0.25% (set by `risk_policy.md`; not overridden).
- **Engine guardrails active:** `max_notional_pct = 1.0` (no leverage), `min_stop_pct = 0.0005` (5 bps min stop). Both will catch any pathological sizing as a side effect of the trailing stop logic.
- **Special sizing rules:** None in v0.1. The paper uses a 2% daily volatility target which is a different sizing paradigm; we are deliberately using fixed-fractional risk to keep risk consistent across strategies in the portfolio.

## 10. Forbidden setups

- No entries during the first 30-min bar of the day (09:30–10:00 ET) — we use that bar to establish open and warm up VWAP.
- No entries during the last 30-min bar (15:30–16:00 ET) — too close to force-close to be meaningful.
- No entries when the prior day was a half-day session (Thanksgiving Friday, Christmas Eve, etc.) — `prev_close` is unreliable.
- No entries when `deviation_14d` is below the 5th percentile of its own history (signal: market is in an unusually quiet regime, bands too tight, expect chop).

## 11. Expected behavior

These are expectations (used by the journal to flag drift), **not** the paper's headline numbers. They reflect the realistic-cost, no-leverage regime we will actually run:

- Expected win rate: **35–40%** (per CloudQuant2's realistic-fee QuantConnect backtest, and consistent with Trader Ostburg's live experience: this is a "many small losses, few big wins" trend-following profile)
- Expected R:R: **1.8–2.5** (winners run, losers cut)
- Expected trades per week: **3–7** (some days don't trigger any signal)
- Expected max consecutive losses (95% CI): **8**
- Expected max drawdown: **10–15%** (vs paper's claim of ~10% with leverage; we have no leverage)
- Expected dominant regime cells: `trend_medium` and `trend_high` (and `range_high` during vol spikes)
- Expected annualized Sharpe at realistic costs: **0.4–1.0** (vs paper's 1.33). Our G1.2 graduation gate requires ≥1.0 — *this strategy may not pass*. That is the intended test.

## 12. Failure modes (pre-mortem)

- **Alpha decay.** Strategy is publicly known since 2024 and discussed widely. Live trader Ostburg reports 6 months of poor 2025 results. Edge may have decayed.
- **Slippage assumption too generous.** Paper assumes $0.001/share; author later admits $0.005/share is more realistic in live. Our default fee model (1 bp slippage) maps to about $0.06/share at SPY = $580, which is *more* conservative than the author's later admission. Should be fine, but validation must include a `PESSIMISTIC` fee model run (3 bps slippage, $0.005/share commission).
- **Regime gate forbids consolidating markets.** Half of all trading days are arguably consolidating. The strategy will be flat much of the time. If signal count drops below the 100-trade floor over our 5-year sample, we abandon — same fate as Range MR.
- **VWAP filter too aggressive.** Requires price *and* VWAP to agree. In ranging-but-trending intraday tape, VWAP can lag, suppressing signals. Possible mitigation: also allow entries when price is within 0.1% of VWAP, not just strictly above/below. Not in v0.1 — keep simple, see baseline.
- **Author's live implementation uses different exits.** This is the biggest risk. If the published trailing-stop logic doesn't capture the edge, we're testing a strawman. Mitigation: our validation report explicitly compares to the paper's published numbers, so we know if we're seeing the same effect they did.

## 13. Validation plan

- **Backtest window:** 2020-07-01 to 2026-05-23 (our full SPY 5-min Parquet history, resampled to 30-min).
- **Walk-forward windows:** train 18 months / test 6 months, step 6 months. That gives us 8 OOS windows across the 5-year history.
- **Two fee runs:** (1) default `ALPACA_PAPER` fee model (1 bp slippage), (2) `PESSIMISTIC` fee model (3 bps slippage + $0.005/share commission). Both must show positive expectancy.
- **Monte Carlo:** 1000 trade-order reshuffles. 5th percentile equity curve must finish positive.
- **Required for G1 graduation:** ≥100 trades over 5 years, Sharpe ≥ 1.0 OOS (per ratified G1.2), max DD ≤ 20% (per ratified G1.3), profit factor ≥ 1.3, no `signals_skipped_by_max_notional` or `signals_skipped_by_min_stop` trips (per G1.8).
- **Parameter sensitivity:** vary `deviation_window` ∈ {7, 14, 21, 28}, `forbidden_first_bar` ∈ {true, false}, and the 1% max stop cap ∈ {0.5%, 1%, 2%}. Performance should be stable within ±20% of headline Sharpe across this sweep. If it isn't, the strategy is overfit to the specific paper parameters.

## 14. Graveyard criteria (kill conditions)

In paper or live, the strategy is paused and reviewed if:

- Drawdown > expected max DD × 1.5 (i.e., > ~22%)
- Win rate < 25% or > 55% over any 30-trade window — outside the expected envelope, hypothesis has shifted
- Slippage > 2× backtest assumption sustained for a week
- Average trade duration deviates > 2× from expected (≈3 hours for this strategy)
- Three consecutive days with the regime gate suppressing every signal (data feed issue or regime classifier broken — diagnose before resuming)

## 15. Sign-off

- [ ] Spec complete and reviewed
- [ ] Strategy code implemented in `src/strategies/intraday_momentum_spy.py`
- [ ] Unit tests for the deviation indicator and band computation
- [ ] Backtest run #1 (`ALPACA_PAPER` fees) passes G1 gates
- [ ] Backtest run #2 (`PESSIMISTIC` fees) passes G1 gates
- [ ] Walk-forward validation passes (8 windows, no Sharpe < 0 window)
- [ ] Monte Carlo passes (5th percentile positive)
- [ ] Parameter sensitivity passes (±20% envelope)
- [ ] QQQ robustness backtest run (separate)
- [ ] Auto-promoted to paper trading
- [ ] Paper trading ≥30 days (per ratified G2.1)
- [ ] Operator manual sign-off (G2.10) for live consideration
- [ ] Promoted to live (date: ______)
