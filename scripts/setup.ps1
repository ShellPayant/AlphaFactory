# =====================================================================
# AlphaFactory — one-time setup script (Windows)
#
# Right-click this file → "Run with PowerShell".
# If Windows asks about execution policy, see GETTING_STARTED.md.
#
# This script:
#   1. Installs uv (the Python package manager) if missing
#   2. Tells uv to install Python 3.12 (uv manages its own Pythons)
#   3. Installs all AlphaFactory dependencies into a project-local venv
#   4. Runs the test suite to verify everything works
#
# Safe to re-run anytime — every step is idempotent.
# =====================================================================

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "    OK: $msg"  -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    !!  $msg"  -ForegroundColor Yellow }

# Move to the alpha_factory root (parent of this scripts/ folder)
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
Write-Host "Project root: $projectRoot" -ForegroundColor DarkGray

# ---------- 1. Install uv ----------
Write-Step "Checking for uv..."
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Write-Warn "uv not found. Installing via the official installer..."
    # Official installer — small, signed, from Astral (Ruff authors)
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # uv installs to %USERPROFILE%\.local\bin — add to PATH for this session
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        Write-Error "uv installation failed. Install manually from https://astral.sh/uv/ and re-run this script."
        exit 1
    }
}
Write-OK "uv $((uv --version) -replace 'uv ', '')"

# ---------- 2. Install Python 3.12 (uv manages this) ----------
Write-Step "Ensuring Python 3.12 is available (uv will download if needed)..."
uv python install 3.12
Write-OK "Python 3.12 ready"

# ---------- 3. Install project dependencies ----------
Write-Step "Installing AlphaFactory dependencies (this can take 2-5 minutes the first time)..."
uv sync --extra dev
Write-OK "Dependencies installed into .venv/"

# ---------- 4. Run tests ----------
Write-Step "Running the test suite to verify the install..."
$testResult = $true
try {
    uv run pytest -q
} catch {
    $testResult = $false
}

Write-Host ""
if ($testResult) {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  Setup complete. Tests passed. You are ready to go." -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host "  Setup finished, but some tests failed." -ForegroundColor Yellow
    Write-Host "  Copy the output above and paste it back to Claude." -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Yellow
}

Write-Host "`nPress any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
