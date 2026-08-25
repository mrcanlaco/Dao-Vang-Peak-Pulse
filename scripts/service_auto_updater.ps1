<#
.SYNOPSIS
    Auto-updater background supervisor service for Đảo Vàng PeakPulse.
    Runs periodically in the background (via Windows Task Scheduler or loop)
    to detect new commits on GitHub origin/main and auto-update the system.
#>

$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$logDir = Join-Path $root "scripts\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "auto_updater.log"

$mutexName = "Local\DaoVangAutoUpdaterSupervisor"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$ownsMutex = $false
try {
    $ownsMutex = $mutex.WaitOne(0)
} catch {
    Write-Host "Cannot acquire auto-updater supervisor mutex: $_"
    $mutex.Dispose()
    exit 1
}

if (-not $ownsMutex) {
    Write-Host "Dao Vang auto-updater supervisor is already running. Nothing to start."
    $mutex.Dispose()
    exit 0
}

function Rotate-Log {
    try {
        if (-not (Test-Path -LiteralPath $logFile)) { return }
        if ((Get-Item -LiteralPath $logFile).Length -lt 20MB) { return }
        $archive = "$logFile.1"
        if (Test-Path -LiteralPath $archive) {
            Remove-Item -LiteralPath $archive -Force
        }
        Move-Item -LiteralPath $logFile -Destination $archive -Force
    } catch {
        return
    }
}

function Log($msg) {
    Rotate-Log
    $systemNow = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId((Get-Date), 'SE Asia Standard Time')
    $line = "$($systemNow.ToString('yyyy-MM-dd HH:mm:ss')) $msg"
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        try {
            Add-Content -LiteralPath $logFile -Encoding utf8 -Value $line -ErrorAction Stop
            return
        } catch {
            Start-Sleep -Milliseconds 100
        }
    }
    Write-Host $line
}

$python = Join-Path $root ".venv\Scripts\python.exe"

try {
    Log "=== Dao Vang Auto-Updater supervisor started (pid=$PID) ==="

    while ($true) {
        Log "Starting auto-updater daemon cycle..."
        try {
            & $python -m dao_vang.cli.main system auto-updater 2>&1 |
                ForEach-Object {
                    Log ([string]$_)
                }
            $exitCode = $LASTEXITCODE
            Log "Auto-updater process exited (code $exitCode)."
        } catch {
            Log "Auto-updater process error: $_"
        }

        Log "Restarting auto-updater supervisor loop in 30s..."
        Start-Sleep -Seconds 30
    }
} finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
