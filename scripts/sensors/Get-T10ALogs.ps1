<#
.SYNOPSIS
    Captures timestamped T-10A measurements using the production sensor config.

.DESCRIPTION
    Opens each configured T-10A COM port, enters PC mode, polls every configured
    head, and appends raw replies plus parsed lux values to one CSV per device/day.
    The script never changes the sensor configuration or existing rows.

    Windows serial ports are exclusive. Stop the application (or otherwise
    release its T-10A COM ports) before this scheduled task runs.

.PARAMETER ConfigPath
    Path to the production sensors_config.json.

.PARAMETER OutputPath
    Root for daily CSV and operational log files.

.PARAMETER SamplesPerHead
    Measurements captured from every configured head in this invocation.

.PARAMETER SampleIntervalSeconds
    Delay between samples when SamplesPerHead is greater than one.

.PARAMETER RetentionDays
    Optional rotation for CSV files created under OutputPath. Zero keeps all files.

.PARAMETER DryRun
    Validates configuration and prints the capture plan without opening a COM port.

.NOTES
    Exit codes: 0 success, 2 configuration error, 3 no captures succeeded,
    4 partial capture failure, 5 another copy is already running.
#>

[CmdletBinding()]
param(
    [string]$ConfigPath = $env:SENSORS_CONFIG_FILE,
    [string]$OutputPath = (Join-Path $PSScriptRoot "backups\t10a"),
    [ValidateRange(1, 10000)]
    [int]$SamplesPerHead = 1,
    [ValidateRange(0, 86400)]
    [double]$SampleIntervalSeconds = 1,
    [ValidateRange(0, 36500)]
    [int]$RetentionDays = 0,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "SensorBackup.Common.ps1")

function Get-T10ABcc {
    param([byte[]]$BodyWithEtx)
    [byte]$bcc = 0
    foreach ($value in $BodyWithEtx) {
        $bcc = $bcc -bxor $value
    }
    return [System.Text.Encoding]::ASCII.GetBytes(("{0:X2}" -f $bcc))
}

function New-T10AFrame {
    param(
        [int]$HeadNo,
        [string]$Command,
        [string]$Parameters,
        [int]$HeadIndexBase,
        [string]$BodyTemplate
    )

    $headAddress = $HeadNo + $HeadIndexBase
    $body = $BodyTemplate.Replace("{head:02d}", ("{0:D2}" -f $headAddress))
    $body = $body.Replace("{head}", [string]$headAddress)
    $body = $body.Replace("{head_no}", [string]$HeadNo)
    $body = $body.Replace("{cmd}", $Command)
    $body = $body.Replace("{params}", $Parameters)
    $bodyWithEtx = [byte[]](
        [System.Text.Encoding]::ASCII.GetBytes($body) + [byte]0x03
    )
    return [byte[]](
        [byte]0x02 +
        $bodyWithEtx +
        (Get-T10ABcc -BodyWithEtx $bodyWithEtx) +
        [byte]0x0D +
        [byte]0x0A
    )
}

function Read-T10ABytes {
    param(
        [System.IO.Ports.SerialPort]$Port,
        [int]$ExpectedLength
    )

    $values = New-Object System.Collections.Generic.List[byte]
    while ($values.Count -lt $ExpectedLength) {
        try {
            $values.Add([byte]$Port.ReadByte())
        }
        catch [System.TimeoutException] {
            break
        }
    }
    return $values.ToArray()
}

function Invoke-T10AExchange {
    param(
        [System.IO.Ports.SerialPort]$Port,
        [byte[]]$Frame,
        [int]$ReplyLength,
        [int]$DelayMilliseconds
    )

    $Port.DiscardInBuffer()
    $Port.Write($Frame, 0, $Frame.Length)
    if ($DelayMilliseconds -gt 0) {
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
    return Read-T10ABytes -Port $Port -ExpectedLength $ReplyLength
}

function ConvertFrom-T10ALux {
    param([byte[]]$Reply)

    if ($null -eq $Reply -or $Reply.Length -eq 0) {
        return $null
    }

    $body = [System.Text.Encoding]::ASCII.GetString($Reply).Trim()
    if ($body.StartsWith([string][char]0x02)) {
        $body = $body.Substring(1)
    }
    $etx = $body.IndexOf([char]0x03)
    if ($etx -ge 0) {
        $body = $body.Substring(0, $etx)
    }
    if ($body.ToUpperInvariant().Contains("ERR")) {
        return $null
    }

    if ($body.Length -ge 14) {
        $field = $body.Substring(8, [Math]::Min(6, $body.Length - 8)).Replace(" ", "")
        if ($field.Length -eq 5 -and @("+", "-") -contains $field.Substring(0, 1)) {
            $field = $field.Substring(0, 1) + "0" + $field.Substring(1)
        }
        if ($field -match '^(?<Sign>[+-])(?<Mantissa>\d{4})(?<Exponent>\d)$') {
            $sign = 1
            if ($Matches.Sign -eq "-") { $sign = -1 }
            return [double]($sign * [int]$Matches.Mantissa * [Math]::Pow(10, ([int]$Matches.Exponent - 4)))
        }
    }

    if ($body -match '(?<Value>[+-]\d{4}E[+-]?\d{1,2})') {
        return [double]::Parse(
            $Matches.Value,
            [System.Globalization.CultureInfo]::InvariantCulture
        )
    }
    if ($body -match '(?<Sign>[+-])(?<Mantissa>\d{4})(?<Exponent>[+-]\d{1,2})') {
        $sign = 1
        if ($Matches.Sign -eq "-") { $sign = -1 }
        return [double]($sign * [int]$Matches.Mantissa * [Math]::Pow(10, [int]$Matches.Exponent))
    }
    if ($body -match '(?<Value>[+-]?(?:\d+\.\d*|\d*\.\d+)(?:E[+-]?\d+)?)') {
        return [double]::Parse(
            $Matches.Value,
            [System.Globalization.CultureInfo]::InvariantCulture
        )
    }
    return $null
}

function Get-OptionalProperty {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Default
    )
    if ($Object.PSObject.Properties.Name -contains $Name -and $null -ne $Object.$Name) {
        return $Object.$Name
    }
    return $Default
}

$mutex = $null
$logPath = $null
try {
    if (-not (Test-Path -LiteralPath $OutputPath -PathType Container)) {
        New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null
    }
    $resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
    $logPath = Join-Path $resolvedOutput ("Get-T10ALogs-{0}.log" -f [DateTime]::UtcNow.ToString("yyyyMMdd"))

    try {
        $mutex = New-SensorBackupMutex -Identity "t10a|$resolvedOutput"
    }
    catch {
        Write-SensorBackupLog -Level ERROR -Message $_.Exception.Message -LogPath $logPath
        exit 5
    }

    $config = Read-SensorConfiguration -ConfigPath $ConfigPath
    if (-not ($config.PSObject.Properties.Name -contains "t10a")) {
        throw "Sensor configuration has no 't10a' array."
    }
    $devices = @($config.t10a | Where-Object {
        -not ($_.PSObject.Properties.Name -contains "enabled") -or [bool]$_.enabled
    })
    if ($devices.Count -eq 0) {
        throw "Sensor configuration has no enabled T-10A devices."
    }

    foreach ($device in $devices) {
        if ([string]::IsNullOrWhiteSpace([string]$device.device_id)) {
            throw "Every T-10A device requires device_id."
        }
        if ([string]::IsNullOrWhiteSpace([string]$device.port)) {
            throw "T-10A '$($device.device_id)' requires a COM port."
        }
        if (
            ([string]$device.port).Trim().ToLowerInvariant() -eq "auto" -and
            -not (Test-SensorHasPortIdentity -Device $device)
        ) {
            throw "T-10A '$($device.device_id)' port 'auto' requires port_identity."
        }
        if (@($device.heads).Count -eq 0) {
            throw "T-10A '$($device.device_id)' requires at least one head."
        }
        foreach ($head in @($device.heads)) {
            if ($null -eq $head.head_no -or [string]::IsNullOrWhiteSpace([string]$head.sensor_id)) {
                throw "T-10A '$($device.device_id)' has an invalid head entry."
            }
        }
        Write-SensorBackupLog -Level INFO -Message (
            "Plan: device={0}, port-selector={1}, heads={2}, samples={3}" -f
            $device.device_id, $device.port, @($device.heads).Count, $SamplesPerHead
        ) -LogPath $logPath
    }

    if ($DryRun) {
        Write-SensorBackupLog -Level INFO -Message "Dry run complete; no COM ports were opened." -LogPath $logPath
        exit 0
    }

    $successCount = 0
    $failureCount = 0
    foreach ($device in $devices) {
        $safeDevice = Get-SensorSafeName -Value ([string]$device.device_id)
        $csvPath = Join-Path $resolvedOutput (
            "t10a-{0}-{1}.csv" -f $safeDevice, [DateTime]::UtcNow.ToString("yyyyMMdd")
        )
        $protocol = Get-OptionalProperty -Object $device -Name "protocol" -Default ([pscustomobject]@{})
        $baudrate = [int](Get-OptionalProperty -Object $protocol -Name "baudrate" -Default (
            Get-OptionalProperty -Object $device -Name "baudrate" -Default 9600
        ))
        $timeoutSeconds = [double](Get-OptionalProperty -Object $device -Name "timeout_s" -Default 1.0)
        $xonxoff = ConvertTo-SensorBoolean -Value (
            Get-OptionalProperty -Object $protocol -Name "xonxoff" -Default $true
        ) -Default $true
        $sendPcMode = ConvertTo-SensorBoolean -Value (
            Get-OptionalProperty -Object $protocol -Name "send_pc_mode" -Default $true
        ) -Default $true
        $headIndexBase = [int](Get-OptionalProperty -Object $protocol -Name "head_index_base" -Default 0)
        $bodyTemplate = [string](Get-OptionalProperty -Object $protocol -Name "body_template" -Default "{head:02d}{cmd}{params}")
        $measureCommand = [string](Get-OptionalProperty -Object $protocol -Name "measure_command" -Default "10")
        $measureParameters = [string](Get-OptionalProperty -Object $protocol -Name "measure_params" -Default "0200")
        $pcModeCommand = [string](Get-OptionalProperty -Object $protocol -Name "pc_mode_command" -Default "54")
        $pcModeParameters = [string](Get-OptionalProperty -Object $protocol -Name "pc_mode_params" -Default "1 ")
        $pcModeHead = [int](Get-OptionalProperty -Object $protocol -Name "pc_mode_head_no" -Default 0)
        $shortReplyLength = [int](Get-OptionalProperty -Object $protocol -Name "short_reply_len" -Default 14)
        $longReplyLength = [int](Get-OptionalProperty -Object $protocol -Name "long_reply_len" -Default 32)
        $delayMs = [int]([double](Get-OptionalProperty -Object $protocol -Name "inter_command_delay_s" -Default 0.1) * 1000)

        $port = New-Object System.IO.Ports.SerialPort
        try {
            $resolvedPort = Resolve-SensorSerialPort -Device $device
            Write-SensorBackupLog -Level INFO -Message (
                "Resolved T-10A {0} port selector {1} -> {2}." -f
                $device.device_id, $device.port, $resolvedPort
            ) -LogPath $logPath
            $port.PortName = $resolvedPort
            $port.BaudRate = $baudrate
            $port.DataBits = 7
            $port.Parity = [System.IO.Ports.Parity]::Even
            $port.StopBits = [System.IO.Ports.StopBits]::One
            $port.Handshake = [System.IO.Ports.Handshake]::None
            if ($xonxoff) {
                $port.Handshake = [System.IO.Ports.Handshake]::XOnXOff
            }
            $port.ReadTimeout = [Math]::Max(1, [int]($timeoutSeconds * 1000))
            $port.WriteTimeout = [Math]::Max(1, [int]($timeoutSeconds * 1000))
            $port.Open()
            Start-Sleep -Milliseconds 200

            if ($sendPcMode) {
                $pcFrame = New-T10AFrame -HeadNo $pcModeHead -Command $pcModeCommand `
                    -Parameters $pcModeParameters -HeadIndexBase $headIndexBase -BodyTemplate $bodyTemplate
                [void](Invoke-T10AExchange -Port $port -Frame $pcFrame `
                    -ReplyLength $shortReplyLength -DelayMilliseconds $delayMs)
            }

            for ($sample = 1; $sample -le $SamplesPerHead; $sample++) {
                foreach ($head in @($device.heads)) {
                    $reply = @()
                    $status = "ok"
                    $lux = $null
                    try {
                        $frame = New-T10AFrame -HeadNo ([int]$head.head_no) `
                            -Command $measureCommand -Parameters $measureParameters `
                            -HeadIndexBase $headIndexBase -BodyTemplate $bodyTemplate
                        $reply = Invoke-T10AExchange -Port $port -Frame $frame `
                            -ReplyLength $longReplyLength -DelayMilliseconds $delayMs
                        $lux = ConvertFrom-T10ALux -Reply $reply
                        if ($null -eq $lux) {
                            $status = "unparsed_reply"
                            $failureCount++
                        }
                        else {
                            $successCount++
                        }
                    }
                    catch {
                        $status = "read_error"
                        $failureCount++
                        Write-SensorBackupLog -Level WARN -Message (
                            "T-10A {0}/{1} capture failed: {2}" -f
                            $device.device_id, $head.sensor_id, $_.Exception.Message
                        ) -LogPath $logPath
                    }

                    $row = [pscustomobject][ordered]@{
                        timestamp_utc = [DateTime]::UtcNow.ToString("o")
                        device_id = [string]$device.device_id
                        sensor_id = [string]$head.sensor_id
                        head_no = [int]$head.head_no
                        configured_port = [string]$device.port
                        port = $resolvedPort
                        lux = $lux
                        status = $status
                        raw_reply_base64 = [Convert]::ToBase64String([byte[]]$reply)
                    }
                    if (Test-Path -LiteralPath $csvPath) {
                        $row | Export-Csv -LiteralPath $csvPath -Append -NoTypeInformation -Encoding UTF8
                    }
                    else {
                        $row | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8
                    }
                }
                if ($sample -lt $SamplesPerHead -and $SampleIntervalSeconds -gt 0) {
                    Start-Sleep -Milliseconds ([int]($SampleIntervalSeconds * 1000))
                }
            }
        }
        catch {
            $deviceFailures = @($device.heads).Count * $SamplesPerHead
            $failureCount += $deviceFailures
            Write-SensorBackupLog -Level ERROR -Message (
                "T-10A {0} on {1} could not be captured: {2}" -f
                $device.device_id, $device.port, $_.Exception.Message
            ) -LogPath $logPath
        }
        finally {
            if ($port.IsOpen) { $port.Close() }
            $port.Dispose()
        }
    }

    $rotated = Remove-ExpiredSensorBackups -RootPath $resolvedOutput `
        -RetentionDays $RetentionDays -Extensions @(".csv")
    Write-SensorBackupLog -Level INFO -Message (
        "Capture complete: succeeded={0}, failed={1}, rotated={2}." -f
        $successCount, $failureCount, $rotated
    ) -LogPath $logPath

    if ($successCount -eq 0) { exit 3 }
    if ($failureCount -gt 0) { exit 4 }
    exit 0
}
catch {
    if ($logPath) {
        Write-SensorBackupLog -Level ERROR -Message $_.Exception.Message -LogPath $logPath
    }
    else {
        Write-Error $_.Exception.Message
    }
    exit 2
}
finally {
    Close-SensorBackupMutex -Mutex $mutex
}
