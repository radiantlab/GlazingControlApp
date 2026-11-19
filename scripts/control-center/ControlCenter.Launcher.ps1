# Logic for the double-click launcher, Open-ControlCenter.ps1 (#108), kept
# separate so Pester can test it. It needs ControlCenter.Common.ps1 dot-sourced
# first. The Compose work is the same Start as Invoke-ControlCenter-CLI.ps1; this
# file adds what the launcher does around it, so an operator never needs a
# terminal or Docker Desktop's own screens:
# - start Docker Desktop when the engine is stopped;
# - rebuild the image on every double-click, fall back to the existing image
#   when the build fails, and restart a running app when the build changed it;
# - warn when this computer's code is not the latest main;
# - remove this app's old images and cap Docker's build cache;
# - open the HMI on success, or keep the window open with a next step.
#
# No Set-StrictMode here, for the same reason as ControlCenter.Common.ps1.

# The same default as Invoke-ControlCenter-CLI.ps1 -TimeoutSeconds.
$script:ControlCenterLauncherTimeoutSeconds = 30

# Seconds the window stays open after a successful start, so a degraded-sensor
# warning can be read before it closes, and longer when the launcher itself
# has warnings for the operator.
$script:ControlCenterCloseDelaySeconds = 10
$script:ControlCenterWarningCloseDelaySeconds = 30

# The build cache makes rebuilds fast and lets an unchanged build run without
# the internet, so it is capped rather than cleared. Docker drops the oldest
# entries first.
$script:ControlCenterBuildCacheLimit = '5gb'

# The longest a git command may take. Only 'git fetch' uses the network.
$script:ControlCenterGitTimeoutSeconds = 20

$script:ControlCenterAskMaintainer = (
    'Ask a maintainer or developer to update this computer.'
)

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
    # Only reached when there is no earlier image to fall back to, as on a
    # new computer. A build can need the internet, which the Halio network
    # does not have.
    ComposeBuild = (
        'The app could not be built. The messages above show why. ' +
        'Building can need the internet: if this computer is only on the ' +
        'Halio network, connect it to the regular network and double-click ' +
        'again.'
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
        # Open but the engine is stopped, e.g. from the tray; only wait.
        # (During start-up, 'docker info' itself waits, so it never gets here.)
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

function Update-ControlCenterImage {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project,

        [Parameter(Mandatory = $true)]
        [object]$App
    )

    # Builds the image from the code on disk. Returns $null on success, or a
    # warning when the build failed but an earlier image can still start, so
    # a broken update or a missing internet connection never stops the app.
    Write-Host ('Building the app. After an update this can take a few ' +
        'minutes; do not close this window.')
    $result = Invoke-ControlCenterCompose -Project $Project `
        -Arguments @('build', $script:ControlCenterAppService)
    if ($result.ExitCode -eq 0) {
        return $null
    }

    $message = "docker compose build failed:`n" + (Get-ControlCenterNativeText -Result $result)
    if (-not (Test-ControlCenterImage -Project $Project -Image $App.Image)) {
        throw (New-ControlCenterError -Kind Compose -Reason 'ComposeBuild' -Message $message)
    }
    [Console]::Error.WriteLine($message)
    return ('The latest code could not be built (see above), so the version ' +
        'already on this computer was started. Building can need the ' +
        'internet. If this repeats, ask a maintainer or developer.')
}

function ConvertTo-ControlCenterArgument {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value
    )

    # Quotes one argument for ProcessStartInfo.Arguments, which Windows
    # PowerShell 5.1 needs in place of an argument list.
    return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}

function Invoke-ControlCenterGit {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GitPath,

        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [ValidateRange(1, 600)]
        [int]$TimeoutSeconds = 20
    )

    # A child process that is killed after the timeout, because 'git fetch'
    # can wait on a network with no internet. Prompts are turned off so a
    # missing credential or SSH key fails instead of waiting for input.
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $GitPath
    $startInfo.Arguments = (@('-C', $RepositoryRoot) + $Arguments |
        ForEach-Object { ConvertTo-ControlCenterArgument -Value $_ }) -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.EnvironmentVariables['GIT_TERMINAL_PROMPT'] = '0'
    $startInfo.EnvironmentVariables['GCM_INTERACTIVE'] = 'never'
    if (-not $env:GIT_SSH_COMMAND) {
        $startInfo.EnvironmentVariables['GIT_SSH_COMMAND'] = (
            'ssh -o BatchMode=yes -o ConnectTimeout=10'
        )
    }

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            $process.Kill()
        }
        catch {
            # It exited between the wait and the kill.
        }
        return [pscustomobject]@{ ExitCode = -1; Output = @(); TimedOut = $true }
    }
    # Waits for the redirected streams to finish as well.
    $process.WaitForExit()
    [void]$stderr.Result
    $lines = @($stdout.Result -split "`r?`n" | Where-Object { $_ -ne '' })
    return [pscustomobject]@{ ExitCode = $process.ExitCode; Output = $lines; TimedOut = $false }
}

function Get-ControlCenterUpdateCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    # The launcher builds what is on disk and never changes the code itself;
    # updating stays a maintainer's step. This only finds reasons to ask for
    # one. Notices are for the operator; Problem says why the check could not
    # finish, which needs no action.
    $check = [pscustomobject]@{ Notices = @(); Problem = $null }
    $git = Find-ControlCenterCommand -Name 'git'
    if (-not $git) {
        $check.Problem = 'Git is not installed.'
        return $check
    }
    $timeout = $script:ControlCenterGitTimeoutSeconds

    $branch = Invoke-ControlCenterGit -GitPath $git -RepositoryRoot $RepositoryRoot `
        -Arguments @('rev-parse', '--abbrev-ref', 'HEAD') -TimeoutSeconds $timeout
    if ($branch.ExitCode -ne 0 -or $branch.Output.Count -eq 0) {
        $check.Problem = 'this folder is not a Git checkout.'
        return $check
    }
    $name = $branch.Output[0]
    if ($name -ne 'main') {
        $check.Notices += "This computer runs '$name', not the main version."
    }

    $status = Invoke-ControlCenterGit -GitPath $git -RepositoryRoot $RepositoryRoot `
        -Arguments @('status', '--porcelain', '--untracked-files=no') -TimeoutSeconds $timeout
    if ($status.ExitCode -eq 0 -and $status.Output.Count -gt 0) {
        $check.Notices += 'This computer has code changes that are not in Git.'
    }

    $fetch = Invoke-ControlCenterGit -GitPath $git -RepositoryRoot $RepositoryRoot `
        -Arguments @('fetch', '--quiet', 'origin', 'main') -TimeoutSeconds $timeout
    if ($fetch.ExitCode -ne 0) {
        $check.Problem = 'GitHub could not be reached.'
        return $check
    }
    $behind = Invoke-ControlCenterGit -GitPath $git -RepositoryRoot $RepositoryRoot `
        -Arguments @('rev-list', '--count', 'HEAD..origin/main') -TimeoutSeconds $timeout
    $count = 0
    if ($behind.ExitCode -eq 0 -and $behind.Output.Count -gt 0 -and
        [int]::TryParse($behind.Output[0], [ref]$count) -and $count -gt 0) {
        $check.Notices += "A newer version is available ($count new changes on main)."
    }
    return $check
}

function Invoke-ControlCenterCleanup {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project,

        [Parameter(Mandatory = $true)]
        [object]$App
    )

    # Runs after a healthy start, so the image in use is never a candidate.
    # Returns warnings; a failed cleanup never stops the app.
    $warnings = @()

    # Only untagged images that Compose built for this project: earlier builds
    # of this app. Nothing else on the computer is touched. Without a project
    # name there is no safe filter, so nothing is removed.
    if ($App.ProjectName) {
        $images = Invoke-ControlCenterNative -FilePath $Project.DockerPath -Arguments @(
            'image', 'prune', '--force',
            '--filter', "label=com.docker.compose.project=$($App.ProjectName)"
        )
        if ($images.ExitCode -ne 0) {
            $warnings += ('Old app images could not be removed: ' +
                (Get-ControlCenterNativeText -Result $images))
        }
    }

    $cache = Invoke-ControlCenterNative -FilePath $Project.DockerPath -Arguments @(
        'builder', 'prune', '--force',
        '--max-used-space', $script:ControlCenterBuildCacheLimit
    )
    if ($cache.ExitCode -ne 0) {
        $warnings += ("Docker's build cache could not be trimmed: " +
            (Get-ControlCenterNativeText -Result $cache))
    }
    return $warnings
}

function Write-ControlCenterNotices {
    param(
        [object]$UpdateCheck,

        [string[]]$Warnings = @()
    )

    # Returns whether anything needs the operator's attention.
    foreach ($warning in $Warnings) {
        Write-Warning $warning
    }
    $notices = @()
    if ($null -ne $UpdateCheck) {
        $notices = @($UpdateCheck.Notices)
        if ($UpdateCheck.Problem) {
            Write-Host "Could not check for updates: $($UpdateCheck.Problem)"
        }
    }
    foreach ($notice in $notices) {
        Write-Warning $notice
    }
    if ($notices.Count -gt 0) {
        Write-Warning $script:ControlCenterAskMaintainer
    }
    return ($Warnings.Count + $notices.Count) -gt 0
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

    $updateCheck = $null
    $warnings = @()
    try {
        $docker = Resolve-ControlCenterLauncherDocker
        $project = New-ControlCenterProject -DockerPath $docker `
            -RepositoryRoot $RepositoryRoot -EnvFile $EnvFile
        $app = Get-ControlCenterApp -Project $project

        try {
            $updateCheck = Get-ControlCenterUpdateCheck -RepositoryRoot $RepositoryRoot
        }
        catch {
            $updateCheck = [pscustomobject]@{ Notices = @(); Problem = $_.Exception.Message }
        }

        $buildWarning = Update-ControlCenterImage -Project $project -App $app
        if ($buildWarning) {
            $warnings += $buildWarning
        }
        # Recreates a running app only when the build or config changed it.
        Start-ControlCenterApp -Project $project -App $app `
            -TimeoutSeconds $script:ControlCenterLauncherTimeoutSeconds -UpdateRunning
    }
    catch {
        $exitCode = Get-ControlCenterExitCode -ErrorRecord $_
        $reason = Get-ControlCenterErrorReason -ErrorRecord $_
        $message = $_.Exception.Message
        [void](Write-ControlCenterNotices -UpdateCheck $updateCheck -Warnings $warnings)
        Write-ControlCenterFailure -Message $message `
            -NextStep (Get-ControlCenterNextStep -ExitCode $exitCode -Reason $reason)
        return $exitCode
    }

    try {
        $warnings += @(Invoke-ControlCenterCleanup -Project $project -App $app)
    }
    catch {
        $warnings += "Docker cleanup failed: $($_.Exception.Message)"
    }
    $needsAttention = Write-ControlCenterNotices -UpdateCheck $updateCheck -Warnings $warnings

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

    $closeDelay = $script:ControlCenterCloseDelaySeconds
    if ($needsAttention) {
        $closeDelay = $script:ControlCenterWarningCloseDelaySeconds
    }
    Wait-ControlCenterClose -Seconds $closeDelay
    return 0
}
