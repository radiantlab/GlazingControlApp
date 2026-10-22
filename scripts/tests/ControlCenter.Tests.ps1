$scriptsRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$commonScript = Join-Path $scriptsRoot "ControlCenter.Common.ps1"
$invokeScript = Join-Path $scriptsRoot "Invoke-ControlCenter.ps1"

function Get-ThrownError {
    param([scriptblock]$Block)

    try {
        [void](& $Block)
    }
    catch {
        return $_
    }
    return $null
}

function New-NativeResult {
    param(
        [int]$ExitCode = 0,
        [string[]]$Output = @()
    )

    return [pscustomobject]@{ ExitCode = $ExitCode; Output = $Output }
}

Describe "Control Center script syntax" {
    foreach ($scriptPath in @($commonScript, $invokeScript)) {
        It "parses $([System.IO.Path]::GetFileName($scriptPath))" {
            $tokens = $null
            $errors = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile(
                $scriptPath,
                [ref]$tokens,
                [ref]$errors
            )
            $errors.Count | Should Be 0
        }
    }
}

Describe "Resolve-ControlCenterEngine" {
    . $commonScript

    $stoppedMachine = '[{"Name":"podman-machine-default","Default":true,"Running":false}]'
    $runningMachine = '[{"Name":"podman-machine-default","Default":true,"Running":true}]'

    It "reports neither engine installed" {
        Mock Find-ControlCenterCommand { $null }

        $thrown = Get-ThrownError { Resolve-ControlCenterEngine -StartMachine }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 1
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "NotInstalled"
    }

    It "starts a stopped Podman machine on Windows when asked" {
        Mock Find-ControlCenterCommand { "podman" } -ParameterFilter { $Name -eq "podman" }
        Mock Test-ControlCenterWindows { $true }
        Mock Invoke-ControlCenterNative { New-NativeResult }
        Mock Invoke-ControlCenterNative { New-NativeResult -Output @($stoppedMachine) } `
            -ParameterFilter { $Arguments[0] -eq "machine" -and $Arguments[1] -eq "list" }
        Mock Write-Host { }

        $engine = Resolve-ControlCenterEngine -StartMachine

        $engine.Name | Should Be "podman"
        $engine.MachineStarted | Should Be $true
        Assert-MockCalled Invoke-ControlCenterNative -Scope It -Times 1 -Exactly `
            -ParameterFilter {
                $Arguments[0] -eq "machine" -and $Arguments[1] -eq "start" -and
                $Arguments[2] -eq "podman-machine-default"
            }
    }

    It "does not start a stopped machine for Status or Stop" {
        Mock Find-ControlCenterCommand { "podman" } -ParameterFilter { $Name -eq "podman" }
        Mock Test-ControlCenterWindows { $true }
        Mock Invoke-ControlCenterNative { New-NativeResult }
        Mock Invoke-ControlCenterNative { New-NativeResult -Output @($stoppedMachine) } `
            -ParameterFilter { $Arguments[0] -eq "machine" -and $Arguments[1] -eq "list" }

        $thrown = Get-ThrownError { Resolve-ControlCenterEngine }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 1
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "MachineStopped"
        Assert-MockCalled Invoke-ControlCenterNative -Scope It -Times 0 -Exactly `
            -ParameterFilter { $Arguments[0] -eq "machine" -and $Arguments[1] -eq "start" }
    }

    It "leaves a running machine alone" {
        Mock Find-ControlCenterCommand { "podman" } -ParameterFilter { $Name -eq "podman" }
        Mock Test-ControlCenterWindows { $true }
        Mock Invoke-ControlCenterNative { New-NativeResult }
        Mock Invoke-ControlCenterNative { New-NativeResult -Output @($runningMachine) } `
            -ParameterFilter { $Arguments[0] -eq "machine" -and $Arguments[1] -eq "list" }

        $engine = Resolve-ControlCenterEngine -StartMachine

        $engine.MachineStarted | Should Be $false
        Assert-MockCalled Invoke-ControlCenterNative -Scope It -Times 0 -Exactly `
            -ParameterFilter { $Arguments[0] -eq "machine" -and $Arguments[1] -eq "start" }
    }

    It "never creates a machine when none exists" {
        Mock Find-ControlCenterCommand { "podman" } -ParameterFilter { $Name -eq "podman" }
        Mock Test-ControlCenterWindows { $true }
        Mock Invoke-ControlCenterNative { New-NativeResult }
        Mock Invoke-ControlCenterNative { New-NativeResult -Output @("[]") } `
            -ParameterFilter { $Arguments[0] -eq "machine" -and $Arguments[1] -eq "list" }

        $thrown = Get-ThrownError { Resolve-ControlCenterEngine -StartMachine }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 1
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "NoMachine"
        Assert-MockCalled Invoke-ControlCenterNative -Scope It -Times 0 -Exactly `
            -ParameterFilter {
                $Arguments[0] -eq "machine" -and
                ($Arguments[1] -eq "init" -or $Arguments[1] -eq "start")
            }
    }

    It "reports Podman's output when the machine fails to start" {
        Mock Find-ControlCenterCommand { "podman" } -ParameterFilter { $Name -eq "podman" }
        Mock Test-ControlCenterWindows { $true }
        Mock Invoke-ControlCenterNative { New-NativeResult }
        Mock Invoke-ControlCenterNative { New-NativeResult -Output @($stoppedMachine) } `
            -ParameterFilter { $Arguments[0] -eq "machine" -and $Arguments[1] -eq "list" }
        Mock Invoke-ControlCenterNative {
            New-NativeResult -ExitCode 125 -Output @("netavark: nftables error")
        } -ParameterFilter { $Arguments[0] -eq "machine" -and $Arguments[1] -eq "start" }
        Mock Write-Host { }

        $thrown = Get-ThrownError { Resolve-ControlCenterEngine -StartMachine }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 1
        $thrown.Exception.Message | Should Match "nftables error"
    }

    It "skips the machine on Linux" {
        Mock Find-ControlCenterCommand { "podman" } -ParameterFilter { $Name -eq "podman" }
        Mock Test-ControlCenterWindows { $false }
        Mock Invoke-ControlCenterNative { New-NativeResult }

        $engine = Resolve-ControlCenterEngine -StartMachine

        $engine.Name | Should Be "podman"
        Assert-MockCalled Invoke-ControlCenterNative -Scope It -Times 0 -Exactly `
            -ParameterFilter { $Arguments[0] -eq "machine" }
    }

    It "falls back to a running Docker when Podman is not installed" {
        Mock Find-ControlCenterCommand { $null }
        Mock Find-ControlCenterCommand { "docker" } -ParameterFilter { $Name -eq "docker" }
        Mock Invoke-ControlCenterNative { New-NativeResult }

        $engine = Resolve-ControlCenterEngine -StartMachine

        $engine.Name | Should Be "docker"
    }

    It "reports Docker installed but not running without starting it" {
        Mock Find-ControlCenterCommand { $null }
        Mock Find-ControlCenterCommand { "docker" } -ParameterFilter { $Name -eq "docker" }
        Mock Invoke-ControlCenterNative { New-NativeResult }
        Mock Invoke-ControlCenterNative { New-NativeResult -ExitCode 1 } `
            -ParameterFilter { $Arguments[0] -eq "info" }

        $thrown = Get-ThrownError { Resolve-ControlCenterEngine -StartMachine }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 1
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "EngineStopped"
    }

    It "fails when compose does not work" {
        Mock Find-ControlCenterCommand { "podman" } -ParameterFilter { $Name -eq "podman" }
        Mock Test-ControlCenterWindows { $false }
        Mock Invoke-ControlCenterNative { New-NativeResult }
        Mock Invoke-ControlCenterNative {
            New-NativeResult -ExitCode 1 -Output @("unknown command: compose")
        } -ParameterFilter { $Arguments[0] -eq "compose" }

        $thrown = Get-ThrownError { Resolve-ControlCenterEngine -StartMachine }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 1
        $thrown.Exception.Message | Should Match "podman compose"
    }
}
