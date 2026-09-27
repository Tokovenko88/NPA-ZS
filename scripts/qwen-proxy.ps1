$port = 3000
$listening = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "Qwen2API already running: http://127.0.0.1:$port" -ForegroundColor Green
    return
}

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path $MyInvocation.MyCommand.Path -Parent }
$repo = (Get-Item $scriptDir).Parent.FullName
$target = Join-Path (Join-Path $repo 'tools') 'Qwen2API'
if (-not (Test-Path (Join-Path $target 'src/server.js'))) {
    Write-Host "ERROR: Qwen2API not found at $target" -ForegroundColor Red
    return
}

# Antivirus/proxy HTTPS interception (Kaspersky, Dr.Web, ESET "scan encrypted
# connections", corporate TLS proxies) replaces certificates with a self-signed
# root. Node.js/bun do not read the Windows trust store, so part of the calls to
# chat.qwen.ai fail with SELF_SIGNED_CERT_IN_CHAIN: the proxy cannot create a chat
# and answers HTTP 500 {"error":"..."} ("qwen2api error (attempt 1/5)" in NPA-ZS).
# Export the Windows roots and pass them via NODE_EXTRA_CA_CERTS - the variable is
# read at process start, so it must be set by the launcher, not in the proxy .env.
$caPem = $null
$caScript = Join-Path $scriptDir 'export_system_ca.ps1'
if (Test-Path $caScript) {
    $caPem = & powershell -NoProfile -ExecutionPolicy Bypass -File $caScript -Quiet 2>$null | Select-Object -Last 1
}
if ($caPem -and (Test-Path $caPem)) {
    $env:NODE_EXTRA_CA_CERTS = $caPem
    Write-Host "TLS: extra CA bundle: $caPem" -ForegroundColor Gray
} else {
    Write-Host 'TLS: CA bundle not built (scripts\export_system_ca.ps1) - antivirus HTTPS interception may cause HTTP 500.' -ForegroundColor Yellow
}

Write-Host "Starting Qwen2API at http://127.0.0.1:$port ..." -ForegroundColor Cyan
$logDir = Join-Path $repo 'data'
$logDir = Join-Path $logDir 'logs'
$log = Join-Path $logDir 'qwen2api-proxy.log'
$bun = if (Test-Path "$env:USERPROFILE\.bun\bin\bun.exe") { "$env:USERPROFILE\.bun\bin\bun.exe" } else { 'bun.exe' }
Start-Process -FilePath $bun `
    -ArgumentList '--no-env-file', 'src/server.js' `
    -WorkingDirectory $target `
    -NoNewWindow `
    -RedirectStandardOutput $log `
    -RedirectStandardError ($log + '.err') `
    -PassThru | Out-Null

Start-Sleep -Seconds 5
$listening = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "Qwen2API running: http://127.0.0.1:$port" -ForegroundColor Green
    Write-Host "Log: $log" -ForegroundColor Gray
} else {
    Write-Host "Check log: $log" -ForegroundColor Yellow
}
