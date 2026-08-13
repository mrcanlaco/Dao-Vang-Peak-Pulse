<#
.SYNOPSIS
    Launch the Đảo Vàng 24/7 scanner daemon.

.DESCRIPTION
    Starts the scanner that polls Binance every 5 minutes, scores with
    a frozen model, and sends Telegram alerts on Distribution signals.

    Prerequisites:
    1. Frozen model exists — run `dao-vang experiment freeze` first.
    2. Telegram bot configured — see docs/TELEGRAM_SETUP.md.
    3. scanner.frozen_model_id set in config or env var.

    To run as a background service, use Task Scheduler or:
        Start-Process powershell -ArgumentList "-File scripts\run_scanner.ps1" -WindowStyle Hidden

.PARAMETER Config
    Path to YAML config file (optional, defaults to built-in).

.PARAMETER ModelId
    Frozen model ID to use (overrides config).

.EXAMPLE
    .\scripts\run_scanner.ps1
    .\scripts\run_scanner.ps1 -Config configs\default.yaml -ModelId frozen_20260803_abc12345
#>
param(
    [string]$Config = "",
    [string]$ModelId = ""
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Đảo Vàng — 24/7 Scanner Daemon" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Set model ID if provided
if ($ModelId) {
    $env:DAO_VANG_SCANNER__FROZEN_MODEL_ID = $ModelId
    Write-Host "Using model: $ModelId" -ForegroundColor Green
}

# Check Telegram config
if (-not $env:DAO_VANG_TELEGRAM__BOT_TOKEN) {
    Write-Host "WARNING: TELEGRAM_BOT_TOKEN not set." -ForegroundColor Yellow
    Write-Host "  See docs\TELEGRAM_SETUP.md for setup instructions." -ForegroundColor Yellow
    Write-Host ""
}

# Check frozen model
if (-not $env:DAO_VANG_SCANNER__FROZEN_MODEL_ID) {
    Write-Host "ERROR: SCANNER__FROZEN_MODEL_ID not set." -ForegroundColor Red
    Write-Host "  Run: dao-vang experiment freeze ..." -ForegroundColor Red
    Write-Host "  Then: set DAO_VANG_SCANNER__FROZEN_MODEL_ID=frozen_..." -ForegroundColor Red
    Write-Host "  Or use -ModelId parameter" -ForegroundColor Red
    exit 1
}

# Build command
$cmdArgs = @("scanner", "start")
if ($Config) {
    $cmdArgs += @("--config", $Config)
}

Write-Host "Starting scanner..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

# Run via uv (preferred) or direct python
try {
    uv run dao-vang @cmdArgs
} catch {
    Write-Host "uv not found, trying python directly..." -ForegroundColor Yellow
    python -m dao_vang @cmdArgs
}
