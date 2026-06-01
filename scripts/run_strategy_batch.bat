@echo off
REM Double-click to batch-test 7 daily swing strategy candidates on SPY + QQQ.
REM Walk-forward + Monte Carlo on each (14 pairs total). Takes ~5-15 minutes.
REM
REM Results land in reports\_batch_<timestamp>\:
REM   INDEX.md           -- ranked summary table, open this first
REM   <strategy>_<sym>.md -- per-pair walk-forward + MC detail
REM   run.log            -- full console output

cd /d "%~dp0\.."

set PYTHONIOENCODING=utf-8

echo Syncing dependencies (no-op if already synced)...
"%USERPROFILE%\.local\bin\uv.exe" sync
echo.
echo Running 7-strategy x 2-symbol batch through walk-forward + Monte Carlo...
echo This will take ~5-15 minutes. Output streams to console AND to reports\_batch_*\run.log.
echo.
"%USERPROFILE%\.local\bin\uv.exe" run python scripts/run_strategy_batch.py
echo.
echo ============================================================
echo BATCH DONE. Open the newest reports\_batch_*\INDEX.md to see
echo the ranking. PASS rows are candidates worth paper-trading.
echo Press any key to close.
echo ============================================================
pause >nul
