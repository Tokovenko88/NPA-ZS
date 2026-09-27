<#
.SYNOPSIS
    Exports Windows trusted root CAs into one PEM bundle for Node.js/bun.

.DESCRIPTION
    Antiviruses and corporate proxies (Kaspersky, Dr.Web, ESET, ...) with
    "scan encrypted connections" enabled replace TLS certificates with their own
    self-signed root. Browsers read the Windows trust store, while Node.js and bun
    (including the local Qwen2API server) use their own bundled CA list, so part of
    the connections to chat.qwen.ai fail with SELF_SIGNED_CERT_IN_CHAIN. The proxy
    then answers HTTP 500 {"error":"... Qwen ..."} on chat creation and NPA-ZS logs
    "qwen2api error (attempt 1/5)".

    This script collects the root certificates from Cert:\LocalMachine\Root and
    Cert:\CurrentUser\Root into a single PEM file. A launcher passes its path to
    the runtime through NODE_EXTRA_CA_CERTS (read by Node/bun at process start,
    so it must be set by the launcher, not in the proxy .env).

    The Mozilla roots from certifi (python -c "import certifi") are appended too,
    so the same bundle is also usable by Python requests via REQUESTS_CA_BUNDLE
    without losing any public CA (NODE_EXTRA_CA_CERTS only adds roots, so extra
    entries are harmless there).

    NOTE: keep this file ASCII-only. Windows PowerShell 5.1 parses a BOM-less .ps1
    as ANSI and non-ASCII characters break the parser.

.PARAMETER OutputPath
    Bundle path. Default: data\work_tools\ssl\system-ca-bundle.pem of the NPA-ZS repo.

.PARAMETER MaxAgeDays
    Rebuild the bundle when it is older than this many days (default 7).
    0 means: never check the age, reuse the existing file.

.PARAMETER Force
    Rebuild the bundle even if the existing file is fresh.

.PARAMETER MergeCertifi
    Append the Mozilla roots from certifi (default: on).

.PARAMETER Quiet
    Suppress progress messages (used by qwen-proxy.bat and setup_qwen2api.py).

.OUTPUTS
    System.String - path to the PEM bundle (last line of the output).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\export_system_ca.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\export_system_ca.ps1 -Force -Quiet
#>
[CmdletBinding()]
param(
    [string]$OutputPath = '',
    [ValidateRange(0, 3650)][int]$MaxAgeDays = 7,
    [switch]$Force,
    [bool]$MergeCertifi = $true,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

function Write-Info([string]$Message) {
    if (-not $Quiet) { Write-Host $Message -ForegroundColor Gray }
}

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path $MyInvocation.MyCommand.Path -Parent }
$repo = (Get-Item $scriptDir).Parent.FullName
if (-not $OutputPath) {
    $OutputPath = Join-Path $repo (Join-Path 'data' (Join-Path 'work_tools' (Join-Path 'ssl' 'system-ca-bundle.pem')))
}

# --- Rebuild needed? ---
if ((Test-Path $OutputPath) -and -not $Force) {
    $fresh = $true
    if ($MaxAgeDays -gt 0) {
        $fresh = ((Get-Date) - (Get-Item $OutputPath).LastWriteTime).TotalDays -lt $MaxAgeDays
    }
    if ($fresh) {
        Write-Info "CA bundle is up to date: $OutputPath"
        Write-Output $OutputPath
        return
    }
}

# --- Collect Windows root certificates ---
$certs = @()
foreach ($storeName in @('LocalMachine', 'CurrentUser')) {
    $store = "Cert:\$storeName\Root"
    if (-not (Test-Path $store)) { continue }
    $certs += @(Get-ChildItem $store -ErrorAction SilentlyContinue)
}
if ($certs.Count -eq 0) {
    Write-Warning 'Failed to read Windows root certificates - CA bundle not created.'
    exit 1
}

$builder = New-Object System.Text.StringBuilder
$seen = New-Object 'System.Collections.Generic.HashSet[string]'
$count = 0
foreach ($cert in $certs) {
    if (-not $cert.Thumbprint -or -not $seen.Add($cert.Thumbprint)) { continue }
    $b64 = [Convert]::ToBase64String($cert.RawData)
    [void]$builder.AppendLine("# $($cert.Subject)")
    [void]$builder.AppendLine('-----BEGIN CERTIFICATE-----')
    for ($i = 0; $i -lt $b64.Length; $i += 64) {
        [void]$builder.AppendLine($b64.Substring($i, [Math]::Min(64, $b64.Length - $i)))
    }
    [void]$builder.AppendLine('-----END CERTIFICATE-----')
    $count++
}

$certifiCount = 0
if ($MergeCertifi) {
    $certifiPem = $null
    foreach ($exe in @('python', 'py')) {
        $candidate = $null
        try {
            $candidate = (& $exe -c "import certifi,sys;sys.stdout.write(certifi.where())" 2>$null) | Select-Object -First 1
        } catch {
            $candidate = $null
        }
        if ($candidate -and (Test-Path $candidate)) {
            $certifiPem = $candidate
            break
        }
    }
    if ($certifiPem) {
        $certifiText = [IO.File]::ReadAllText($certifiPem)
        $certifiCount = ([regex]::Matches($certifiText, 'BEGIN CERTIFICATE')).Count
        if ($certifiCount -gt 0) {
            [void]$builder.AppendLine()
            [void]$builder.AppendLine("# --- Mozilla roots from certifi: $certifiPem ---")
            [void]$builder.AppendLine($certifiText.TrimEnd())
            Write-Info "Added Mozilla roots (certifi): $certifiPem ($certifiCount pcs)"
        }
    } else {
        Write-Info 'certifi not found (python unavailable) - bundle contains Windows roots only.'
    }
}

$parent = Split-Path $OutputPath -Parent
if ($parent -and -not (Test-Path $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
# UTF-8 without BOM: OpenSSL/BoringSSL reject a BOM before "-----BEGIN CERTIFICATE-----"
[IO.File]::WriteAllText($OutputPath, $builder.ToString(), (New-Object System.Text.UTF8Encoding($false)))

Write-Info "CA bundle updated: $OutputPath ($count Windows roots + $certifiCount certifi)"
Write-Output $OutputPath
