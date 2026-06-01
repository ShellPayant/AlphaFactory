@echo off
REM Double-click to smoke-test the GARCH macro overlay + IsolationForest data-QA layer.
REM First run will `uv sync` to install new deps (arch, scikit-learn). Takes ~30-60s after that.
REM
REM The Python script writes its own log to reports\_macro_smoke_<timestamp>.log,
REM so even if you close this window, the output is preserved.

cd /d "%~dp0\.."

REM Force UTF-8 for Python stdout so Polars' Unicode chars render cleanly.
set PYTHONIOENCODING=utf-8

echo Syncing dependencies (one-time install of arch + scikit-learn)...
"%USERPROFILE%\.local\bin\uv.exe" sync
echo.
echo Running macro overlay + IsolationForest smoke test on SPY 5Min...
echo.
"%USERPROFILE%\.local\bin\uv.exe" run python scripts/run_macro_smoke.py --symbol SPY --timeframe 5Min
echo.
echo ============================================================
echo Done. Log file written under reports\_macro_smoke_*.log
echo Press any key to close.
echo ============================================================
pause >nul
