# Backtest Report — `range_mean_reversion` on `SPY`

_Generated 2026-05-25 04:26:17 UTC_

## Configuration

| Setting | Value |
|---|---|
| Strategy | `range_mean_reversion` |
| Symbol | `SPY` |
| Timeframe | `5Min` |
| Starting equity | $100,000.00 |
| Ending equity | $98,157.70 |
| Fee model | slippage=1.0 bps/side, commission/share=0.0 |
| risk_per_trade | 0.0025 |
| force_close_local | 15:30:00 |

## Headline metrics

| Metric | Value |
|---|---|
| Total return | -1.84% |
| CAGR | -0.30% |
| Sharpe (annualized) | -0.16 |
| Sortino (annualized) | -0.18 |
| Max drawdown | -4.05% |
| Time under water | 93.1% |
| Bars in backtest | 123,319 |

## Trade statistics

| Metric | Value |
|---|---|
| Trades | 4 |
| Signals generated | 4 |
| Signals skipped (sizing) | 0 |
| Win rate | 50.0% |
| Avg win | $174.12 |
| Avg loss | -$767.11 |
| Profit factor | 0.23 |
| Expectancy / trade | -$296.49 |
| Avg bars held | 3.8 |
| Max consec. wins / losses | 2 / 1 |
| Best trade | $298.35 |
| Worst trade | -$1,438.85 |

## Exit reason breakdown

| Reason | Count |
|---|---|
| target | 3 |
| stop | 1 |

## P&L by regime

| Regime | Trades | Total P&L | Win rate |
|---|---:|---:|---:|
| `range_medium` | 2 | -$1,140.50 | 50.0% |
| `range_low` | 2 | -$45.47 | 50.0% |

## Best 5 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2025-01-27 18:05:00+00:00 | 2025-01-27 19:15:00+00:00 | long | 326.0 | 588.0788 | 589.0529 | 298.35 | 0.1556 | 14 | target | range_medium |
| 2021-10-27 16:25:00+00:00 | 2021-10-27 16:30:00+00:00 | short | 881.0 | 428.8971 | 428.7976 | 49.89 | 0.0132 | 1 | target | range_low |
| 2026-02-23 13:15:00+00:00 | 2026-02-23 13:15:00+00:00 | short | 73.0 | 684.4615 | 685.6993 | -95.36 | -0.1909 | 0 | target | range_low |
| 2020-12-17 21:00:00+00:00 | 2020-12-17 21:00:00+00:00 | short | 17222.0 | 345.1255 | 345.1745 | -1438.85 | -0.0242 | 0 | stop | range_medium |

## Worst 5 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020-12-17 21:00:00+00:00 | 2020-12-17 21:00:00+00:00 | short | 17222.0 | 345.1255 | 345.1745 | -1438.85 | -0.0242 | 0 | stop | range_medium |
| 2026-02-23 13:15:00+00:00 | 2026-02-23 13:15:00+00:00 | short | 73.0 | 684.4615 | 685.6993 | -95.36 | -0.1909 | 0 | target | range_low |
| 2021-10-27 16:25:00+00:00 | 2021-10-27 16:30:00+00:00 | short | 881.0 | 428.8971 | 428.7976 | 49.89 | 0.0132 | 1 | target | range_low |
| 2025-01-27 18:05:00+00:00 | 2025-01-27 19:15:00+00:00 | long | 326.0 | 588.0788 | 589.0529 | 298.35 | 0.1556 | 14 | target | range_medium |

## First 10 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020-12-17 21:00:00+00:00 | 2020-12-17 21:00:00+00:00 | short | 17222.0 | 345.1255 | 345.1745 | -1438.85 | -0.0242 | 0 | stop | range_medium |
| 2021-10-27 16:25:00+00:00 | 2021-10-27 16:30:00+00:00 | short | 881.0 | 428.8971 | 428.7976 | 49.89 | 0.0132 | 1 | target | range_low |
| 2025-01-27 18:05:00+00:00 | 2025-01-27 19:15:00+00:00 | long | 326.0 | 588.0788 | 589.0529 | 298.35 | 0.1556 | 14 | target | range_medium |
| 2026-02-23 13:15:00+00:00 | 2026-02-23 13:15:00+00:00 | short | 73.0 | 684.4615 | 685.6993 | -95.36 | -0.1909 | 0 | target | range_low |

## Last 10 trades

| entry_ts | exit_ts | side | shares | entry | exit | pnl | pnl_pct | bars | exit_reason | regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020-12-17 21:00:00+00:00 | 2020-12-17 21:00:00+00:00 | short | 17222.0 | 345.1255 | 345.1745 | -1438.85 | -0.0242 | 0 | stop | range_medium |
| 2021-10-27 16:25:00+00:00 | 2021-10-27 16:30:00+00:00 | short | 881.0 | 428.8971 | 428.7976 | 49.89 | 0.0132 | 1 | target | range_low |
| 2025-01-27 18:05:00+00:00 | 2025-01-27 19:15:00+00:00 | long | 326.0 | 588.0788 | 589.0529 | 298.35 | 0.1556 | 14 | target | range_medium |
| 2026-02-23 13:15:00+00:00 | 2026-02-23 13:15:00+00:00 | short | 73.0 | 684.4615 | 685.6993 | -95.36 | -0.1909 | 0 | target | range_low |
