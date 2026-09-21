param([switch]$Wait)

$port = 9655
$listening = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "FreeDeepseekAPI already running: http://127.0.0.1:$port" -ForegroundColor Green
    return
}

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path $MyInvocation.MyCommand.Path -Parent }
$repo = (Get-Item $scriptDir).Parent.FullName
$target = Join-Path (Join-Path $repo 'tools') 'FreeDeepseekAPI'
if (-not (Test-Path (Join-Path $target 'server.js'))) {
    Write-Host "ERROR: FreeDeepseekAPI not found at $target" -ForegroundColor Red
    return
}

Write-Host "Starting FreeDeepseekAPI at http://127.0.0.1:$port ..." -ForegroundColor Cyan
$env:NON_INTERACTIVE = '1'
$logDir = Join-Path $repo 'data'
$logDir = Join-Path $logDir 'logs'
$log = Join-Path $logDir 'free-deepseek-proxy.log'
$npm = if (Test-Path 'C:\Program Files\nodejs\npm.cmd') { 'C:\Program Files\nodejs\npm.cmd' } else { 'npm.cmd' }
Start-Process -FilePath $npm `
    -ArgumentList 'start' `
    -WorkingDirectory $target `
    -NoNewWindow `
    -RedirectStandardOutput $log `
    -RedirectStandardError ($log + '.err') `
    -PassThru | Out-Null

if ($Wait) {
    Start-Process -FilePath 'http://127.0.0.1:' + $port
    Write-Host "Opened http://127.0.0.1:$port - waiting..." -ForegroundColor Yellow
    while ((Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue)) { Start-Sleep -Seconds 2 }
    Write-Host "Proxy stopped." -ForegroundColor Yellow
} else {
    Start-Sleep -Seconds 5
    $listening = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($listening) {
        Write-Host "FreeDeepseekAPI running: http://127.0.0.1:$port" -ForegroundColor Green
        Write-Host "Log: $log" -ForegroundColor Gray
    } else {
        Write-Host "Check log: $log" -ForegroundColor Yellow
    }
}
