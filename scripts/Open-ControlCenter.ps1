#requires -Version 5.1

<#
.SYNOPSIS
Starts the production Control Center and opens the HMI, for the double-click
launcher.

.DESCRIPTION
Run by Start-ControlCenter.cmd, which a desktop shortcut points to (see
DEV-SETUP.md). Runs Invoke-ControlCenter.ps1 -Action Start. On success it opens
the HMI in the default browser and closes after a few seconds. On failure it
keeps the window open with the script's message and a next step, until Enter
is pressed.

Exits with the code from Invoke-ControlCenter.ps1, or 5 when the HMI could not
be opened or this script failed.
#>

[CmdletBinding()]
param(
    # Defaults to svc/.env.production in this repository.
    [string]$EnvFile
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Windows PowerShell 5.1 leaves $PSScriptRoot empty while it evaluates param()
# defaults for a script started with -File, as the .cmd launcher does, so
# defaults that need it are filled in here.
if (-not $EnvFile) {
    $EnvFile = Join-Path $PSScriptRoot '../svc/.env.production'
}

. (Join-Path $PSScriptRoot 'ControlCenter.Common.ps1')

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$envPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($EnvFile)

exit (Invoke-ControlCenterLauncher `
        -LifecycleScript (Join-Path $PSScriptRoot 'Invoke-ControlCenter.ps1') `
        -RepositoryRoot $repositoryRoot -EnvFile $envPath)
