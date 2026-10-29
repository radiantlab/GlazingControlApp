# Shared logic for Invoke-ControlCenter.ps1, kept separate so Pester can test
# it without a container engine. Every external command goes through
# Invoke-ControlCenterNative, and every host check through a small function,
# so tests can mock them.
#
# No Set-StrictMode here: this file is dot-sourced into the caller's scope, so
# a mode set here would replace the caller's `Set-StrictMode -Version Latest`.
#
# Failures throw an exception carrying the script's exit code in
# Data['ExitCode'] (see the table in issue #68) and, where a caller needs to
# tell causes apart, a short Data['Reason'].
#
# `docker compose config` prints every resolved value, including the Halio
# address and site ID. Its output is parsed in memory and never printed.

$script:ControlCenterAppService = 'app'
$script:ControlCenterDataTarget = '/app/svc/data'

# Exit code for an exception the script did not raise itself, so a bug is
# never reported as one of the documented causes.
$script:ControlCenterUnexpectedExitCode = 5

# The variable behind each bind mount, so errors name what to fix in the env
# file rather than a container path.
$script:ControlCenterMountVariables = @{
    '/app/svc/data' = 'SVC_PRODUCTION_DATA_DIR'
    '/app/svc/config' = 'SVC_PRODUCTION_CONFIG_DIR'
    '/app/db-backups' = 'SVC_DB_BACKUP_DIR'
    '/app/svc/sensor-input/specbos-lival.capture' = 'SVC_JETI_CAPTURE_PATH'
}

function New-ControlCenterError {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ExitCode,

        [Parameter(Mandatory = $true)]
        [string]$Message,

        [string]$Reason = ''
    )

    $exception = New-Object System.Exception $Message
    $exception.Data['ExitCode'] = $ExitCode
    $exception.Data['Reason'] = $Reason
    return $exception
}

function Get-ControlCenterExitCode {
    param(
        [Parameter(Mandatory = $true)]
        [System.Management.Automation.ErrorRecord]$ErrorRecord
    )

    $data = $ErrorRecord.Exception.Data
    if ($data.Contains('ExitCode')) {
        return [int]$data['ExitCode']
    }
    return $script:ControlCenterUnexpectedExitCode
}

function Get-ControlCenterErrorReason {
    param(
        [Parameter(Mandatory = $true)]
        [System.Management.Automation.ErrorRecord]$ErrorRecord
    )

    $data = $ErrorRecord.Exception.Data
    if ($data.Contains('Reason')) {
        return [string]$data['Reason']
    }
    return ''
}

function Find-ControlCenterCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $command) {
        return $null
    }
    return $command.Source
}

function Invoke-ControlCenterNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$Arguments = @()
    )

    # With 'Stop', Windows PowerShell 5.1 turns a native command's stderr into
    # a terminating error; the exit code is what decides success here.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& $FilePath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    # Stderr lines arrive as ErrorRecords. Keep them apart so a warning never
    # ends up in output that is parsed as JSON.
    $stdout = @($lines | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] } |
        ForEach-Object { [string]$_ })
    $stderr = @($lines | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } |
        ForEach-Object { [string]$_ })

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $stdout
        Errors = $stderr
    }
}

function Get-ControlCenterNativeText {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Result
    )

    return (@($Result.Errors) + @($Result.Output)) -join "`n"
}

function Get-ControlCenterProperty {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function ConvertFrom-ControlCenterJson {
    param(
        [string[]]$Lines
    )

    # Windows PowerShell 5.1 returns a JSON array as one object; piping it
    # through ForEach-Object enumerates it the same way in 5.1 and 7.
    $parsed = ConvertFrom-Json -InputObject ($Lines -join "`n")
    return @($parsed | ForEach-Object { $_ })
}

function Resolve-ControlCenterDocker {
    # Docker is the only supported runtime (docs/adr/0007). Starting Docker
    # Desktop or the engine is left to the #75 launcher, so a stopped engine
    # is only reported.
    $dockerPath = Find-ControlCenterCommand -Name 'docker'
    if (-not $dockerPath) {
        throw (New-ControlCenterError -ExitCode 1 -Reason 'NotInstalled' -Message (
            'Docker is not installed. Install it (see DEV-SETUP.md) and run ' +
            'this again.'
        ))
    }

    $info = Invoke-ControlCenterNative -FilePath $dockerPath `
        -Arguments @('info', '--format', '{{.ServerVersion}}')
    if ($info.ExitCode -ne 0) {
        throw (New-ControlCenterError -ExitCode 1 -Reason 'EngineStopped' -Message (
            'Docker is installed but not running. Start Docker Desktop (or ' +
            'the Docker service) and run this again.'
        ))
    }

    $compose = Invoke-ControlCenterNative -FilePath $dockerPath `
        -Arguments @('compose', 'version')
    if ($compose.ExitCode -ne 0) {
        throw (New-ControlCenterError -ExitCode 1 -Reason 'NoCompose' -Message (
            "'docker compose' does not work:`n" + (Get-ControlCenterNativeText -Result $compose)
        ))
    }

    return $dockerPath
}

function New-ControlCenterProject {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DockerPath,

        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string]$EnvFile
    )

    # The project directory is the repository root, so the project name matches
    # a plain `docker compose` run from there and the two can manage the same
    # stack.
    return [pscustomobject]@{
        DockerPath = $DockerPath
        RepositoryRoot = $RepositoryRoot
        ComposeFile = Join-Path $RepositoryRoot 'docker-compose.yml'
        EnvFile = $EnvFile
    }
}

function Invoke-ControlCenterCompose {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $prefix = @(
        'compose',
        '--project-directory', $Project.RepositoryRoot,
        '-f', $Project.ComposeFile,
        '--env-file', $Project.EnvFile
    )
    return Invoke-ControlCenterNative -FilePath $Project.DockerPath `
        -Arguments ($prefix + $Arguments)
}

function Get-ControlCenterApp {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project
    )

    if (-not (Test-Path -LiteralPath $Project.EnvFile -PathType Leaf)) {
        throw (New-ControlCenterError -ExitCode 2 -Reason 'NoEnvFile' -Message (
            "Env file not found: $($Project.EnvFile). Create it from " +
            'svc/.env.production.example (see DEV-SETUP.md).'
        ))
    }

    # --no-path-resolution keeps relative mount sources relative, so they can
    # be rejected instead of silently resolved against the repository.
    $result = Invoke-ControlCenterCompose -Project $Project `
        -Arguments @('config', '--format', 'json', '--no-path-resolution')
    if ($result.ExitCode -ne 0) {
        throw (New-ControlCenterError -ExitCode 2 -Reason 'ComposeConfig' -Message (
            "Compose could not read $($Project.EnvFile):`n" +
            (Get-ControlCenterNativeText -Result $result)
        ))
    }

    $config = @(ConvertFrom-ControlCenterJson -Lines $result.Output)[0]
    $services = Get-ControlCenterProperty $config 'services'
    $app = Get-ControlCenterProperty $services $script:ControlCenterAppService
    if ($null -eq $app) {
        throw (New-ControlCenterError -ExitCode 2 -Message (
            "docker-compose.yml has no '$script:ControlCenterAppService' service."
        ))
    }

    $port = 8000
    $ports = @(Get-ControlCenterProperty $app 'ports')
    if ($ports.Count -gt 0 -and $null -ne $ports[0]) {
        $published = Get-ControlCenterProperty $ports[0] 'published'
        if ($published) {
            $port = [int]$published
        }
    }

    $mounts = @(Get-ControlCenterProperty $app 'volumes' | Where-Object {
        $null -ne $_ -and (Get-ControlCenterProperty $_ 'type') -eq 'bind'
    } | ForEach-Object {
        [pscustomobject]@{
            Source = [string](Get-ControlCenterProperty $_ 'source')
            Target = [string](Get-ControlCenterProperty $_ 'target')
        }
    })

    return [pscustomobject]@{
        ContainerName = [string](Get-ControlCenterProperty $app 'container_name')
        Image = [string](Get-ControlCenterProperty $app 'image')
        Port = $port
        Mounts = $mounts
    }
}

function Test-ControlCenterAbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [bool]$Windows = ([System.IO.Path]::DirectorySeparatorChar -eq '\')
    )

    # IsPathRooted accepts '\data' on Windows, which depends on the current
    # drive; require a drive letter or a UNC share there.
    if ($Windows) {
        return $Path -match '^[A-Za-z]:[\\/]' -or $Path -match '^\\\\[^\\]+\\'
    }
    return $Path.StartsWith('/')
}

function Assert-ControlCenterMounts {
    param(
        [Parameter(Mandatory = $true)]
        [object]$App
    )

    # Every production mount sets create_host_path: false, so a missing source
    # would only fail inside `compose up`.
    foreach ($mount in $App.Mounts) {
        $name = $script:ControlCenterMountVariables[$mount.Target]
        if (-not $name) {
            $name = "the mount for $($mount.Target)"
        }

        if (-not $mount.Source -or -not (Test-ControlCenterAbsolutePath -Path $mount.Source)) {
            throw (New-ControlCenterError -ExitCode 2 -Reason 'RelativePath' -Message (
                "$name must be an absolute path, not '$($mount.Source)'."
            ))
        }
        if (-not (Test-Path -LiteralPath $mount.Source)) {
            throw (New-ControlCenterError -ExitCode 2 -Reason 'MissingPath' -Message (
                "$name does not exist: $($mount.Source)"
            ))
        }

        if ($mount.Target -eq $script:ControlCenterDataTarget) {
            $database = Join-Path $mount.Source 'audit.db'
            if (-not (Test-Path -LiteralPath $database -PathType Leaf)) {
                throw (New-ControlCenterError -ExitCode 2 -Reason 'NoDatabase' -Message (
                    "audit.db not found in $name ($($mount.Source)). Production " +
                    'refuses to start without it; see the restore steps in ' +
                    'svc/README.md.'
                ))
            }
        }
    }
}

function Get-ControlCenterContainer {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $result = Invoke-ControlCenterNative -FilePath $Project.DockerPath `
        -Arguments @('container', 'inspect', $Name)
    if ($result.ExitCode -ne 0) {
        return $null
    }

    $container = @(ConvertFrom-ControlCenterJson -Lines $result.Output)[0]
    $state = Get-ControlCenterProperty $container 'State'
    return [pscustomobject]@{
        Status = [string](Get-ControlCenterProperty $state 'Status')
        RestartCount = [int](Get-ControlCenterProperty $container 'RestartCount')
    }
}

function Test-ControlCenterImage {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project,

        [Parameter(Mandatory = $true)]
        [string]$Image
    )

    $result = Invoke-ControlCenterNative -FilePath $Project.DockerPath `
        -Arguments @('image', 'inspect', $Image)
    return $result.ExitCode -eq 0
}

function Test-ControlCenterPortOpen {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    # Compose publishes on every address, so the port is taken if anything
    # answers on a loopback address or the wildcard address cannot be bound.
    foreach ($address in @([System.Net.IPAddress]::Loopback, [System.Net.IPAddress]::IPv6Loopback)) {
        $client = New-Object System.Net.Sockets.TcpClient $address.AddressFamily
        try {
            $connect = $client.BeginConnect($address, $Port, $null, $null)
            if ($connect.AsyncWaitHandle.WaitOne(1000)) {
                $client.EndConnect($connect)
                return $true
            }
        }
        catch {
            # Refused or unsupported: nothing listening on this address.
        }
        finally {
            $client.Close()
        }
    }

    $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Any, $Port)
    try {
        $listener.Start()
        return $false
    }
    catch {
        return $true
    }
    finally {
        $listener.Stop()
    }
}

function Get-ControlCenterHealthResponse {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    # Any failure, including a non-200 status, means "not healthy yet".
    try {
        return Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" `
            -TimeoutSec 5 -UseBasicParsing
    }
    catch {
        return $null
    }
}

function Write-ControlCenterLogs {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    # docker logs replays the container's stderr on its own stderr, so both
    # streams are the log.
    $logs = Invoke-ControlCenterNative -FilePath $Project.DockerPath `
        -Arguments @('logs', '--tail', '50', $Name)
    [Console]::Error.WriteLine("Last 50 log lines from ${Name}:")
    [Console]::Error.WriteLine((Get-ControlCenterNativeText -Result $logs))
}

function Wait-ControlCenterHealth {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project,

        [Parameter(Mandatory = $true)]
        [object]$App,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,

        [int]$RestartCount = 0,

        [int]$PollSeconds = 2
    )

    # Always try at least once, so a timeout of 0 is a single check.
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        $health = Get-ControlCenterHealthResponse -Port $App.Port
        if ($null -ne $health) {
            return $health
        }

        # restart: unless-stopped turns a crash into a loop, so a new restart
        # counts as the container exiting.
        $container = Get-ControlCenterContainer -Project $Project -Name $App.ContainerName
        if ($null -eq $container -or $container.Status -ne 'running' -or
            $container.RestartCount -gt $RestartCount) {
            Write-ControlCenterLogs -Project $Project -Name $App.ContainerName
            throw (New-ControlCenterError -ExitCode 3 -Reason 'ContainerExited' -Message (
                "$($App.ContainerName) stopped or restarted before /health answered."
            ))
        }

        if ($stopwatch.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
            throw (New-ControlCenterError -ExitCode 4 -Reason 'HealthTimeout' -Message (
                "/health did not answer within $TimeoutSeconds seconds. Check " +
                "'docker logs $($App.ContainerName)'."
            ))
        }
        Start-Sleep -Seconds $PollSeconds
    }
}

function Write-ControlCenterHealth {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Health,

        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $status = [string](Get-ControlCenterProperty $Health 'status')
    $environment = [string](Get-ControlCenterProperty $Health 'environment')
    $controlSource = [string](Get-ControlCenterProperty $Health 'control_source')
    $sensorStatus = [string](Get-ControlCenterProperty $Health 'sensor_status')
    $sensorErrors = @(Get-ControlCenterProperty $Health 'sensor_errors' |
        Where-Object { $null -ne $_ })

    Write-Host "status:         $status"
    Write-Host "environment:    $environment"
    Write-Host "control_source: $controlSource"
    Write-Host "sensor_status:  $sensorStatus"
    foreach ($sensorError in $sensorErrors) {
        Write-Host "sensor_error:   $sensorError"
    }

    if ($environment -ne 'production' -or $controlSource -ne 'physical') {
        throw (New-ControlCenterError -ExitCode 2 -Reason 'WrongEnvironment' -Message (
            "Expected environment 'production' and control_source 'physical', " +
            "got '$environment' and '$controlSource'. Check SVC_ENVIRONMENT and " +
            "that port $Port belongs to this stack."
        ))
    }

    # Missing instruments are reported, not fatal.
    if ($status -eq 'degraded') {
        Write-Warning 'Running with degraded sensors; see sensor_error lines above.'
    }
}

function Start-ControlCenter {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,

        [switch]$Build
    )

    $app = Get-ControlCenterApp -Project $Project
    Assert-ControlCenterMounts -App $app

    $restartCount = 0
    $container = Get-ControlCenterContainer -Project $Project -Name $app.ContainerName
    if ($null -ne $container -and $container.Status -eq 'paused') {
        # A paused container still holds the port, so it is ours, not a
        # conflict, but compose up does not resume it.
        throw (New-ControlCenterError -ExitCode 3 -Reason 'Paused' -Message (
            "$($app.ContainerName) is paused. Run 'docker unpause " +
            "$($app.ContainerName)', or Stop and then Start."
        ))
    }
    if ($null -ne $container -and $container.Status -eq 'running') {
        Write-Host "$($app.ContainerName) is already running."
        $restartCount = $container.RestartCount
    }
    else {
        if (Test-ControlCenterPortOpen -Port $app.Port) {
            throw (New-ControlCenterError -ExitCode 2 -Reason 'PortInUse' -Message (
                "Port $($app.Port) is in use by another process, so " +
                "$($app.ContainerName) cannot start. Stop that process first."
            ))
        }

        $arguments = @('up', '-d')
        if ($Build -or -not (Test-ControlCenterImage -Project $Project -Image $app.Image)) {
            $arguments += '--build'
        }
        Write-Host "Starting $($app.ContainerName)..."
        $result = Invoke-ControlCenterCompose -Project $Project -Arguments $arguments
        if ($result.ExitCode -ne 0) {
            throw (New-ControlCenterError -ExitCode 3 -Reason 'ComposeUp' -Message (
                "docker compose up failed:`n" + (Get-ControlCenterNativeText -Result $result)
            ))
        }

        $started = Get-ControlCenterContainer -Project $Project -Name $app.ContainerName
        if ($null -ne $started) {
            $restartCount = $started.RestartCount
        }
    }

    $health = Wait-ControlCenterHealth -Project $Project -App $app `
        -TimeoutSeconds $TimeoutSeconds -RestartCount $restartCount
    Write-ControlCenterHealth -Health $health -Port $app.Port
}

function Stop-ControlCenter {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project
    )

    # Only config is read: Stop must work even when audit.db or a mount source
    # has gone missing.
    [void](Get-ControlCenterApp -Project $Project)
    $result = Invoke-ControlCenterCompose -Project $Project -Arguments @('down')
    if ($result.ExitCode -ne 0) {
        throw (New-ControlCenterError -ExitCode 3 -Reason 'ComposeDown' -Message (
            "docker compose down failed:`n" + (Get-ControlCenterNativeText -Result $result)
        ))
    }
    Write-Host 'Stopped. Data on the host is untouched.'
}

function Get-ControlCenterStatus {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Project
    )

    $app = Get-ControlCenterApp -Project $Project
    $container = Get-ControlCenterContainer -Project $Project -Name $app.ContainerName
    if ($null -eq $container -or $container.Status -ne 'running') {
        $state = 'not created'
        if ($null -ne $container) {
            $state = $container.Status
        }
        $message = "$($app.ContainerName) is not running ($state)."
        if ($state -ne 'paused' -and (Test-ControlCenterPortOpen -Port $app.Port)) {
            $message += " Another process holds port $($app.Port), so Start would fail."
        }
        throw (New-ControlCenterError -ExitCode 3 -Reason 'NotRunning' -Message $message)
    }

    Write-Host "$($app.ContainerName) is running."
    $health = Wait-ControlCenterHealth -Project $Project -App $app `
        -TimeoutSeconds 0 -RestartCount $container.RestartCount
    Write-ControlCenterHealth -Health $health -Port $app.Port
}
