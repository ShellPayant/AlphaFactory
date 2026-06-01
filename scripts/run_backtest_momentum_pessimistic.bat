@echo off
REM Double-click to run the Intraday Momentum backtest on SPY with PESSIMISTIC fees.
REM PESSIMISTIC = 3 bps slippage + $0.005/share commission. Stress-test run.
REM Per the spec's validation plan, both ALPACA_PAPER and PESSIMISTIC must pass G1.

cd /d "%~dp0\.."
echo Running Intraday Momentum backtest on SPY (PESSIMISTIC fees, 5min -^> 30min)...
echo Run log will be saved alongside the report under reports\
echo.
"%USERPROFILE%\.local\bin\uv.exe" run python scripts/run_backtest.py --strategy intraday_momentum_spy --symbol SPY --fee-model pessimistic
echo.
echo ============================================================
echo Done. Report + run log saved under: reports\
echo Press any key to close.
echo ============================================================
pause >nul
