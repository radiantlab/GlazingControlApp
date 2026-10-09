#requires -Version 5.1

<#
.SYNOPSIS
Runs the native Windows sensor agent in the foreground.

.DESCRIPTION
This is the Task Scheduler entry point for continuous production acquisition.
The Python agent loads svc/.env.production (falling back to svc/.env), owns the
physical COM ports, keeps an agent-only durable outbox, and sends idempotent
events to POST /sensors/ingest. The API container remains the sole audit.db
writer.
#>

[CmdletBinding()]
param(
    [ValidateSet('continuous', 'once', 'list-ports')]
    [string]$Command = 'continuous',

    [string]$ServiceDirectory = (Join-Path $PSScriptRoot '..\..\svc'),

    [string]$ConfigPath,

    [string]$DataDirectory,

    [string]$OutboxPath,

    [string]$Endpoint,

    [string]$AgentId
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$servicePath = (Resolve-Path -LiteralPath $ServiceDirectory).Path
$agentScript = Join-Path $servicePath 'scripts\sensor_agent.py'
if (-not (Test-Path -LiteralPath $agentScript -PathType Leaf)) {
    throw "Sensor Agent entry point does not exist: $agentScript"
}

# Prefer uv: it reads svc/.python-version and uv.lock and brings svc/.venv up to
# date first, so an upgrade cannot leave the agent on a stale interpreter or
# stale packages. The first run after an upgrade needs internet access once.
# Without uv, use svc/.venv only if it was built for the Python version in
# svc/.python-version; otherwise stop and tell the operator to install uv.
$installUvHint = 'Install uv from https://docs.astral.sh/uv/ and run this script again; it will set everything up.'
$uvCommand = Get-Command 'uv' -ErrorAction SilentlyContinue
$venvPython = Join-Path $servicePath '.venv\Scripts\python.exe'
if ($uvCommand) {
    $agentExecutable = $uvCommand.Source
    if (-not $env:UV_CACHE_DIR) {
        $env:UV_CACHE_DIR = Join-Path $servicePath '.uv-cache'
    }
    # Sync as its own step so a failed install gets a plain message, not an
    # agent error. The usual causes are no internet on the first run after an
    # update, or a running agent task holding files in svc\.venv.
    $syncExitCode = 1
    $syncError = $null
    try {
        & $agentExecutable sync --frozen --no-dev --quiet --directory $servicePath
        $syncExitCode = $LASTEXITCODE
    }
    catch {
        $syncError = $_.Exception.Message.TrimEnd(".")
    }
    if ($syncExitCode -ne 0) {
        $syncDetail = if ($syncError) { $syncError } else { "uv exit code $syncExitCode; its message is above" }
        throw "uv could not install Python or the Sensor Agent packages ($syncDetail). The first run on a new PC, and the first run after an update to Python or the agent's packages, needs internet. Connect this PC to the internet, or if it already has internet, stop the Sensor Agent scheduled task. Then run this script again."
    }
    # --no-sync skips the install step above and implies --frozen.
    $agentArgs = @(
        'run',
        '--no-sync',
        'python',
        'scripts/sensor_agent.py',
        $Command
    )
}
elseif (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    # Nothing refreshes the venv without uv. Any failure to confirm its Python
    # version (missing .python-version, a venv whose base Python was removed)
    # ends in the same readable message instead of a PowerShell error.
    $wantedPython = $null
    $venvVersion = $null
    try {
        $wantedPython = "$(Get-Content -LiteralPath (Join-Path $servicePath '.python-version') -TotalCount 1)".Trim()
        $venvVersion = "$(& $venvPython -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null)".Trim()
        if ($LASTEXITCODE -ne 0) {
            $venvVersion = $null
        }
    }
    catch {
        $venvVersion = $null
    }
    if (-not $wantedPython -or -not $venvVersion) {
        throw "svc\.venv could not be checked against svc\.python-version. $installUvHint"
    }
    if ($venvVersion -ne $wantedPython) {
        throw "svc\.venv uses Python $venvVersion but this checkout needs Python $wantedPython. $installUvHint"
    }
    $agentExecutable = $venvPython
    $agentArgs = @('scripts/sensor_agent.py', $Command)
}
else {
    throw "Neither uv nor svc\.venv was found. $installUvHint"
}

if ($Command -ne 'list-ports') {
    if ($ConfigPath) {
        $agentArgs += @('--config', $ConfigPath)
    }
    if ($DataDirectory) {
        $agentArgs += @('--data-dir', $DataDirectory)
    }
    if ($OutboxPath) {
        $agentArgs += @('--outbox', $OutboxPath)
    }
    if ($Endpoint) {
        $agentArgs += @('--endpoint', $Endpoint)
    }
    if ($AgentId) {
        $agentArgs += @('--agent-id', $AgentId)
    }
}

Push-Location -LiteralPath $servicePath
try {
    & $agentExecutable @agentArgs
    $agentExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($null -eq $agentExitCode) {
    $agentExitCode = 1
}
exit $agentExitCode
