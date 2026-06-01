@echo off
REM Double-click to run the Range MR backtest on SPY 5Min.
REM Assumes scripts\pull_data.bat has already populated data\bars\SPY\5Min\.

cd /d "%~dp0\.."
echo Running Range Mean Reversion backtest on SPY 5Min...
echo.
"%USERPROFILE%\.local\bin\uv.exe" run python scripts/run_backtest.py --strategy range_mean_reversion --symbol SPY --timeframe 5Min
echo.
echo ============================================================
echo Done. Report saved under: reports\
echo Press any key to close.
echo ============================================================
pause >nul
