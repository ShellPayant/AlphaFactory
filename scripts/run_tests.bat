@echo off
REM Double-click this file to run the AlphaFactory test suite.
REM Uses the venv created by setup.ps1. Run setup.ps1 first if you haven't.

cd /d "%~dp0\.."
echo Running AlphaFactory tests...
echo.
"%USERPROFILE%\.local\bin\uv.exe" run pytest -v
echo.
echo ============================================================
echo Done. Press any key to close.
echo ============================================================
pause >nul
