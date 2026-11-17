# Logic for the double-click launcher, Open-ControlCenter.ps1 (#108), kept
# separate so Pester can test it. It needs ControlCenter.Common.ps1 dot-sourced
# first. The Compose work is the same Start as Invoke-ControlCenter.ps1; this
# file adds what the launcher does around it: start Docker Desktop when the
# engine is stopped, open the HMI on success, or keep the window open with a
# next step on failure.
#
# No Set-StrictMode here, for the same reason as ControlCenter.Common.ps1.

# The same default as Invoke-ControlCenter.ps1 -TimeoutSeconds.
$script:ControlCenterLauncherTimeoutSeconds = 30

# Seconds the window stays open after a successful start, so a degraded-sensor
# warning can be read before it closes.
$script:ControlCenterCloseDelaySeconds = 10

# How long to wait for the Docker engine after starting Docker Desktop, and how
# often to ask. A cold Docker Desktop start usually takes well under a minute.
# Each check also waits for 'docker info', so the total can run a little over.
$script:ControlCenterEngineStartSeconds = 120
$script:ControlCenterEnginePollSeconds = 2

$script:ControlCenterNextSteps = @{
    $script:ControlCenterExitCodes.Engine = (
        "Docker Desktop is not installed or did not start. If it is " +
        "installed, open it from the Start menu, wait for 'Engine running', " +
        'then double-click again.'
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

# Next steps for failures whose exit code covers several causes, where the
# code's own next step would send the operator the wrong way.
$script:ControlCenterReasonNextSteps = @{
    # Docker is there but is not Docker Desktop, for example the engine in
    # WSL 2 (docs/adr/0007).
    NoDockerDesktop = (
        'Start Docker Desktop or the Docker service, then double-click ' +
        'again. If neither is installed, ask the system maintainer.'
    )
    NoCompose = (
        "Docker is running but 'docker compose' does not work. Ask the " +
        'system maintainer to repair or update Docker.'
    )
}

function Get-ControlCenterNextStep {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ExitCode,

        [string]$Reason = ''
    )

    if ($Reason -and $script:ControlCenterReasonNextSteps.ContainsKey($Reason)) {
        return $script:ControlCenterReasonNextSteps[$Reason]
    }
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

function Start-ControlCenterProgram {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )

    Start-Process -FilePath $FilePath -ErrorAction Stop
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

function Test-ControlCenterDockerDesktopRunning {
    return $null -ne (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)
}

function Get-ControlCenterDockerDesktopPath {
    # The default install location. Returns $null when it is not there.
    if (-not $env:ProgramFiles) {
        return $null
    }
    $path = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        return $path
    }
    return $null
}

function Start-ControlCenterDockerDesktop {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DockerPath
    )

    # Newer Docker Desktop versions have 'docker desktop start'. --detach
    # returns at once, because the launcher waits for the engine itself. Older
    # versions fail the command, so fall back to the program file.
    $result = Invoke-ControlCenterNative -FilePath $DockerPath `
        -Arguments @('desktop', 'start', '--detach')
    if ($result.ExitCode -eq 0) {
        return
    }

    $desktopPath = Get-ControlCenterDockerDesktopPath
    if (-not $desktopPath) {
        throw (New-ControlCenterError -Kind Engine -Reason 'NoDockerDesktop' -Message (
            'Docker is installed but not running, and Docker Desktop was not ' +
            'found, so it could not be started.'
        ))
    }
    try {
        Start-ControlCenterProgram -FilePath $desktopPath
    }
    catch {
        throw (New-ControlCenterError -Kind Engine -Reason 'DockerDesktopFailed' -Message (
            "Docker Desktop could not be started: $($_.Exception.Message)"
        ))
    }
}

function Wait-ControlCenterDockerEngine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DockerPath,

        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 3600)]
        [int]$TimeoutSeconds,

        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 60)]
        [int]$PollSeconds
    )

    # Counted in attempts, not wall-clock time, so a test that mocks
    # Start-Sleep runs the same number of checks.
    $attempts = [int][Math]::Ceiling($TimeoutSeconds / $PollSeconds)
    for ($attempt = 1; $attempt -le $attempts; $attempt++) {
        if (Test-ControlCenterDockerEngine -DockerPath $DockerPath) {
            return
        }
        if ($attempt -lt $attempts) {
            Start-Sleep -Seconds $PollSeconds
        }
    }
    throw (New-ControlCenterError -Kind Engine -Reason 'EngineTimeout' -Message (
        "The Docker engine did not start within $TimeoutSeconds seconds."
    ))
}

function Resolve-ControlCenterLauncherDocker {
    # Resolve-ControlCenterDocker, but a stopped engine starts Docker Desktop
    # and waits for it instead of failing. Docker not installed, or a broken
    # 'docker compose', still fails at once.
    try {
        return Resolve-ControlCenterDocker
    }
    catch {
        if ((Get-ControlCenterErrorReason -ErrorRecord $_) -ne 'EngineStopped') {
            throw
        }
    }

    # Found again only on this slow path; Resolve-ControlCenterDocker does not
    # return the path when it fails.
    $dockerPath = Find-ControlCenterCommand -Name 'docker'
    if (Test-ControlCenterDockerDesktopRunning) {
        # Already launched, by an earlier click or at sign-in; only wait.
        Write-Host 'Docker Desktop is starting. Waiting for the Docker engine...'
    }
    else {
        Write-Host 'Starting Docker Desktop...'
        Start-ControlCenterDockerDesktop -DockerPath $dockerPath
        Write-Host 'Waiting for the Docker engine...'
    }
    Wait-ControlCenterDockerEngine -DockerPath $dockerPath `
        -TimeoutSeconds $script:ControlCenterEngineStartSeconds `
        -PollSeconds $script:ControlCenterEnginePollSeconds

    # Check again with the engine up, which also checks 'docker compose'.
    return Resolve-ControlCenterDocker
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
        $docker = Resolve-ControlCenterLauncherDocker
        $project = New-ControlCenterProject -DockerPath $docker `
            -RepositoryRoot $RepositoryRoot -EnvFile $EnvFile
        $app = Get-ControlCenterApp -Project $project
        Start-ControlCenterApp -Project $project -App $app `
            -TimeoutSeconds $script:ControlCenterLauncherTimeoutSeconds
    }
    catch {
        $exitCode = Get-ControlCenterExitCode -ErrorRecord $_
        $reason = Get-ControlCenterErrorReason -ErrorRecord $_
        Write-ControlCenterFailure -Message $_.Exception.Message `
            -NextStep (Get-ControlCenterNextStep -ExitCode $exitCode -Reason $reason)
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
