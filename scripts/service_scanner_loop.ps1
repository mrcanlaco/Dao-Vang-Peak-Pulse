<#
.SYNOPSIS
    Auto-restarting wrapper for the scanner daemon, meant to be run by
    Windows Task Scheduler at system startup.

.DESCRIPTION
    `dao-vang scanner start` runs forever, but if it crashes (bad data,
    unhandled exception, network blip) nothing brings it back. This loop
    restarts it automatically with a short backoff, and logs each
    restart so failures are visible in scripts\logs\scanner_live.log.
#>

param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "..\configs\live.yaml"),
    [int]$RestartDelaySeconds = 10,
    [int]$MaxLogBytes = 50MB
)

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

# Bound DuckDB's memory and parallelism for the long-running live process.
# The workload spills to data_live\duckdb_temp when an analytic query needs
# more working space instead of taking all RAM from the desktop.
$env:DAO_VANG_DUCKDB_MEMORY_LIMIT = "1GB"
$env:DAO_VANG_DUCKDB_THREADS = "2"
$env:DAO_VANG_DUCKDB_SNAPSHOT_TTL_SECONDS = "30"
# Telegram is the live Radar reporting channel. Force the intended mode here
# so a long-lived parent process cannot restore a stale production override.
$env:DAO_VANG_SCANNER__OPERATING_MODE = "shadow"
$env:DAO_VANG_SCANNER__MAX_COINS = "150"
$env:DAO_VANG_SCANNER__SHADOW_TELEGRAM_ENABLED = "true"
$env:DAO_VANG_WEB__PUBLIC_URL = "https://trade.comaygiauco.com"

$logDir = Join-Path $root "scripts\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "scanner_live.log"
$config = (Resolve-Path $ConfigPath).Path

if (-not (Test-Path -LiteralPath $config)) {
    throw "Scanner config not found: $config"
}

# Prevent two supervisors from repeatedly fighting over scanner.lock. This
# covers Task Scheduler plus a manual start of run_scanner_live.bat.
$mutexName = "Local\DaoVangScannerLiveSupervisor"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$ownsMutex = $false
try {
    $ownsMutex = $mutex.WaitOne(0)
} catch {
    Write-Host "Cannot acquire live scanner supervisor mutex: $_"
    $mutex.Dispose()
    exit 1
}

if (-not $ownsMutex) {
    Write-Host "Dao Vang live scanner supervisor is already running. Nothing to start."
    $mutex.Dispose()
    exit 0
}

function Rotate-Log {
    if (-not (Test-Path -LiteralPath $logFile)) {
        return
    }
    if ((Get-Item -LiteralPath $logFile).Length -lt $MaxLogBytes) {
        return
    }
    $archive = "$logFile.1"
    if (Test-Path -LiteralPath $archive) {
        Remove-Item -LiteralPath $archive -Force
    }
    Move-Item -LiteralPath $logFile -Destination $archive -Force
}

function Log($msg) {
    Rotate-Log
    $systemNow = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId((Get-Date), 'SE Asia Standard Time')
    $line = "$($systemNow.ToString('yyyy-MM-dd HH:mm:ss')) $msg"
    Add-Content -Path $logFile -Value $line
}

try {
    Log "=== service_scanner_loop started (pid=$PID, config=$config) ==="

    while ($true) {
        Log "Starting scanner with config $config..."
        try {
            & "$root\.venv\Scripts\dao-vang.exe" scanner start --config $config 2>&1 |
                ForEach-Object {
                    Rotate-Log
                    Add-Content -LiteralPath $logFile -Encoding utf8 -Value ([string]$_)
                }
            $exitCode = $LASTEXITCODE
            Log "Scanner exited (exit code $exitCode)."
        } catch {
            Log "Scanner crashed: $_"
        }
        Log "Restarting in ${RestartDelaySeconds}s..."
        Start-Sleep -Seconds $RestartDelaySeconds
    }
} finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
