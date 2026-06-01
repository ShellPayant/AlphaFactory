# =====================================================================
# AlphaFactory — interactive .env key setter
#
# Right-click this file -> "Run with PowerShell".
#
# What it does:
#   1. Creates .env from .env.example if .env doesn't exist yet
#   2. Prompts you for your Alpaca paper API Key ID
#   3. Prompts you for your Alpaca paper Secret Key (input is hidden)
#   4. Writes both into .env, preserving everything else
#   5. Confirms what was set (Secret shown only as length)
#
# Safe to re-run anytime — just overwrites the two key lines.
# =====================================================================

$ErrorActionPreference = "Stop"

function Write-OK($msg)   { Write-Host "    OK: $msg"  -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    !!  $msg"  -ForegroundColor Yellow }
function Write-Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
Write-Host "Project root: $projectRoot" -ForegroundColor DarkGray

$envFile     = Join-Path $projectRoot ".env"
$envExample  = Join-Path $projectRoot ".env.example"

# 1. Make sure .env exists
Write-Step "Checking for .env..."
if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $envExample)) {
        Write-Error "Neither .env nor .env.example found at $projectRoot. Re-clone or restore the repo."
        exit 1
    }
    Copy-Item $envExample $envFile
    Write-OK ".env created from .env.example"
} else {
    Write-OK ".env already exists"
}

# 2. Prompt for Key ID (plain text — it's not secret)
Write-Step "Enter your Alpaca PAPER API Key ID"
Write-Host "    (starts with PK, about 20 characters — get it from app.alpaca.markets Home page)" -ForegroundColor DarkGray
$keyId = Read-Host "    ALPACA_API_KEY"

if ([string]::IsNullOrWhiteSpace($keyId)) {
    Write-Error "Empty key. Aborting."
    exit 1
}
if (-not $keyId.StartsWith("PK")) {
    Write-Warn "Your key does NOT start with PK. That's the live-trading key prefix (AK), not paper."
    Write-Warn "If you want paper trading (recommended), switch to Paper mode in the dashboard top-left toggle"
    Write-Warn "and use that key instead. Continuing anyway — abort with Ctrl+C if you want to redo."
    Start-Sleep -Seconds 2
}

# 3. Prompt for Secret Key (hidden input — SecureString)
Write-Step "Enter your Alpaca PAPER Secret Key"
Write-Host "    (about 40 characters — input will be HIDDEN as you type/paste; this is normal)" -ForegroundColor DarkGray
$secureSecret = Read-Host "    ALPACA_SECRET_KEY" -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
$secretPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null

if ([string]::IsNullOrWhiteSpace($secretPlain)) {
    Write-Error "Empty secret. Aborting."
    exit 1
}

# 4. Rewrite .env, replacing the two lines
Write-Step "Writing .env..."
$lines = Get-Content $envFile
$newLines = New-Object System.Collections.Generic.List[string]
$setKeyId = $false
$setSecret = $false

foreach ($line in $lines) {
    if ($line -match '^\s*ALPACA_API_KEY\s*=') {
        $newLines.Add("ALPACA_API_KEY=$keyId")
        $setKeyId = $true
    } elseif ($line -match '^\s*ALPACA_SECRET_KEY\s*=') {
        $newLines.Add("ALPACA_SECRET_KEY=$secretPlain")
        $setSecret = $true
    } else {
        $newLines.Add($line)
    }
}

# In case the lines were missing entirely, append them.
if (-not $setKeyId)  { $newLines.Add("ALPACA_API_KEY=$keyId") }
if (-not $setSecret) { $newLines.Add("ALPACA_SECRET_KEY=$secretPlain") }

# Write back as UTF-8 WITHOUT BOM (BOMs break dotenv parsers)
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($envFile, $newLines, $utf8NoBom)

Write-OK ".env updated"

# 5. Confirmation (don't echo the secret)
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Done." -ForegroundColor Green
Write-Host "  ALPACA_API_KEY    = $keyId" -ForegroundColor Green
Write-Host "  ALPACA_SECRET_KEY = [hidden, $($secretPlain.Length) chars]" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next step: double-click scripts\pull_data.bat to download SPY + QQQ 5-min bars." -ForegroundColor Cyan
Write-Host ""

# Clear plain secret from memory
$secretPlain = $null
[System.GC]::Collect()

Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
