# Backtest Report — `intraday_momentum_spy` on `SPY`

_Generated 2026-05-25 05:24:15 UTC_

## Configuration

| Setting | Value |
|---|---|
| Strategy | `intraday_momentum_spy` |
| Symbol | `SPY` |
| Timeframe | `30m` |
| Starting equity | $100,000.00 |
| Ending equity | $68,712.40 |
| Fee model | slippage=1.0 bps/side, commission/share=0.0 |
| risk_per_trade | 0.0025 |
| max_notional_pct | 1.0 |
| min_stop_pct | 0.0005 |
| force_close_local | 15:30:00 |

## Headline metrics

| Metric | Value |
|---|---|
| Total return | -31.29% |
| CAGR | -27.72% |
| Sharpe (annualized) | -5.33 |
| Sortino (annualized) | -6.64 |
| Max drawdown | -31.90% |
| Time under water | 98.4% |
| Bars in backtest | 22,725 |

## Trade statistics

| Metric | Value |
|---|---|
| Trades | 827 |
| Signals generated | 4175 |
| Signals skipped (sizing) | 37 |
| Signals skipped (max notional cap) | 1669 |
| Signals skipped (min stop guard) | 373 |
| Win rate | 35.4% |
| Avg win | $124.10 |
| Avg loss | -$118.19 |
| Profit factor | 0.58 |
| Expectancy / trade | -$32.35 |
| Avg bars held | 1.6 |
| Max consec. wins / losses | 6 / 14 |
| Best trade | $1,037.71 |
| Worst trade | -$919.98 |

## Exit reason breakdown

| Reason | Count |
|---|---|
| force_close | 511 |
| invalidation | 172 |
| stop | 144 |

## P&L by regime

| Regime | Trades | Total P&L | Win rate |
|---|---:|---:|---:|
| `weak_trend_high` | 322 | -$14,025.55 | 35.4% |
| `weak_trend_medium` | 169 | -$2,527.48 | 39.1% |
| `weak_trend_low` | 157 | -$5,098.35 | 28.7% |
| `strong_trend_high` | 65 | -$3,725.20 | 27.7% |
| `range_high` | 59 | $382.95 | 45.8% |
| `strong_trend_low` | 43 | -$1,161.86 | 41.9% |
| `strong_trend_medium` | 12 | -$595.83 | 41.7% |

## Best 5 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022-09-13 18:00:00+00:00 | 2022-09-13 19:30:00+00:00 | short | 206.0 | 378.6121 | 373.5374 | 1037.71 | 1.3305 | 3 | force_close | weak_trend_low |
| 2023-03-09 18:30:00+00:00 | 2023-03-09 20:30:00+00:00 | short | 193.0 | 379.982 | 375.4775 | 862.11 | 1.1756 | 4 | force_close | weak_trend_high |
| 2022-03-07 15:30:00+00:00 | 2022-03-07 20:30:00+00:00 | short | 130.0 | 401.7998 | 395.7196 | 785.29 | 1.5034 | 10 | force_close | weak_trend_low |
| 2025-04-04 16:00:00+00:00 | 2025-04-04 19:30:00+00:00 | short | 64.0 | 509.3991 | 500.22 | 584.26 | 1.7921 | 7 | force_close | strong_trend_high |
| 2023-08-29 14:30:00+00:00 | 2023-08-29 19:30:00+00:00 | long | 175.0 | 430.7931 | 433.7966 | 518.03 | 0.6871 | 10 | force_close | weak_trend_high |

## Worst 5 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022-01-24 18:30:00+00:00 | 2022-01-24 18:30:00+00:00 | short | 192.0 | 402.0698 | 406.8207 | -919.98 | -1.1917 | 0 | invalidation | strong_trend_high |
| 2021-01-28 20:00:00+00:00 | 2021-01-28 20:30:00+00:00 | long | 258.0 | 354.0454 | 351.3649 | -700.64 | -0.767 | 1 | invalidation | weak_trend_high |
| 2021-11-26 18:30:00+00:00 | 2021-11-29 13:30:00+00:00 | short | 116.0 | 430.4869 | 436.2736 | -676.32 | -1.3544 | 1 | invalidation | weak_trend_high |
| 2022-05-20 16:30:00+00:00 | 2022-05-20 19:30:00+00:00 | short | 115.0 | 363.7436 | 368.6769 | -571.56 | -1.3664 | 6 | invalidation | weak_trend_medium |
| 2022-10-10 17:00:00+00:00 | 2022-10-10 17:30:00+00:00 | short | 171.0 | 341.8958 | 344.9845 | -534.06 | -0.9135 | 1 | invalidation | strong_trend_low |

## First 10 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020-08-26 16:30:00+00:00 | 2020-08-26 18:30:00+00:00 | long | 234.0 | 320.342 | 320.0102 | -85.13 | -0.1136 | 4 | stop | strong_trend_medium |
| 2020-08-26 19:30:00+00:00 | 2020-08-26 19:30:00+00:00 | long | 199.0 | 321.0621 | 320.8979 | -39.06 | -0.0611 | 0 | force_close | strong_trend_high |
| 2020-08-26 20:00:00+00:00 | 2020-08-26 20:00:00+00:00 | long | 215.0 | 320.9421 | 321.3179 | 73.88 | 0.1071 | 0 | force_close | strong_trend_high |
| 2020-08-26 20:30:00+00:00 | 2020-08-26 20:30:00+00:00 | long | 172.0 | 321.6222 | 321.3979 | -44.11 | -0.0797 | 0 | force_close | strong_trend_medium |
| 2020-09-01 20:00:00+00:00 | 2020-09-01 20:00:00+00:00 | long | 205.0 | 325.4925 | 325.6274 | 20.98 | 0.0314 | 0 | force_close | weak_trend_medium |
| 2020-09-01 20:30:00+00:00 | 2020-09-01 20:30:00+00:00 | long | 174.0 | 325.9026 | 325.8374 | -17.01 | -0.03 | 0 | force_close | weak_trend_low |
| 2020-09-02 17:30:00+00:00 | 2020-09-02 19:30:00+00:00 | long | 268.0 | 329.1429 | 330.217 | 279.0 | 0.3163 | 4 | force_close | weak_trend_high |
| 2020-09-02 20:00:00+00:00 | 2020-09-02 20:00:00+00:00 | long | 158.0 | 330.343 | 330.457 | 12.78 | 0.0245 | 0 | force_close | weak_trend_high |
| 2020-09-03 14:30:00+00:00 | 2020-09-03 15:00:00+00:00 | short | 136.0 | 325.4774 | 323.4359 | 273.25 | 0.6173 | 1 | stop | weak_trend_high |
| 2020-09-03 15:30:00+00:00 | 2020-09-03 19:30:00+00:00 | short | 86.0 | 320.5079 | 318.9319 | 132.8 | 0.4818 | 8 | force_close | weak_trend_high |

## Last 10 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-15 20:00:00+00:00 | 2026-04-15 20:00:00+00:00 | long | 85.0 | 700.07 | 699.3301 | -68.84 | -0.1157 | 0 | force_close | strong_trend_low |
| 2026-04-17 15:00:00+00:00 | 2026-04-17 17:00:00+00:00 | long | 93.0 | 710.561 | 709.698 | -86.87 | -0.1315 | 4 | stop | strong_trend_high |
| 2026-04-30 19:30:00+00:00 | 2026-04-30 19:30:00+00:00 | long | 75.0 | 719.1519 | 718.3382 | -66.42 | -0.1231 | 0 | force_close | weak_trend_high |
| 2026-05-06 18:30:00+00:00 | 2026-05-06 19:30:00+00:00 | long | 84.0 | 733.0933 | 733.6966 | 44.52 | 0.0723 | 2 | force_close | strong_trend_low |
| 2026-05-12 15:30:00+00:00 | 2026-05-12 17:00:00+00:00 | short | 80.0 | 732.2868 | 734.4034 | -175.21 | -0.2991 | 3 | invalidation | weak_trend_high |
| 2026-05-13 19:00:00+00:00 | 2026-05-13 19:30:00+00:00 | long | 77.0 | 742.7443 | 742.2258 | -45.64 | -0.0798 | 1 | force_close | weak_trend_medium |
| 2026-05-14 15:30:00+00:00 | 2026-05-14 17:00:00+00:00 | long | 87.0 | 748.5698 | 746.7758 | -162.58 | -0.2496 | 3 | stop | weak_trend_high |
| 2026-05-18 19:00:00+00:00 | 2026-05-18 19:00:00+00:00 | short | 77.0 | 733.6516 | 735.9495 | -182.61 | -0.3232 | 0 | stop | weak_trend_high |
| 2026-05-20 16:00:00+00:00 | 2026-05-20 17:30:00+00:00 | long | 90.0 | 740.334 | 739.756 | -58.68 | -0.0881 | 3 | invalidation | weak_trend_high |
| 2026-05-22 17:30:00+00:00 | 2026-05-22 17:30:00+00:00 | long | 90.0 | 748.9949 | 747.1118 | -176.2 | -0.2614 | 0 | stop | weak_trend_low |
