# Backtest Report — `intraday_momentum_spy` on `SPY`

_Generated 2026-05-25 05:24:17 UTC_

## Configuration

| Setting | Value |
|---|---|
| Strategy | `intraday_momentum_spy` |
| Symbol | `SPY` |
| Timeframe | `30m` |
| Starting equity | $100,000.00 |
| Ending equity | $39,779.79 |
| Fee model | slippage=3.0 bps/side, commission/share=0.005 |
| risk_per_trade | 0.0025 |
| max_notional_pct | 1.0 |
| min_stop_pct | 0.0005 |
| force_close_local | 15:30:00 |

## Headline metrics

| Metric | Value |
|---|---|
| Total return | -60.22% |
| CAGR | -54.95% |
| Sharpe (annualized) | -12.03 |
| Sortino (annualized) | -14.08 |
| Max drawdown | -60.32% |
| Time under water | 98.4% |
| Bars in backtest | 22,725 |

## Trade statistics

| Metric | Value |
|---|---|
| Trades | 901 |
| Signals generated | 4175 |
| Signals skipped (sizing) | 16 |
| Signals skipped (max notional cap) | 1710 |
| Signals skipped (min stop guard) | 194 |
| Win rate | 23.5% |
| Avg win | $107.31 |
| Avg loss | -$102.90 |
| Profit factor | 0.32 |
| Expectancy / trade | -$53.44 |
| Avg bars held | 1.5 |
| Max consec. wins / losses | 6 / 38 |
| Best trade | $740.32 |
| Worst trade | -$786.20 |

## Exit reason breakdown

| Reason | Count |
|---|---|
| force_close | 542 |
| invalidation | 189 |
| stop | 170 |

## P&L by regime

| Regime | Trades | Total P&L | Win rate |
|---|---:|---:|---:|
| `weak_trend_high` | 345 | -$21,148.47 | 25.2% |
| `weak_trend_medium` | 184 | -$6,777.90 | 25.5% |
| `weak_trend_low` | 172 | -$9,694.86 | 14.0% |
| `strong_trend_high` | 70 | -$5,594.57 | 21.4% |
| `range_high` | 67 | -$1,957.28 | 37.3% |
| `strong_trend_low` | 48 | -$2,113.92 | 22.9% |
| `strong_trend_medium` | 15 | -$864.47 | 20.0% |

## Best 5 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022-09-13 18:00:00+00:00 | 2022-09-13 19:30:00+00:00 | short | 154.0 | 378.5364 | 373.6121 | 740.32 | 1.27 | 3 | force_close | weak_trend_low |
| 2022-03-07 15:30:00+00:00 | 2022-03-07 20:30:00+00:00 | short | 106.0 | 401.7194 | 395.7987 | 614.48 | 1.443 | 10 | force_close | weak_trend_low |
| 2023-03-09 18:30:00+00:00 | 2023-03-09 20:30:00+00:00 | short | 139.0 | 379.906 | 375.5526 | 588.76 | 1.1149 | 4 | force_close | weak_trend_high |
| 2022-11-10 18:30:00+00:00 | 2022-11-10 20:30:00+00:00 | long | 172.0 | 372.8618 | 376.3171 | 574.02 | 0.8951 | 4 | force_close | weak_trend_medium |
| 2025-02-21 17:30:00+00:00 | 2025-02-21 20:30:00+00:00 | short | 78.0 | 596.8909 | 591.5874 | 399.44 | 0.8579 | 6 | force_close | weak_trend_high |

## Worst 5 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022-01-24 18:30:00+00:00 | 2022-01-24 18:30:00+00:00 | short | 156.0 | 401.9894 | 406.902 | -786.2 | -1.2537 | 0 | invalidation | strong_trend_high |
| 2021-01-28 20:00:00+00:00 | 2021-01-28 20:30:00+00:00 | long | 230.0 | 354.1162 | 351.2946 | -674.36 | -0.828 | 1 | invalidation | weak_trend_high |
| 2021-11-26 18:30:00+00:00 | 2021-11-29 13:30:00+00:00 | short | 98.0 | 430.4008 | 436.3609 | -597.4 | -1.4163 | 1 | invalidation | weak_trend_high |
| 2020-10-30 18:30:00+00:00 | 2020-10-30 19:30:00+00:00 | short | 159.0 | 299.99 | 302.9909 | -492.39 | -1.0323 | 2 | invalidation | weak_trend_high |
| 2022-05-20 16:30:00+00:00 | 2022-05-20 19:30:00+00:00 | short | 92.0 | 363.6709 | 368.7506 | -477.97 | -1.4286 | 6 | invalidation | weak_trend_medium |

## First 10 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020-08-26 16:30:00+00:00 | 2020-08-26 18:30:00+00:00 | long | 221.0 | 320.4061 | 319.9462 | -123.95 | -0.175 | 4 | stop | strong_trend_medium |
| 2020-08-26 19:30:00+00:00 | 2020-08-26 19:30:00+00:00 | long | 189.0 | 321.1263 | 320.8337 | -74.44 | -0.1226 | 0 | force_close | strong_trend_high |
| 2020-08-26 20:00:00+00:00 | 2020-08-26 20:00:00+00:00 | long | 203.0 | 321.0063 | 321.2536 | 29.63 | 0.0455 | 0 | force_close | strong_trend_high |
| 2020-08-26 20:30:00+00:00 | 2020-08-26 20:30:00+00:00 | long | 164.0 | 321.6865 | 321.3336 | -74.51 | -0.1412 | 0 | force_close | strong_trend_medium |
| 2020-09-01 20:00:00+00:00 | 2020-09-01 20:00:00+00:00 | long | 194.0 | 325.5576 | 325.5623 | -19.01 | -0.0301 | 0 | force_close | weak_trend_medium |
| 2020-09-01 20:30:00+00:00 | 2020-09-01 20:30:00+00:00 | long | 166.0 | 325.9678 | 325.7722 | -49.51 | -0.0915 | 0 | force_close | weak_trend_low |
| 2020-09-02 17:30:00+00:00 | 2020-09-02 19:30:00+00:00 | long | 250.0 | 329.2087 | 330.1509 | 209.54 | 0.2546 | 4 | force_close | weak_trend_high |
| 2020-09-02 20:00:00+00:00 | 2020-09-02 20:00:00+00:00 | long | 151.0 | 330.4091 | 330.3909 | -18.48 | -0.037 | 0 | force_close | weak_trend_high |
| 2020-09-03 14:30:00+00:00 | 2020-09-03 15:00:00+00:00 | short | 131.0 | 325.4123 | 323.5006 | 237.07 | 0.5561 | 1 | stop | weak_trend_high |
| 2020-09-03 15:30:00+00:00 | 2020-09-03 19:30:00+00:00 | short | 84.0 | 320.4438 | 318.9957 | 113.19 | 0.4205 | 8 | force_close | weak_trend_high |

## Last 10 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-30 19:30:00+00:00 | 2026-04-30 19:30:00+00:00 | long | 41.0 | 719.2957 | 718.1945 | -54.19 | -0.1837 | 0 | force_close | weak_trend_high |
| 2026-05-06 18:30:00+00:00 | 2026-05-06 19:30:00+00:00 | long | 46.0 | 733.2399 | 733.5499 | 3.91 | 0.0116 | 2 | force_close | strong_trend_low |
| 2026-05-12 15:30:00+00:00 | 2026-05-12 17:00:00+00:00 | short | 43.0 | 732.1403 | 734.5503 | -113.32 | -0.36 | 3 | invalidation | weak_trend_high |
| 2026-05-13 17:00:00+00:00 | 2026-05-13 17:00:00+00:00 | long | 53.0 | 742.3927 | 742.3772 | -12.89 | -0.0328 | 0 | invalidation | range_high |
| 2026-05-13 19:00:00+00:00 | 2026-05-13 19:30:00+00:00 | long | 42.0 | 742.8928 | 742.0773 | -43.81 | -0.1404 | 1 | force_close | weak_trend_medium |
| 2026-05-13 20:00:00+00:00 | 2026-05-13 20:00:00+00:00 | long | 51.0 | 742.6227 | 742.5472 | -15.47 | -0.0408 | 0 | force_close | weak_trend_medium |
| 2026-05-14 15:30:00+00:00 | 2026-05-14 17:00:00+00:00 | long | 47.0 | 748.7195 | 746.6264 | -109.14 | -0.3101 | 3 | stop | weak_trend_high |
| 2026-05-18 19:00:00+00:00 | 2026-05-18 19:00:00+00:00 | short | 42.0 | 733.5049 | 736.0967 | -118.34 | -0.3841 | 0 | stop | weak_trend_high |
| 2026-05-20 16:00:00+00:00 | 2026-05-20 17:30:00+00:00 | long | 48.0 | 740.4821 | 739.6081 | -52.84 | -0.1487 | 3 | invalidation | weak_trend_high |
| 2026-05-22 17:30:00+00:00 | 2026-05-22 17:30:00+00:00 | long | 48.0 | 749.1447 | 746.9624 | -115.75 | -0.3219 | 0 | stop | weak_trend_low |
