# Strategy Spec — `range_mean_reversion`

## 1. Identity

- **Name:** `range_mean_reversion`
- **Author:** AlphaFactory (Wisconsin Nugget + Claude)
- **Date:** 2026-05-24
- **Status:** `draft`
- **Version:** v0.1.0

## 2. Hypothesis

When SPY or QQQ consolidates inside a narrow intraday range during the US regular session, price tends to mean-revert from range extremes back toward the session VWAP more often than it breaks the range — provided ATR is stable (not collapsing or expanding) and ADX confirms no trend.

The edge is *not* that the strategy predicts the next bar; it's that we systematically buy at the lower edge of a structurally-confirmed range and sell near a mathematical center of gravity (VWAP), with a tight stop that defines the structural break.

## 3. Universe & timeframe

- **Instruments:** `[SPY, QQQ]` initially. Single-name expansion only after walk-forward holds.
- **Primary timeframe:** `5m`
- **Higher timeframe context:** `1h` ADX (read-only — used as veto, not entry trigger)
- **Session restrictions:** RTH only, 09:45–15:30 ET. Skip the first 15 min (opening volatility), skip the last 30 min (close auction distortions).

## 4. Regime gate

Strategy fires **only** when ALL of:

- `categorical_state == "consolidating"` (from `src/regimes/regime_classifier.py`)
- `trend_bucket == "range"` (5m ADX < 20)
- 1h ADX < 30 (no higher-timeframe trend bleeding into the range)
- `vol_bucket in {"low", "medium"}` (skip high-volatility — false ranges break)
- ATR(14) on 5m has been stable: rolling std / rolling mean ≤ 0.4 over last 20 bars

Outside this gate the strategy produces **no signal**, not just a losing signal.

## 5. Entry

The "range" is defined as: `[rolling_low_20, rolling_high_20]` over the last 20 5m bars (≈100 minutes).

**Long entry** (all must hold):
- Close of bar T ≤ `rolling_low_20 + 0.15 × range_width`
- Close of bar T > Open of bar T (rejection candle — at least mildly green)
- `close[T] > close[T-1]` (intra-bar reversal confirmation)
- All regime-gate conditions still true at bar T

**Short entry** (mirror):
- Close of bar T ≥ `rolling_high_20 − 0.15 × range_width`
- Close of bar T < Open of bar T
- `close[T] < close[T-1]`
- All regime-gate conditions still true

**Entry order:** market at bar T+1 open (we never act on the same bar that produced the signal — that's the no-lookahead contract).

**Time-in-force:** day (no overnight holds in this strategy).

## 6. Stop loss

- **Initial stop placement:**
  - Long: `entry_fill − max(0.5 × ATR(14), 0.25 × range_width)`
  - Short: `entry_fill + max(0.5 × ATR(14), 0.25 × range_width)`
- **Stop adjustment:** move to breakeven after price reaches +1R (one-R measured from entry to initial stop). Never widen.
- **Maximum stop distance:** 0.5% of entry price. If the computed stop is wider than that, skip the trade.

## 7. Target / exit

- **Primary target:** session VWAP (computed by `src/features/vwap.session_vwap`).
- **Partial exit:** none in v0.1 (keep it simple; partials add a parameter we'd need to tune).
- **Time-based exit:** force-close at 15:30 ET regardless of P&L. We do not hold these into the close.
- **Trailing rule:** none in v0.1.

## 8. Invalidation

Exit immediately at market (separate from stop) if any of:

- `categorical_state` flips to `chaotic` mid-trade
- Range is broken: close > `rolling_high_20` (for longs, you're in the wrong trade) or close < `rolling_low_20` (for shorts)
- 1h ADX crosses above 30 (higher-timeframe trend just woke up; range thesis dead)
- ATR(14) spikes > 2× its 20-bar rolling mean within 3 bars of entry

## 9. Sizing

- **Risk per trade:** 0.25% of equity (default per `docs/risk_policy.md`)
- `shares = floor(equity × 0.0025 / (entry − stop))`
- If `shares < 1`, skip the trade.

## 10. Forbidden setups

- No entries in the first 15 min or last 30 min of RTH.
- No entries within 15 min of FOMC, CPI, NFP releases (use a calendar; for v0.1 we can hard-code a small list).
- No entries on Fridays after 15:00 ET (weekend gap risk vs short-duration thesis).
- No entries if average 5m volume over last 20 bars is < 50% of 20-day median (illiquid → unreliable fills).

## 11. Expected behavior

These are *hypotheses* we'll validate in the backtest report. Wildly missing them is a yellow flag.

- Expected win rate: 55–62%
- Expected R:R: 1.0–1.5 (target=VWAP, stop=0.5×ATR)
- Expected trades per week per symbol: 3–8
- Expected max consecutive losses (95% CI): 5
- Expected max drawdown: 4–6% over a full year
- Expected dominant regime: `range_low` and `range_medium` (by construction)

## 12. Failure modes (pre-mortem)

- "Range" definition is too generous → too many false consolidations, fees eat edge.
- VWAP target unreliable when the regime stays consolidating but VWAP drifts (because we exit at VWAP, not at fixed R).
- 5m bars are too noisy on SPY — single ticks can fake out the entry condition.
- The strategy might be a hidden short-vol strategy, not a mean-revert one — meaning it works in calm regimes and blows up in regime transitions (i.e., we lose the months we most need to perform).
- 0.5×ATR stops may be too tight for SPY's intraday noise → death by a thousand stop-outs.

## 13. Validation plan

- **Backtest window:** 2020-01-02 → 2025-12-31 (6 years, includes COVID, 2022 bear, 2024 rally — multiple regime epochs)
- **Walk-forward windows:** train 12 months / test 3 months / step 3 months (deferred to Sprint 3)
- **Required:** ≥ 100 trades in the OOS window, OOS Sharpe ≥ 60% of IS Sharpe, profitable after fees + slippage modeled at 1 bp each side
- **Required:** P&L not concentrated in one regime cell unless gated to one by design (this strategy IS gated, so we expect range_low + range_medium to dominate — that's fine)
- **Required:** Parameter sensitivity — performance stable within ±20% on lookback window (15–25 bars), stop multiplier (0.4–0.6 ATR), entry zone fraction (0.10–0.20 of range)

## 14. Graveyard criteria

Pause and review in paper or live if:

- Drawdown > 8% (1.5× expected max)
- Win rate < 45% over any 30-trade window
- Slippage > 2 bps sustained for a week
- Average trade duration > 4 hours or < 5 minutes (drift from "intraday mean revert")

## 15. Sign-off

- [x] Spec complete
- [ ] Code implemented
- [ ] Backtest passed all validation gates
- [ ] Walk-forward passed
- [ ] Paper trading ≥ 30 days
- [ ] Risk Officer review
- [ ] Promoted to live
