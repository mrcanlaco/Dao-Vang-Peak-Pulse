<#
.SYNOPSIS
    Auto-restarting wrapper for the Streamlit web UI, meant to be run by
    Windows Task Scheduler at system startup.
#>

$root = "D:\Coding\dao_vang"
Set-Location $root

$env:DAO_VANG_DUCKDB_MEMORY_LIMIT = "1GB"
$env:DAO_VANG_DUCKDB_THREADS = "2"
$env:DAO_VANG_DUCKDB_SNAPSHOT_TTL_SECONDS = "30"

$logDir = Join-Path $root "scripts\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "web.log"
$maxLogBytes = 50MB

function Rotate-Log {
    if (-not (Test-Path -LiteralPath $logFile)) { return }
    if ((Get-Item -LiteralPath $logFile).Length -lt $maxLogBytes) { return }
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

Log "=== service_web_loop started (pid=$PID) ==="

while ($true) {
    Log "Starting web UI..."
    try {
        & "$root\.venv\Scripts\dao-vang-ui.exe" 2>&1 |
            ForEach-Object {
                Rotate-Log
                Add-Content -LiteralPath $logFile -Encoding utf8 -Value ([string]$_)
            }
        Log "Web UI exited normally (exit code $LASTEXITCODE)."
    } catch {
        Log "Web UI crashed: $_"
    }
    Log "Restarting in 10s..."
    Start-Sleep -Seconds 10
}
