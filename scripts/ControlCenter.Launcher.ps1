# Logic for the double-click launcher, Open-ControlCenter.ps1 (#108), kept
# separate so Pester can test it. It needs ControlCenter.Common.ps1 dot-sourced
# first. The Compose work is the same Start as Invoke-ControlCenter.ps1; this
# file adds only what the console window does around it: open the HMI on
# success, or keep the window open with a next step on failure.
#
# No Set-StrictMode here, for the same reason as ControlCenter.Common.ps1.

# The same default as Invoke-ControlCenter.ps1 -TimeoutSeconds.
$script:ControlCenterLauncherTimeoutSeconds = 30

# Seconds the window stays open after a successful start, so a degraded-sensor
# warning can be read before it closes.
$script:ControlCenterCloseDelaySeconds = 10

$script:ControlCenterNextSteps = @{
    $script:ControlCenterExitCodes.Engine = (
        "If Docker Desktop is installed, open it from the Start menu, wait " +
        "for 'Engine running', then double-click again."
    )
    $script:ControlCenterExitCodes.Configuration = (
        'A setting or file is wrong (see above). Fix it, or ask the system ' +
        'maintainer.'
    )
    $script:ControlCenterExitCodes.Compose = (
        'The app did not start. The messages above show why.'
    )
    $script:ControlCenterExitCodes.HealthTimeout = (
        'The app did not answer in time. Double-click again, and if this ' +
        'repeats, ask the system maintainer.'
    )
    $script:ControlCenterExitCodes.Unexpected = (
        'Unexpected error in the start script. Ask the system maintainer.'
    )
}

function Get-ControlCenterNextStep {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    if ($script:ControlCenterNextSteps.ContainsKey($ExitCode)) {
        return $script:ControlCenterNextSteps[$ExitCode]
    }
    return ("The start script failed with exit code $ExitCode. Ask the " +
        'system maintainer.')
}

function Open-ControlCenterBrowser {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    Start-Process $Url
}

function Wait-ControlCenterEnter {
    [void](Read-Host 'Press Enter to close this window')
}

function Wait-ControlCenterClose {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Seconds
    )

    Write-Host "This window closes in $Seconds seconds."
    Start-Sleep -Seconds $Seconds
}

function Write-ControlCenterFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [Parameter(Mandatory = $true)]
        [string]$NextStep
    )

    [Console]::Error.WriteLine($Message)
    Write-Host ''
    Write-Host $NextStep
    Wait-ControlCenterEnter
}

function Invoke-ControlCenterLauncher {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string]$EnvFile
    )

    try {
        $docker = Resolve-ControlCenterDocker
        $project = New-ControlCenterProject -DockerPath $docker `
            -RepositoryRoot $RepositoryRoot -EnvFile $EnvFile
        $app = Get-ControlCenterApp -Project $project
        Start-ControlCenterApp -Project $project -App $app `
            -TimeoutSeconds $script:ControlCenterLauncherTimeoutSeconds
    }
    catch {
        $exitCode = Get-ControlCenterExitCode -ErrorRecord $_
        Write-ControlCenterFailure -Message $_.Exception.Message `
            -NextStep (Get-ControlCenterNextStep -ExitCode $exitCode)
        return $exitCode
    }

    $url = "http://localhost:$($app.Port)/"
    try {
        Write-Host "Opening the HMI at $url"
        Open-ControlCenterBrowser -Url $url
    }
    catch {
        # Start succeeded, so the next step must not blame it.
        Write-ControlCenterFailure `
            -Message "The browser could not be opened: $($_.Exception.Message)" `
            -NextStep "The app is running. Open $url in a web browser."
        return $script:ControlCenterExitCodes.Unexpected
    }

    Wait-ControlCenterClose -Seconds $script:ControlCenterCloseDelaySeconds
    return 0
}
