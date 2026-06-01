@echo off
REM Double-click to pull SPY + QQQ 5-min bars from Alpaca into data/bars/.
REM Requires: .env populated with ALPACA_API_KEY + ALPACA_SECRET_KEY.
REM Edit the symbols / dates / timeframe below for a custom pull.

cd /d "%~dp0\.."
echo Pulling SPY and QQQ 5Min bars from Alpaca...
echo.
"%USERPROFILE%\.local\bin\uv.exe" run python scripts/pull_data.py SPY QQQ --timeframe 5Min --start 2020-01-01
echo.
echo ============================================================
echo Done. Press any key to close.
echo ============================================================
pause >nul
