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
# Without uv, fall back to whatever svc/.venv already holds.
$uvCommand = Get-Command 'uv' -ErrorAction SilentlyContinue
$venvPython = Join-Path $servicePath '.venv\Scripts\python.exe'
if ($uvCommand) {
    $agentExecutable = $uvCommand.Source
    if (-not $env:UV_CACHE_DIR) {
        $env:UV_CACHE_DIR = Join-Path $servicePath '.uv-cache'
    }
    $agentArgs = @(
        'run',
        '--frozen',
        '--no-dev',
        'python',
        'scripts/sensor_agent.py',
        $Command
    )
}
elseif (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    # Without uv nothing refreshes the venv, so refuse one built for another
    # Python version instead of failing later with an unreadable error.
    $wantedPython = (Get-Content -LiteralPath (Join-Path $servicePath '.python-version') -TotalCount 1).Trim()
    $venvVersion = (& $venvPython -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')").Trim()
    if ($venvVersion -ne $wantedPython) {
        throw "svc\.venv uses Python $venvVersion but this version needs Python $wantedPython. Install uv from https://docs.astral.sh/uv/ and run this script again; it will set everything up."
    }
    $agentExecutable = $venvPython
    $agentArgs = @('scripts/sensor_agent.py', $Command)
}
else {
    throw "Neither uv nor $venvPython was found. Install uv from https://docs.astral.sh/uv/ and run this script again."
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
