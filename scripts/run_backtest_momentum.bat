@echo off
REM Double-click to run the Intraday Momentum backtest on SPY.
REM Uses default ALPACA_PAPER fee model (1 bp slippage, free commission).
REM Assumes scripts\pull_data.bat has already populated data\bars\SPY\5Min\.
REM The strategy resamples 5-min bars to 30-min internally.

cd /d "%~dp0\.."
echo Running Intraday Momentum backtest on SPY (alpaca_paper fees, 5min -^> 30min)...
echo Run log will be saved alongside the report under reports\
echo.
"%USERPROFILE%\.local\bin\uv.exe" run python scripts/run_backtest.py --strategy intraday_momentum_spy --symbol SPY --fee-model alpaca_paper
echo.
echo ============================================================
echo Done. Report + run log saved under: reports\
echo Press any key to close.
echo ============================================================
pause >nul
