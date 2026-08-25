<#
.SYNOPSIS
    1-Click / 1-Command system updater for Dao Vang PeakPulse on Windows.

.DESCRIPTION
    Pulls the latest commits from GitHub origin/main, updates Python dependencies,
    rebuilds frontend assets (if needed), cleanly restarts background scheduled tasks /
    supervisors without lock conflicts, and verifies system health.

.EXAMPLE
    .\scripts\update.ps1
    .\scripts\update.ps1 -CheckOnly
    .\scripts\update.ps1 -Force -DeployRemote
#>

param(
    [switch]$CheckOnly,
    [switch]$Force,
    [switch]$NoRestart,
    [switch]$NoFrontend,
    [switch]$DeployRemote,
    [switch]$NonInteractive,
    [string]$Remote = "origin",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "         DAO VANG PEAKPULSE - ONE CLICK SYSTEM UPDATER          " -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Thu muc du an: $root" -ForegroundColor DarkGray
Write-Host "Thoi gian: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
Write-Host ""

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "[ERROR] Khong tim thay Python virtual environment tai .venv\Scripts\python.exe" -ForegroundColor Red
    Write-Host "Vui long khoi tao .venv truoc khi chay updater." -ForegroundColor Yellow
    exit 1
}

# Run Python UpdateManager via CLI
$cliArgs = @(
    "-m", "dao_vang.cli.main", "system", "update",
    "--remote", $Remote,
    "--branch", $Branch
)

if ($CheckOnly) {
    $cliArgs += "--check-only"
}
if ($Force) {
    $cliArgs += "--force"
}
if ($NoRestart) {
    $cliArgs += "--no-restart"
}
if ($NoFrontend) {
    $cliArgs += "--no-frontend"
}
if ($DeployRemote) {
    $cliArgs += "--remote-deploy"
}

Write-Host "[1/3] Dang kiem tra ma nguon va cap nhat he thong..." -ForegroundColor Green
& $python $cliArgs
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "[WARN] Qua trinh cap nhat hoan tat voi ma: $exitCode" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "   HE THONG DAO VANG DA CAP NHAT VA SAN SANG HOAT DONG!        " -ForegroundColor Green
    Write-Host "================================================================" -ForegroundColor Cyan
}

# Health Check Probe
if (-not $CheckOnly -and -not $NoRestart) {
    Write-Host ""
    Write-Host "[2/3] Kiem tra suc khoe he thong (Health Check)..." -ForegroundColor Cyan
    Start-Sleep -Seconds 2
    try {
        $ports = @(8001, 8000)
        $tested = $false
        foreach ($p in $ports) {
            $resp = Invoke-RestMethod -Uri "http://localhost:$p/api/status" -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($resp) {
                Write-Host "[OK] Web API Server (Port $p): HEALTHY (Status: $($resp.status))" -ForegroundColor Green
                $tested = $true
                break
            }
        }
        if (-not $tested) {
            Write-Host "[INFO] Web API Server dang khoi dong lai trong vai giay toi..." -ForegroundColor DarkYellow
        }
    } catch {
        Write-Host "[INFO] Web API Server dang tai..." -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "[3/3] Hoan tat tien trinh cap nhat." -ForegroundColor Cyan

exit $exitCode
