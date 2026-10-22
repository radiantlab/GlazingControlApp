Set-StrictMode -Version 2.0

# Shared logic for Invoke-ControlCenter.ps1, kept separate so Pester can test
# it without a container engine. Every external command goes through
# Invoke-ControlCenterNative, and every host check through a small function,
# so tests can mock them.
#
# Failures throw an exception carrying the script's exit code in
# Data['ExitCode'] (see the table in issue #68) and, where a caller needs to
# tell causes apart, a short Data['Reason'].

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
    return 1
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

function Test-ControlCenterWindows {
    # $IsWindows does not exist in Windows PowerShell 5.1.
    return [System.Environment]::OSVersion.Platform -eq
        [System.PlatformID]::Win32NT
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
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = @($output | ForEach-Object { [string]$_ })
    }
}

function Get-ControlCenterProperty {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name) {
        return $Object.$Name
    }
    return $null
}

function Get-ControlCenterPodmanMachine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PodmanPath
    )

    $result = Invoke-ControlCenterNative -FilePath $PodmanPath `
        -Arguments @('machine', 'list', '--format', 'json')
    if ($result.ExitCode -ne 0) {
        throw (New-ControlCenterError -ExitCode 1 -Message (
            "Could not list Podman machines:`n" + ($result.Output -join "`n")
        ))
    }

    # Windows PowerShell 5.1 returns a JSON array as one object; piping it
    # through ForEach-Object enumerates it the same way in 5.1 and 7.
    $parsed = ConvertFrom-Json -InputObject ($result.Output -join "`n")
    $machines = @($parsed | ForEach-Object { $_ })

    if ($machines.Count -eq 0) {
        throw (New-ControlCenterError -ExitCode 1 -Reason 'NoMachine' -Message (
            'Podman is installed but has no machine. Set it up once with ' +
            "'podman machine init' (see DEV-SETUP.md), then run this again."
        ))
    }

    $defaults = @($machines | Where-Object {
        (Get-ControlCenterProperty $_ 'Default') -eq $true
    })
    if ($defaults.Count -eq 1) {
        $machine = $defaults[0]
    }
    elseif ($machines.Count -eq 1) {
        $machine = $machines[0]
    }
    else {
        throw (New-ControlCenterError -ExitCode 1 -Message (
            'Several Podman machines exist and none is the default. Pick one ' +
            "with 'podman system connection default <name>'."
        ))
    }

    return [pscustomobject]@{
        Name = [string](Get-ControlCenterProperty $machine 'Name')
        Running = (Get-ControlCenterProperty $machine 'Running') -eq $true
    }
}

function Assert-ControlCenterCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EngineName,

        [Parameter(Mandatory = $true)]
        [string]$EnginePath
    )

    $result = Invoke-ControlCenterNative -FilePath $EnginePath `
        -Arguments @('compose', 'version')
    if ($result.ExitCode -ne 0) {
        throw (New-ControlCenterError -ExitCode 1 -Message (
            "'$EngineName compose' does not work:`n" + ($result.Output -join "`n")
        ))
    }
}

function Resolve-ControlCenterPodman {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PodmanPath,

        [switch]$StartMachine
    )

    # On Windows, Podman runs containers in a VM that is stopped after every
    # reboot. Start may start it (never create it); Status and Stop only look.
    # On Linux, Podman runs natively and there is no machine.
    $machineStarted = $false
    if (Test-ControlCenterWindows) {
        $machine = Get-ControlCenterPodmanMachine -PodmanPath $PodmanPath
        if (-not $machine.Running) {
            if (-not $StartMachine) {
                throw (New-ControlCenterError -ExitCode 1 -Reason 'MachineStopped' -Message (
                    "Podman is installed but its machine '$($machine.Name)' is " +
                    'stopped. Run this script with -Action Start, or run ' +
                    "'podman machine start $($machine.Name)'."
                ))
            }
            # podman machine start blocks until the machine is up, so this
            # wait is separate from the -TimeoutSeconds health polling.
            Write-Host "Starting Podman machine '$($machine.Name)'..."
            $result = Invoke-ControlCenterNative -FilePath $PodmanPath `
                -Arguments @('machine', 'start', $machine.Name)
            if ($result.ExitCode -ne 0) {
                throw (New-ControlCenterError -ExitCode 1 -Message (
                    "Podman machine '$($machine.Name)' failed to start:`n" +
                    ($result.Output -join "`n")
                ))
            }
            $machineStarted = $true
        }
    }

    $info = Invoke-ControlCenterNative -FilePath $PodmanPath -Arguments @('info')
    if ($info.ExitCode -ne 0) {
        throw (New-ControlCenterError -ExitCode 1 -Message (
            "Podman is installed but not responding:`n" + ($info.Output -join "`n")
        ))
    }
    Assert-ControlCenterCompose -EngineName 'podman' -EnginePath $PodmanPath

    return [pscustomobject]@{
        Name = 'podman'
        Path = $PodmanPath
        MachineStarted = $machineStarted
    }
}

function Resolve-ControlCenterDocker {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DockerPath
    )

    # Docker is a development fallback; the trailer runs Podman. Starting
    # Docker Desktop from a script is unreliable, so only report it.
    $info = Invoke-ControlCenterNative -FilePath $DockerPath -Arguments @('info')
    if ($info.ExitCode -ne 0) {
        throw (New-ControlCenterError -ExitCode 1 -Reason 'EngineStopped' -Message (
            'Docker is installed but not running. Start Docker Desktop (or the ' +
            'Docker service) and run this again.'
        ))
    }
    Assert-ControlCenterCompose -EngineName 'docker' -EnginePath $DockerPath

    return [pscustomobject]@{
        Name = 'docker'
        Path = $DockerPath
        MachineStarted = $false
    }
}

function Resolve-ControlCenterEngine {
    param(
        [switch]$StartMachine
    )

    $podmanPath = Find-ControlCenterCommand -Name 'podman'
    if ($podmanPath) {
        return Resolve-ControlCenterPodman -PodmanPath $podmanPath `
            -StartMachine:$StartMachine
    }

    $dockerPath = Find-ControlCenterCommand -Name 'docker'
    if ($dockerPath) {
        return Resolve-ControlCenterDocker -DockerPath $dockerPath
    }

    throw (New-ControlCenterError -ExitCode 1 -Reason 'NotInstalled' -Message (
        'Neither Podman nor Docker is installed. Install Podman ' +
        '(see DEV-SETUP.md) and run this again.'
    ))
}
