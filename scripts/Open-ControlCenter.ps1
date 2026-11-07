#requires -Version 5.1

<#
.SYNOPSIS
Starts the production Control Center and opens the HMI, for the double-click
launcher.

.DESCRIPTION
Run by Start-ControlCenter.cmd, which a desktop shortcut points to (see
DEV-SETUP.md). Runs the same Start as Invoke-ControlCenter.ps1 -Action Start,
with its default timeout. On success it opens the HMI in the default browser
and closes after a few seconds. On failure it keeps the window open with the
reason and a next step, until Enter is pressed.

Exits with the same codes as Invoke-ControlCenter.ps1, and 5 also when the app
started but the browser could not be opened.
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
. (Join-Path $PSScriptRoot 'ControlCenter.Launcher.ps1')

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$envPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($EnvFile)

exit (Invoke-ControlCenterLauncher -RepositoryRoot $repositoryRoot -EnvFile $envPath)
