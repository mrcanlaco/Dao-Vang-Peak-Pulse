<#
.SYNOPSIS
    Auto-restarting supervisor for the live web/API server.

    The live server must use data_live and port 8001.  Keeping this separate
    from the development web loop prevents dev.duckdb and live.duckdb from
    being mixed when both environments exist on the same machine.
#>

$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$logDir = Join-Path $root "scripts\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "web_live.log"

# Prevent two copies of this supervisor from writing the same log file and
# fighting over port 8001. This also covers double-clicking run_live.bat while
# the Task Scheduler instance is already running.
$mutexName = "Local\DaoVangWebLiveSupervisor"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$ownsMutex = $false
try {
    $ownsMutex = $mutex.WaitOne(0)
} catch {
    Write-Host "Cannot acquire live web supervisor mutex: $_"
    $mutex.Dispose()
    exit 1
}

if (-not $ownsMutex) {
    Write-Host "Dao Vang live web supervisor is already running. Nothing to start."
    $mutex.Dispose()
    exit 0
}

$existingListener = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($existingListener) {
    Write-Host "Dao Vang live web is already listening on port 8001 (PID=$($existingListener.OwningProcess))."
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    exit 0
}

# Get-NetTCPConnection is not available in some minimal Windows PowerShell
# environments, so keep a netstat fallback for the duplicate-start guard.
$netstatListener = netstat -ano 2>$null |
    Select-String ':8001\s+.*LISTENING\s+\d+' |
    Select-Object -First 1
if ($netstatListener) {
    Write-Host "A process is already listening on port 8001. Nothing to start."
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    exit 0
}

$env:PYTHONPATH = "src"
$env:DAO_VANG_WEB__PORT = "8001"
$env:DAO_VANG_WEB__PUBLIC_URL = "https://trade.comaygiauco.com"
$env:DAO_VANG_PATHS__DATA_DIR = "data_live"
$env:DAO_VANG_PATHS__RAW_DIR = "data_live/raw"
$env:DAO_VANG_PATHS__NORMALIZED_DIR = "data_live/normalized"
$env:DAO_VANG_SCANNER__DB_PATH = "data_live/live.duckdb"
$env:DAO_VANG_SCANNER__FROZEN_MODEL_ID = "frozen_20260811_082824_96df7ec9"
$env:DAO_VANG_SCANNER__OPERATING_MODE = "shadow"
$env:DAO_VANG_SCANNER__SHADOW_TELEGRAM_ENABLED = "true"
$env:DAO_VANG_SELF_LEARNING__ENABLED = "true"
$env:DAO_VANG_SELF_LEARNING__CHECK_INTERVAL_CYCLES = "12"
$env:DAO_VANG_SELF_LEARNING__RECENT_WINDOW_DAYS = "14"
$env:DAO_VANG_SELF_LEARNING__RECENT_SAMPLE_WEIGHT = "2.0"
$env:DAO_VANG_SELF_LEARNING__HISTORICAL_MAX_ROWS = "100000"
$env:DAO_VANG_SELF_LEARNING__STATE_PATH = "artifacts/self_learning/live_state.json"
$env:DAO_VANG_SELF_LEARNING__REPORT_DIR = "artifacts/self_learning/live_runs"
$env:DAO_VANG_DUCKDB_MEMORY_LIMIT = "1GB"
$env:DAO_VANG_DUCKDB_THREADS = "2"
$env:DAO_VANG_DUCKDB_SNAPSHOT_TTL_SECONDS = "30"

function Rotate-Log {
    try {
        if (-not (Test-Path -LiteralPath $logFile)) { return }
        if ((Get-Item -LiteralPath $logFile).Length -lt 50MB) { return }
        $archive = "$logFile.1"
        if (Test-Path -LiteralPath $archive) {
            Remove-Item -LiteralPath $archive -Force
        }
        Move-Item -LiteralPath $logFile -Destination $archive -Force
    } catch {
        # Another legacy supervisor may still have the file open. Keep
        # writing the current log and retry rotation on the next line.
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
    Log "=== live web supervisor started (pid=$PID) ==="

    while ($true) {
        Log "Starting live web/API on port 8001..."
        try {
            & $python -m dao_vang.web.run 8001 2>&1 |
                ForEach-Object {
                    Log ([string]$_)
                }
            $exitCode = $LASTEXITCODE
            Log "Live web exited (exit code $exitCode)."
            if ($exitCode -eq 2) {
                Log "Another live web instance owns the lock. Stopping this supervisor."
                break
            }
        } catch {
            Log "Live web crashed: $_"
        }
        Log "Restarting live web in 10s..."
        Start-Sleep -Seconds 10
    }
} finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
