#requires -Version 5.1

<#
.SYNOPSIS
Starts, stops, or reports on the production Control Center containers.

.DESCRIPTION
Headless entry point for the operator docs, Task Scheduler, and the #75
double-click launcher. Exit codes: 0 success (including status: degraded),
1 engine not installed or not running, 2 configuration, 3 Compose, 4 health
check timed out.

DRAFT (issue #68): only Start step 1, finding the container engine and
starting a stopped Podman machine, is implemented. The configuration,
Compose, and health steps, and Stop and Status beyond the engine check, are
not written yet.
#>

[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status')]
    [string]$Action = 'Start',

    [string]$EnvFile = (Join-Path $PSScriptRoot '..\svc\.env.production'),

    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 30,

    [switch]$Build
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot 'ControlCenter.Common.ps1')

try {
    $engine = Resolve-ControlCenterEngine -StartMachine:($Action -eq 'Start')
}
catch {
    $reason = Get-ControlCenterErrorReason -ErrorRecord $_
    # Nothing can be running in a stopped machine, so Stop has nothing to do.
    if ($Action -eq 'Stop' -and $reason -eq 'MachineStopped') {
        Write-Host 'The Podman machine is stopped, so the app is not running.'
        exit 0
    }
    [Console]::Error.WriteLine($_.Exception.Message)
    exit (Get-ControlCenterExitCode -ErrorRecord $_)
}

$started = ''
if ($engine.MachineStarted) {
    $started = ' (machine started)'
}
Write-Host "Container engine: $($engine.Name)$started"
Write-Warning (
    'Draft: only the container engine step is implemented. Configuration, ' +
    'Compose, and health checks are not written yet.'
)
exit 0
