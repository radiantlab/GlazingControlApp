$scriptsRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$t10aScript = Join-Path $scriptsRoot "Get-T10ALogs.ps1"
$jetiScript = Join-Path $scriptsRoot "Get-JetiLogs.ps1"
$agentScript = Join-Path $scriptsRoot "Start-SensorAgent.ps1"
$commonScript = Join-Path $scriptsRoot "SensorBackup.Common.ps1"
$powershellExe = (Get-Command powershell.exe -ErrorAction Stop).Source

Describe "Sensor backup script syntax" {
    foreach ($scriptPath in @($commonScript, $t10aScript, $jetiScript, $agentScript)) {
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

    It "exposes only SourceFile and DataDirectory for scheduled JETI backups" {
        $tokens = $null
        $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile(
            $jetiScript,
            [ref]$tokens,
            [ref]$errors
        )
        $parameters = @($ast.ParamBlock.Parameters | ForEach-Object {
            $_.Name.VariablePath.UserPath
        })

        $parameters.Count | Should Be 2
        $parameters[0] | Should Be "SourceFile"
        $parameters[1] | Should Be "DataDirectory"
    }
}

Describe "Stable serial-port selectors" {
    . $commonScript

    It "resolves auto to the one matching USB identity" {
        $device = [pscustomobject]@{
            port = "auto"
            port_identity = [pscustomobject]@{
                vid = "0403"
                pid = "6001"
                serial_number = "T10A-ABC"
            }
        }
        $inventory = @(
            [pscustomobject]@{
                port = "COM4"; vid = 0x0403; pid = 0x6001
                serial_number = "OTHER"; manufacturer = "FTDI"
                product = "USB Serial Port"; location = $null; hwid = "first"
            },
            [pscustomobject]@{
                port = "COM12"; vid = 0x0403; pid = 0x6001
                serial_number = "T10A-ABC"; manufacturer = "FTDI"
                product = "USB Serial Port"; location = $null; hwid = "second"
            }
        )

        Resolve-SensorSerialPort -Device $device -Inventory $inventory |
            Should Be "COM12"
    }

    It "rejects an ambiguous auto selector" {
        $device = [pscustomobject]@{
            port = "auto"
            port_identity = [pscustomobject]@{ vid = "0403"; pid = "6001" }
        }
        $inventory = @(
            [pscustomobject]@{
                port = "COM4"; vid = 0x0403; pid = 0x6001
                serial_number = "A"; manufacturer = $null
                product = $null; location = $null; hwid = "first"
            },
            [pscustomobject]@{
                port = "COM12"; vid = 0x0403; pid = 0x6001
                serial_number = "B"; manufacturer = $null
                product = $null; location = $null; hwid = "second"
            }
        )

        $threw = $false
        try {
            [void](Resolve-SensorSerialPort -Device $device -Inventory $inventory)
        }
        catch {
            $threw = $true
        }
        $threw | Should Be $true
    }
}

Describe "Get-T10ALogs" {
    It "validates a configured device without opening its COM port" {
        $caseRoot = Join-Path $TestDrive "t10a"
        New-Item -ItemType Directory -Path $caseRoot -Force | Out-Null
        $configPath = Join-Path $caseRoot "sensors_config.json"
        $outputPath = Join-Path $caseRoot "output"
        @'
{
  "t10a": [
    {
      "device_id": "KM-TEST",
      "port": "COM999",
      "heads": [
        {"head_no": 0, "sensor_id": "KM-TEST-H0", "label": "Test"}
      ]
    }
  ],
  "jeti_spectraval": []
}
'@ | Set-Content -LiteralPath $configPath -Encoding UTF8

        $output = & $powershellExe -NoProfile -NonInteractive `
            -ExecutionPolicy Bypass -File $t10aScript `
            -ConfigPath $configPath -OutputPath $outputPath -DryRun 2>&1
        $exitCode = $LASTEXITCODE

        $exitCode | Should Be 0
        ($output -join "`n") | Should Match "no COM ports were opened"
        @(Get-ChildItem -LiteralPath $outputPath -Filter "*.csv").Count | Should Be 0
    }

    It "returns a configuration exit code for a missing port" {
        $caseRoot = Join-Path $TestDrive "t10a-invalid"
        New-Item -ItemType Directory -Path $caseRoot -Force | Out-Null
        $configPath = Join-Path $caseRoot "sensors_config.json"
        $outputPath = Join-Path $caseRoot "output"
        @'
{
  "t10a": [
    {
      "device_id": "KM-TEST",
      "heads": [
        {"head_no": 0, "sensor_id": "KM-TEST-H0", "label": "Test"}
      ]
    }
  ]
}
'@ | Set-Content -LiteralPath $configPath -Encoding UTF8

        $output = & $powershellExe -NoProfile -NonInteractive `
            -ExecutionPolicy Bypass -File $t10aScript `
            -ConfigPath $configPath -OutputPath $outputPath -DryRun 2>&1
        $LASTEXITCODE | Should Be 2
    }
}

Describe "Get-JetiLogs file capture" {
    It "incrementally backs up a live LiVal capture with a non-cap suffix" {
        $caseRoot = Join-Path $TestDrive "jeti-lival-incremental"
        $backupPath = Join-Path $caseRoot "backup"
        New-Item -ItemType Directory -Path $caseRoot -Force | Out-Null
        $sourcePath = Join-Path $caseRoot "JETI_capture.xlsx"
        $firstRow = "Date and Time:; 07/27/2026; 04:00:00pm; ; Ev [lx]; 10;`r`n"
        $secondRow = "Date and Time:; 07/27/2026; 04:01:00pm; ; Ev [lx]; 11;`r`n"
        [System.IO.File]::WriteAllText(
            $sourcePath,
            $firstRow,
            [System.Text.Encoding]::ASCII
        )

        $writer = [System.IO.FileStream]::new(
            $sourcePath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::ReadWrite
        )
        try {
            $firstOutput = & $powershellExe -NoProfile -NonInteractive `
                -ExecutionPolicy Bypass -File $jetiScript `
                -SourceFile $sourcePath -DataDirectory $backupPath 2>&1
            $firstExit = $LASTEXITCODE

            [void]$writer.Seek(0, [System.IO.SeekOrigin]::End)
            $bytes = [System.Text.Encoding]::ASCII.GetBytes($secondRow)
            $writer.Write($bytes, 0, $bytes.Length)
            $writer.Flush()

            $secondOutput = & $powershellExe -NoProfile -NonInteractive `
                -ExecutionPolicy Bypass -File $jetiScript `
                -SourceFile $sourcePath -DataDirectory $backupPath 2>&1
            $secondExit = $LASTEXITCODE
        }
        finally {
            $writer.Dispose()
        }

        $firstExit | Should Be 0
        $secondExit | Should Be 0
        ($firstOutput -join "`n") | Should Match "Backed up"
        ($secondOutput -join "`n") | Should Match "Backed up"
        $chunks = @(
            Get-ChildItem -LiteralPath $backupPath -File -Filter "*.capture.txt" |
                Sort-Object Name
        )
        $chunks.Count | Should Be 2
        $combined = ($chunks | ForEach-Object {
            [System.IO.File]::ReadAllText($_.FullName)
        }) -join ""
        $combined | Should Be ($firstRow + $secondRow)
        $cursor = Get-ChildItem -LiteralPath (Join-Path $backupPath ".state") `
            -File -Filter "*.cursor.json" | Select-Object -First 1
        ([long]((Get-Content -LiteralPath $cursor.FullName -Raw | ConvertFrom-Json).offset)) |
            Should Be ([long](Get-Item -LiteralPath $sourcePath).Length)
    }

}
