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

# Antivirus/proxy HTTPS interception (Kaspersky, Dr.Web, ESET "scan encrypted
# connections", corporate TLS proxies) replaces certificates with a self-signed
# root. Node.js (npm start) does not read the Windows trust store, so calls to the
# upstream provider fail intermittently. Export the Windows roots and pass them via
# NODE_EXTRA_CA_CERTS - read at process start, hence set here, not in the proxy .env.
$caPem = $null
$caScript = Join-Path $scriptDir 'export_system_ca.ps1'
if (Test-Path $caScript) {
    $caPem = & powershell -NoProfile -ExecutionPolicy Bypass -File $caScript -Quiet 2>$null | Select-Object -Last 1
}
if ($caPem -and (Test-Path $caPem)) {
    $env:NODE_EXTRA_CA_CERTS = $caPem
    Write-Host "TLS: extra CA bundle: $caPem" -ForegroundColor Gray
} else {
    Write-Host 'TLS: CA bundle not built (scripts\export_system_ca.ps1) - antivirus HTTPS interception may cause request failures.' -ForegroundColor Yellow
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
