$scriptsRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$commonScript = Join-Path $scriptsRoot "ControlCenter.Common.ps1"
$invokeScript = Join-Path $scriptsRoot "Invoke-ControlCenter.ps1"

# The entry script runs under Latest; ControlCenter.Common.ps1 sets no mode of
# its own, so the tests set the same one.
Set-StrictMode -Version Latest

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
        [string[]]$Output = @(),
        [string[]]$Errors = @()
    )

    return [pscustomobject]@{ ExitCode = $ExitCode; Output = $Output; Errors = $Errors }
}

function Invoke-ControlCenterProcess {
    param(
        [string]$Arguments,
        [string]$PathDirectory
    )

    # Runs the entry script in a child shell with only $PathDirectory on PATH,
    # so `exit` codes can be checked without a real Docker.
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = (Get-Process -Id $PID).Path
    $startInfo.Arguments = "-NoProfile -NonInteractive -File `"$invokeScript`" $Arguments"
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardError = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.EnvironmentVariables["PATH"] = $PathDirectory
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $stderr = $process.StandardError.ReadToEnd()
    $stdout = $process.StandardOutput.ReadToEnd()
    $process.WaitForExit()

    return [pscustomobject]@{ ExitCode = $process.ExitCode; Stdout = $stdout; Stderr = $stderr }
}

function New-FailingDocker {
    param([string]$Directory)

    # A docker whose every command fails, as `docker info` does when the
    # engine is stopped.
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    if ([System.IO.Path]::DirectorySeparatorChar -eq "\") {
        Set-Content -LiteralPath (Join-Path $Directory "docker.cmd") -Value "@exit /b 1"
    }
    else {
        $fake = Join-Path $Directory "docker"
        Set-Content -LiteralPath $fake -Value "#!/bin/sh`nexit 1"
        & chmod +x $fake
    }
}

function New-TestProject {
    param([string]$EnvFile = "env.production")

    return [pscustomobject]@{
        DockerPath = "docker"
        RepositoryRoot = "repo"
        ComposeFile = "repo/docker-compose.yml"
        EnvFile = $EnvFile
    }
}

function New-TestApp {
    param([object[]]$Mounts = @())

    return [pscustomobject]@{
        ContainerName = "glazing-control-app"
        Image = "glazing-control-app"
        Port = 8000
        Mounts = $Mounts
    }
}

function New-TestHealth {
    param(
        [string]$Status = "ok",
        [string]$Environment = "production",
        [string]$ControlSource = "physical",
        [string[]]$SensorErrors = @()
    )

    $sensorStatus = "healthy"
    if ($Status -eq "degraded") {
        $sensorStatus = "degraded"
    }
    return [pscustomobject]@{
        status = $Status
        environment = $Environment
        control_source = $ControlSource
        sensor_status = $sensorStatus
        sensor_errors = $SensorErrors
    }
}

function New-TestMounts {
    param([string]$Root)

    $data = Join-Path $Root "data"
    $config = Join-Path $Root "config"
    $backups = Join-Path $Root "backups"
    $capture = Join-Path $Root "specbos-lival.capture"
    foreach ($directory in @($data, $config, $backups)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    Set-Content -LiteralPath $capture -Value ""
    Set-Content -LiteralPath (Join-Path $data "audit.db") -Value ""

    return @(
        [pscustomobject]@{ Source = $data; Target = "/app/svc/data" },
        [pscustomobject]@{ Source = $config; Target = "/app/svc/config" },
        [pscustomobject]@{ Source = $backups; Target = "/app/db-backups" },
        [pscustomobject]@{
            Source = $capture
            Target = "/app/svc/sensor-input/specbos-lival.capture"
        }
    )
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

    It "uses no `$PSScriptRoot in Invoke-ControlCenter.ps1 parameter defaults" {
        # Windows PowerShell 5.1 leaves it empty there under -File.
        $tokens = $null
        $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile(
            $invokeScript,
            [ref]$tokens,
            [ref]$errors
        )
        $defaults = @($ast.ParamBlock.Parameters | Where-Object { $null -ne $_.DefaultValue } |
            ForEach-Object { $_.DefaultValue.Extent.Text })

        ($defaults -join "`n") | Should Not Match "PSScriptRoot"
    }
}

Describe "Invoke-ControlCenter.ps1 exit codes" {
    It "exits 1 when Docker is not installed" {
        $emptyPath = Join-Path $TestDrive "empty-path"
        New-Item -ItemType Directory -Path $emptyPath -Force | Out-Null

        $run = Invoke-ControlCenterProcess -Arguments "-Action Status" -PathDirectory $emptyPath

        $run.ExitCode | Should Be 1
        $run.Stderr | Should Match "Docker is not installed"
    }

    It "exits 1 for Status when Docker is not running" {
        $stoppedPath = Join-Path $TestDrive "stopped-docker"
        New-FailingDocker -Directory $stoppedPath

        $run = Invoke-ControlCenterProcess -Arguments "-Action Status" -PathDirectory $stoppedPath

        $run.ExitCode | Should Be 1
        $run.Stderr | Should Match "not running"
    }

    It "exits 0 for Stop when Docker is not running" {
        $stoppedPath = Join-Path $TestDrive "stopped-docker-stop"
        New-FailingDocker -Directory $stoppedPath

        $run = Invoke-ControlCenterProcess -Arguments "-Action Stop" -PathDirectory $stoppedPath

        $run.ExitCode | Should Be 0
        $run.Stdout | Should Match "app is not running either"
    }
}

Describe "Error and JSON helpers" {
    . $commonScript

    It "gives an unexpected exception exit 5, not a documented code" {
        $thrown = Get-ThrownError { throw "bug" }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 5
    }

    It "enumerates a JSON array as separate objects" {
        $items = @(ConvertFrom-ControlCenterJson -Lines @('[{"a":1},', '{"a":2}]'))

        $items.Count | Should Be 2
        $items[1].a | Should Be 2
    }

    It "returns a JSON object as one item" {
        $items = @(ConvertFrom-ControlCenterJson -Lines @('{"a":1}'))

        $items.Count | Should Be 1
    }

    It "keeps a native command's stderr out of its output" {
        $shell = (Get-Process -Id $PID).Path
        $result = Invoke-ControlCenterNative -FilePath $shell -Arguments @(
            "-NoProfile", "-NonInteractive", "-Command",
            "[Console]::Error.WriteLine('WARN on stderr'); [Console]::Out.WriteLine('{}')"
        )

        $result.ExitCode | Should Be 0
        ($result.Output -join "") | Should Be "{}"
        ($result.Errors -join "") | Should Match "WARN on stderr"
    }
}

Describe "Test-ControlCenterAbsolutePath" {
    . $commonScript

    $cases = @(
        @{ Path = "C:\DIAL\data"; Windows = $true; Expected = $true },
        @{ Path = "C:/DIAL/data"; Windows = $true; Expected = $true },
        @{ Path = "\\server\share\data"; Windows = $true; Expected = $true },
        @{ Path = "\data"; Windows = $true; Expected = $false },
        @{ Path = "data"; Windows = $true; Expected = $false },
        @{ Path = "/srv/data"; Windows = $false; Expected = $true },
        @{ Path = "srv/data"; Windows = $false; Expected = $false }
    )
    foreach ($case in $cases) {
        It "treats '$($case.Path)' as absolute=$($case.Expected) when Windows=$($case.Windows)" {
            Test-ControlCenterAbsolutePath -Path $case.Path -Windows $case.Windows |
                Should Be $case.Expected
        }
    }
}

# Each It in this Describe and in Start-ControlCenter sits in its own Context:
# mocks with -ParameterFilter otherwise outlive their It and take precedence
# over the next test's catch-all mocks.
Describe "Resolve-ControlCenterDocker" {
    . $commonScript

    Context "reports Docker not installed" {
        It "reports Docker not installed" {
            Mock Find-ControlCenterCommand { $null }

            $thrown = Get-ThrownError { Resolve-ControlCenterDocker }

            Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 1
            Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "NotInstalled"
        }
    }

    Context "reports Docker installed but not running" {
        It "reports Docker installed but not running" {
            Mock Find-ControlCenterCommand { "docker" }
            Mock Invoke-ControlCenterNative { New-NativeResult -ExitCode 1 } `
                -ParameterFilter { $Arguments[0] -eq "info" }

            $thrown = Get-ThrownError { Resolve-ControlCenterDocker }

            Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 1
            Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "EngineStopped"
        }
    }

    Context "reports a missing compose plugin" {
        It "reports a missing compose plugin" {
            Mock Find-ControlCenterCommand { "docker" }
            Mock Invoke-ControlCenterNative { New-NativeResult }
            Mock Invoke-ControlCenterNative { New-NativeResult -ExitCode 1 } `
                -ParameterFilter { $Arguments[0] -eq "compose" }

            $thrown = Get-ThrownError { Resolve-ControlCenterDocker }

            Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 1
            Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "NoCompose"
        }
    }

    Context "returns the docker path when the engine and compose work" {
        It "returns the docker path when the engine and compose work" {
            Mock Find-ControlCenterCommand { "/usr/bin/docker" }
            Mock Invoke-ControlCenterNative { New-NativeResult }

            Resolve-ControlCenterDocker | Should Be "/usr/bin/docker"
        }
    }
}

Describe "Get-ControlCenterApp" {
    . $commonScript

    $configJson = @'
{"name":"glazingcontrolapp","services":{"app":{
  "container_name":"glazing-control-app","image":"glazing-control-app",
  "ports":[{"target":8000,"published":"8000"}],
  "volumes":[{"type":"bind","source":"/srv/data","target":"/app/svc/data"},
             {"type":"volume","source":"cache","target":"/cache"}],
  "environment":{"HALIO_SITE_ID":"placeholder"}}}}
'@

    It "fails with exit 2 when the env file is missing" {
        Mock Invoke-ControlCenterNative { New-NativeResult }
        $project = New-TestProject -EnvFile (Join-Path $TestDrive "missing.env")

        $thrown = Get-ThrownError { Get-ControlCenterApp -Project $project }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 2
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "NoEnvFile"
        Assert-MockCalled Invoke-ControlCenterNative -Scope It -Times 0 -Exactly
    }

    It "fails with exit 2 when compose cannot read the config" {
        $envFile = Join-Path $TestDrive "bad.env"
        Set-Content -LiteralPath $envFile -Value ""
        Mock Invoke-ControlCenterNative {
            New-NativeResult -ExitCode 1 -Output @("required variable HALIO_API_URL is missing")
        }

        $thrown = Get-ThrownError { Get-ControlCenterApp -Project (New-TestProject -EnvFile $envFile) }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 2
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "ComposeConfig"
    }

    It "reads the container, port, and bind mounts without resolving paths" {
        $envFile = Join-Path $TestDrive "good.env"
        Set-Content -LiteralPath $envFile -Value ""
        Mock Invoke-ControlCenterNative { New-NativeResult -Output @($configJson) }

        $app = Get-ControlCenterApp -Project (New-TestProject -EnvFile $envFile)

        $app.ContainerName | Should Be "glazing-control-app"
        $app.Port | Should Be 8000
        $app.Mounts.Count | Should Be 1
        $app.Mounts[0].Source | Should Be "/srv/data"
        Assert-MockCalled Invoke-ControlCenterNative -Scope It -Times 1 -Exactly -ParameterFilter {
            ($Arguments -contains "--no-path-resolution") -and ($Arguments -contains $envFile)
        }
    }

    It "parses the config when compose also warns on stderr" {
        $envFile = Join-Path $TestDrive "warn.env"
        Set-Content -LiteralPath $envFile -Value ""
        Mock Invoke-ControlCenterNative {
            New-NativeResult -Output @($configJson) -Errors @("WARN[0000] a compose warning")
        }

        $app = Get-ControlCenterApp -Project (New-TestProject -EnvFile $envFile)

        $app.ContainerName | Should Be "glazing-control-app"
    }

    It "reads a published port other than 8000" {
        $envFile = Join-Path $TestDrive "port.env"
        Set-Content -LiteralPath $envFile -Value ""
        $otherPort = $configJson.Replace('"published":"8000"', '"published":"8080"')
        Mock Invoke-ControlCenterNative { New-NativeResult -Output @($otherPort) }

        $app = Get-ControlCenterApp -Project (New-TestProject -EnvFile $envFile)

        $app.Port | Should Be 8080
    }
}

Describe "Assert-ControlCenterMounts" {
    . $commonScript

    It "accepts four existing absolute paths with audit.db" {
        $mounts = New-TestMounts -Root (Join-Path $TestDrive "ok")

        { Assert-ControlCenterMounts -App (New-TestApp -Mounts $mounts) } | Should Not Throw
    }

    $cases = @(
        @{ Index = 0; Variable = "SVC_PRODUCTION_DATA_DIR" },
        @{ Index = 1; Variable = "SVC_PRODUCTION_CONFIG_DIR" },
        @{ Index = 2; Variable = "SVC_DB_BACKUP_DIR" },
        @{ Index = 3; Variable = "SVC_JETI_CAPTURE_PATH" }
    )
    foreach ($case in $cases) {
        It "fails with exit 2 when $($case.Variable) does not exist" {
            $mounts = New-TestMounts -Root (Join-Path $TestDrive "missing-$($case.Index)")
            Remove-Item -LiteralPath $mounts[$case.Index].Source -Recurse -Force

            $thrown = Get-ThrownError {
                Assert-ControlCenterMounts -App (New-TestApp -Mounts $mounts)
            }

            Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 2
            Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "MissingPath"
            $thrown.Exception.Message | Should Match $case.Variable
        }
    }

    It "fails with exit 2 on a relative path" {
        $mounts = New-TestMounts -Root (Join-Path $TestDrive "relative")
        $mounts[1].Source = "svc/config/production"

        $thrown = Get-ThrownError { Assert-ControlCenterMounts -App (New-TestApp -Mounts $mounts) }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 2
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "RelativePath"
        $thrown.Exception.Message | Should Match "SVC_PRODUCTION_CONFIG_DIR"
    }

    It "fails with exit 2 when audit.db is missing" {
        $mounts = New-TestMounts -Root (Join-Path $TestDrive "no-db")
        Remove-Item -LiteralPath (Join-Path $mounts[0].Source "audit.db")

        $thrown = Get-ThrownError { Assert-ControlCenterMounts -App (New-TestApp -Mounts $mounts) }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 2
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "NoDatabase"
    }
}

Describe "Start-ControlCenter" {
    . $commonScript

    $running = [pscustomobject]@{ Status = "running"; RestartCount = 0 }

    Context "does not run compose up when audit.db is missing" {
        It "does not run compose up when audit.db is missing" {
            Mock Get-ControlCenterApp { New-TestApp -Mounts @(
                [pscustomobject]@{ Source = (Join-Path $TestDrive "empty"); Target = "/app/svc/data" }
            ) }
            New-Item -ItemType Directory -Path (Join-Path $TestDrive "empty") -Force | Out-Null
            Mock Invoke-ControlCenterCompose { New-NativeResult }

            $thrown = Get-ThrownError { Start-ControlCenter -Project (New-TestProject) -TimeoutSeconds 1 }

            Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 2
            Assert-MockCalled Invoke-ControlCenterCompose -Scope It -Times 0 -Exactly
        }
    }

    Context "reports an app container that is already running and skips compose up" {
        It "reports an app container that is already running and skips compose up" {
            Mock Get-ControlCenterApp { New-TestApp }
            Mock Get-ControlCenterContainer { $running }
            Mock Test-ControlCenterPortOpen { $true }
            Mock Invoke-ControlCenterCompose { New-NativeResult }
            Mock Get-ControlCenterHealthResponse { New-TestHealth }
            Mock Write-Host { }

            Start-ControlCenter -Project (New-TestProject) -TimeoutSeconds 1

            Assert-MockCalled Invoke-ControlCenterCompose -Scope It -Times 0 -Exactly
            Assert-MockCalled Write-Host -Scope It -ParameterFilter {
                $Object -eq "glazing-control-app is already running."
            }
        }
    }

    Context "fails with exit 2 when another process holds the port" {
        It "fails with exit 2 when another process holds the port" {
            Mock Get-ControlCenterApp { New-TestApp }
            Mock Get-ControlCenterContainer { $null }
            Mock Test-ControlCenterPortOpen { $true }
            Mock Invoke-ControlCenterCompose { New-NativeResult }

            $thrown = Get-ThrownError { Start-ControlCenter -Project (New-TestProject) -TimeoutSeconds 1 }

            Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 2
            Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "PortInUse"
            Assert-MockCalled Invoke-ControlCenterCompose -Scope It -Times 0 -Exactly
        }
    }

    Context "starts without --build when the image exists" {
        It "starts without --build when the image exists" {
            Mock Get-ControlCenterApp { New-TestApp }
            Mock Get-ControlCenterContainer { $null }
            Mock Get-ControlCenterContainer { $running } -ParameterFilter { $script:upCalled }
            Mock Test-ControlCenterPortOpen { $false }
            Mock Test-ControlCenterImage { $true }
            Mock Invoke-ControlCenterCompose { $script:upCalled = $true; New-NativeResult }
            Mock Get-ControlCenterHealthResponse { New-TestHealth }
            Mock Write-Host { }
            $script:upCalled = $false

            Start-ControlCenter -Project (New-TestProject) -TimeoutSeconds 1

            Assert-MockCalled Invoke-ControlCenterCompose -Scope It -Times 1 -Exactly -ParameterFilter {
                $Arguments[0] -eq "up" -and -not ($Arguments -contains "--build")
            }
        }
    }

    Context "builds when the image is missing" {
        It "builds when the image is missing" {
            Mock Get-ControlCenterApp { New-TestApp }
            Mock Get-ControlCenterContainer { $running } -ParameterFilter { $script:upCalled }
            Mock Get-ControlCenterContainer { $null }
            Mock Test-ControlCenterPortOpen { $false }
            Mock Test-ControlCenterImage { $false }
            Mock Invoke-ControlCenterCompose { $script:upCalled = $true; New-NativeResult }
            Mock Get-ControlCenterHealthResponse { New-TestHealth }
            Mock Write-Host { }
            $script:upCalled = $false

            Start-ControlCenter -Project (New-TestProject) -TimeoutSeconds 1

            Assert-MockCalled Invoke-ControlCenterCompose -Scope It -Times 1 -Exactly -ParameterFilter {
                $Arguments -contains "--build"
            }
        }
    }

    Context "runs compose up for a stopped app container when the port is free" {
        It "runs compose up for a stopped app container when the port is free" {
            Mock Get-ControlCenterApp { New-TestApp }
            Mock Get-ControlCenterContainer { [pscustomobject]@{ Status = "exited"; RestartCount = 3 } }
            Mock Get-ControlCenterContainer { $running } -ParameterFilter { $script:upCalled }
            Mock Test-ControlCenterPortOpen { $false }
            Mock Test-ControlCenterImage { $true }
            Mock Invoke-ControlCenterCompose { $script:upCalled = $true; New-NativeResult }
            Mock Get-ControlCenterHealthResponse { New-TestHealth }
            Mock Write-Host { }
            $script:upCalled = $false

            Start-ControlCenter -Project (New-TestProject) -TimeoutSeconds 1

            Assert-MockCalled Invoke-ControlCenterCompose -Scope It -Times 1 -Exactly -ParameterFilter {
                $Arguments[0] -eq "up"
            }
        }
    }

    Context "fails with exit 3 for a paused app container" {
        It "fails with exit 3 for a paused app container" {
            Mock Get-ControlCenterApp { New-TestApp }
            Mock Get-ControlCenterContainer { [pscustomobject]@{ Status = "paused"; RestartCount = 0 } }
            Mock Test-ControlCenterPortOpen { $true }
            Mock Invoke-ControlCenterCompose { New-NativeResult }

            $thrown = Get-ThrownError { Start-ControlCenter -Project (New-TestProject) -TimeoutSeconds 1 }

            Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 3
            Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "Paused"
            Assert-MockCalled Invoke-ControlCenterCompose -Scope It -Times 0 -Exactly
        }
    }

    Context "fails with exit 3 when compose up fails" {
        It "fails with exit 3 when compose up fails" {
            Mock Get-ControlCenterApp { New-TestApp }
            Mock Get-ControlCenterContainer { $null }
            Mock Test-ControlCenterPortOpen { $false }
            Mock Test-ControlCenterImage { $true }
            Mock Invoke-ControlCenterCompose { New-NativeResult -ExitCode 1 -Output @("boom") }
            Mock Write-Host { }

            $thrown = Get-ThrownError { Start-ControlCenter -Project (New-TestProject) -TimeoutSeconds 1 }

            Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 3
            Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "ComposeUp"
        }
    }
}

Describe "Wait-ControlCenterHealth" {
    . $commonScript

    It "returns the health response once /health answers" {
        Mock Get-ControlCenterHealthResponse { New-TestHealth }

        $health = Wait-ControlCenterHealth -Project (New-TestProject) -App (New-TestApp) -TimeoutSeconds 1

        $health.status | Should Be "ok"
    }

    It "fails with exit 3 and prints logs when the container exits" {
        Mock Get-ControlCenterHealthResponse { $null }
        Mock Get-ControlCenterContainer { [pscustomobject]@{ Status = "exited"; RestartCount = 0 } }
        Mock Write-ControlCenterLogs { }

        $thrown = Get-ThrownError {
            Wait-ControlCenterHealth -Project (New-TestProject) -App (New-TestApp) -TimeoutSeconds 30
        }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 3
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "ContainerExited"
        Assert-MockCalled Write-ControlCenterLogs -Scope It -Times 1 -Exactly
    }

    It "fails with exit 3 when the container restarts while waiting" {
        Mock Get-ControlCenterHealthResponse { $null }
        Mock Get-ControlCenterContainer { [pscustomobject]@{ Status = "running"; RestartCount = 2 } }
        Mock Write-ControlCenterLogs { }

        $thrown = Get-ThrownError {
            Wait-ControlCenterHealth -Project (New-TestProject) -App (New-TestApp) `
                -TimeoutSeconds 30 -RestartCount 1
        }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 3
    }

    It "fails with exit 4 when /health does not answer in time" {
        Mock Get-ControlCenterHealthResponse { $null }
        Mock Get-ControlCenterContainer { [pscustomobject]@{ Status = "running"; RestartCount = 0 } }
        Mock Start-Sleep { }

        $thrown = Get-ThrownError {
            Wait-ControlCenterHealth -Project (New-TestProject) -App (New-TestApp) -TimeoutSeconds 0
        }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 4
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "HealthTimeout"
    }
}

Describe "Write-ControlCenterHealth" {
    . $commonScript

    It "accepts an ok production response" {
        Mock Write-Host { }
        Mock Write-Warning { }

        { Write-ControlCenterHealth -Health (New-TestHealth) -Port 8000 } | Should Not Throw
        Assert-MockCalled Write-Warning -Scope It -Times 0 -Exactly
    }

    It "treats degraded as success with a warning" {
        Mock Write-Host { }
        Mock Write-Warning { }

        $health = New-TestHealth -Status "degraded" -SensorErrors @("EKO-1: timeout")
        { Write-ControlCenterHealth -Health $health -Port 8000 } | Should Not Throw
        Assert-MockCalled Write-Warning -Scope It -Times 1 -Exactly
        Assert-MockCalled Write-Host -Scope It -ParameterFilter { $Object -match "EKO-1: timeout" }
    }

    It "fails with exit 2 on the development environment" {
        Mock Write-Host { }

        $health = New-TestHealth -Environment "development" -ControlSource "simulated"
        $thrown = Get-ThrownError { Write-ControlCenterHealth -Health $health -Port 8000 }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 2
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "WrongEnvironment"
    }

    It "fails with exit 2 when production reports simulated control" {
        Mock Write-Host { }

        $thrown = Get-ThrownError {
            Write-ControlCenterHealth -Health (New-TestHealth -ControlSource "simulated") -Port 8000
        }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 2
    }
}

Describe "Stop-ControlCenter and Get-ControlCenterStatus" {
    . $commonScript

    It "stops with compose down" {
        Mock Get-ControlCenterApp { New-TestApp }
        Mock Invoke-ControlCenterCompose { New-NativeResult }
        Mock Write-Host { }

        Stop-ControlCenter -Project (New-TestProject)

        Assert-MockCalled Invoke-ControlCenterCompose -Scope It -Times 1 -Exactly -ParameterFilter {
            $Arguments[0] -eq "down"
        }
    }

    It "fails with exit 3 when compose down fails" {
        Mock Get-ControlCenterApp { New-TestApp }
        Mock Invoke-ControlCenterCompose { New-NativeResult -ExitCode 1 }

        $thrown = Get-ThrownError { Stop-ControlCenter -Project (New-TestProject) }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 3
    }

    It "reports a stopped app with exit 3 and starts nothing" {
        Mock Get-ControlCenterApp { New-TestApp }
        Mock Get-ControlCenterContainer { $null }
        Mock Test-ControlCenterPortOpen { $false }
        Mock Invoke-ControlCenterCompose { New-NativeResult }

        $thrown = Get-ThrownError { Get-ControlCenterStatus -Project (New-TestProject) }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 3
        Get-ControlCenterErrorReason -ErrorRecord $thrown | Should Be "NotRunning"
        Assert-MockCalled Invoke-ControlCenterCompose -Scope It -Times 0 -Exactly
    }

    It "says when another process holds the port of a stopped app" {
        Mock Get-ControlCenterApp { New-TestApp }
        Mock Get-ControlCenterContainer { $null }
        Mock Test-ControlCenterPortOpen { $true }

        $thrown = Get-ThrownError { Get-ControlCenterStatus -Project (New-TestProject) }

        Get-ControlCenterExitCode -ErrorRecord $thrown | Should Be 3
        $thrown.Exception.Message | Should Match "Another process holds port 8000"
    }

    It "reports a running app's health" {
        Mock Get-ControlCenterApp { New-TestApp }
        Mock Get-ControlCenterContainer { [pscustomobject]@{ Status = "running"; RestartCount = 0 } }
        Mock Get-ControlCenterHealthResponse { New-TestHealth }
        Mock Write-Host { }

        { Get-ControlCenterStatus -Project (New-TestProject) } | Should Not Throw
    }
}

Describe "Test-ControlCenterPortOpen" {
    . $commonScript

    It "sees a listener on a local port" {
        $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Loopback, 0)
        $listener.Start()
        try {
            $port = $listener.LocalEndpoint.Port
            Test-ControlCenterPortOpen -Port $port | Should Be $true
        }
        finally {
            $listener.Stop()
        }
    }

    It "reports a closed port as free" {
        $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Loopback, 0)
        $listener.Start()
        $port = $listener.LocalEndpoint.Port
        $listener.Stop()

        Test-ControlCenterPortOpen -Port $port | Should Be $false
    }
}
