@echo off
REM Double-click to run walk-forward + Monte Carlo on the Intraday Momentum strategy.
REM Defaults: 18-month train, 6-month test, 6-month step, alpaca_paper fees, 1000 MC sims.
REM Tests G1.5 and G1.6 graduation gates simultaneously. Takes ~1-3 minutes.

cd /d "%~dp0\.."
echo Running walk-forward + Monte Carlo on intraday_momentum_spy SPY...
echo Run log + combined report will be saved under reports\
echo.
"%USERPROFILE%\.local\bin\uv.exe" run python scripts/run_walk_forward.py --strategy intraday_momentum_spy --symbol SPY --fee-model alpaca_paper
echo.
echo ============================================================
echo Done. Report + run log saved under: reports\
echo Press any key to close.
echo ============================================================
pause >nul
