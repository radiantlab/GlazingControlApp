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

$venvPython = Join-Path $servicePath '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $agentExecutable = $venvPython
    $agentArgs = @('scripts/sensor_agent.py', $Command)
}
else {
    $uvCommand = Get-Command 'uv' -ErrorAction Stop
    $agentExecutable = $uvCommand.Source
    if (-not $env:UV_CACHE_DIR) {
        $env:UV_CACHE_DIR = Join-Path $servicePath '.uv-cache'
    }
    $agentArgs = @(
        'run',
        '--python',
        '3.11',
        'python',
        'scripts/sensor_agent.py',
        $Command
    )
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
