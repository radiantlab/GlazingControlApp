#requires -Version 5.1

<#
.SYNOPSIS
Starts, stops, or reports on the production Control Center container.

.DESCRIPTION
Headless entry point for the operator docs, Task Scheduler, and the #75
double-click launcher. Start checks Docker and the production env file, starts
the stack with docker compose, and waits for /health. Stop runs compose down
and leaves host data untouched. Status reports the container and /health and
starts nothing.

Exit codes: 0 success (including status: degraded), 1 Docker not installed or
not running, 2 configuration (env file, paths, audit.db, port conflict, wrong
environment), 3 Compose failed or the container is not running, 4 /health did
not answer in time, 5 unexpected error in this script.
#>

[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status')]
    [string]$Action = 'Start',

    # Defaults to svc/.env.production in this repository.
    [string]$EnvFile,

    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 30,

    [switch]$Build
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Windows PowerShell 5.1 leaves $PSScriptRoot empty while it evaluates param()
# defaults for a script started with -File, as Task Scheduler does, so
# defaults that need it are filled in here.
if (-not $EnvFile) {
    $EnvFile = Join-Path $PSScriptRoot '../svc/.env.production'
}

. (Join-Path $PSScriptRoot 'ControlCenter.Common.ps1')

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$envPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($EnvFile)

try {
    $docker = Resolve-ControlCenterDocker
}
catch {
    # Nothing can be running without the engine, so Stop has nothing to do.
    if ($Action -eq 'Stop' -and (Get-ControlCenterErrorReason -ErrorRecord $_) -eq 'EngineStopped') {
        Write-Host 'Docker is not running, so the app is not running either.'
        exit 0
    }
    [Console]::Error.WriteLine($_.Exception.Message)
    exit (Get-ControlCenterExitCode -ErrorRecord $_)
}

$project = New-ControlCenterProject -DockerPath $docker `
    -RepositoryRoot $repositoryRoot -EnvFile $envPath

try {
    switch ($Action) {
        'Start' {
            Start-ControlCenter -Project $project -TimeoutSeconds $TimeoutSeconds -Build:$Build
        }
        'Stop' {
            Stop-ControlCenter -Project $project
        }
        'Status' {
            Get-ControlCenterStatus -Project $project
        }
    }
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit (Get-ControlCenterExitCode -ErrorRecord $_)
}
exit 0
