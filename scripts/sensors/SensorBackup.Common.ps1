Set-StrictMode -Version 2.0

function Get-SensorSafeName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $safe = [regex]::Replace($Value.Trim(), '[^A-Za-z0-9._-]', '_')
    if ([string]::IsNullOrWhiteSpace($safe)) {
        return "unknown"
    }
    return $safe
}

function ConvertTo-SensorBoolean {
    param(
        [object]$Value,
        [bool]$Default = $false
    )

    if ($null -eq $Value) {
        return $Default
    }
    if ($Value -is [bool]) {
        return [bool]$Value
    }
    $normalized = ([string]$Value).Trim().ToLowerInvariant()
    if (@("1", "true", "yes", "on") -contains $normalized) {
        return $true
    }
    if (@("0", "false", "no", "off") -contains $normalized) {
        return $false
    }
    throw "Invalid boolean value '$Value'."
}

function ConvertTo-SensorUsbId {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    if ($Value -is [int] -or $Value -is [long]) {
        $parsed = [int]$Value
    }
    else {
        $text = ([string]$Value).Trim()
        if ($text.StartsWith("0x", [System.StringComparison]::OrdinalIgnoreCase)) {
            $text = $text.Substring(2)
        }
        $parsed = [Convert]::ToInt32($text, 16)
    }
    if ($parsed -lt 0 -or $parsed -gt 0xFFFF) {
        throw "USB ID '$Value' must be between 0x0000 and 0xFFFF."
    }
    return $parsed
}

function Get-SensorObjectProperty {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Default = $null
    )

    if (
        $null -ne $Object -and
        $Object.PSObject.Properties.Name -contains $Name -and
        $null -ne $Object.$Name
    ) {
        return $Object.$Name
    }
    return $Default
}

function ConvertFrom-SensorRegistryText {
    param([object]$Value)
    if ($null -eq $Value) {
        return $null
    }
    $text = [string]$Value
    if ($text.Contains(";")) {
        $text = $text.Substring($text.LastIndexOf(";") + 1)
    }
    $text = $text.Trim()
    if ($text) { return $text }
    return $null
}

function Get-SensorRegistryPortInventory {
    param([string[]]$ActivePorts)

    $records = @()
    foreach ($rootName in @("USB", "FTDIBUS", "SERENUM")) {
        $root = "HKLM:\SYSTEM\CurrentControlSet\Enum\$rootName"
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        foreach ($deviceKey in @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue)) {
            foreach ($instanceKey in @(Get-ChildItem -LiteralPath $deviceKey.PSPath -ErrorAction SilentlyContinue)) {
                $parametersPath = Join-Path $instanceKey.PSPath "Device Parameters"
                $parameters = Get-ItemProperty -LiteralPath $parametersPath -ErrorAction SilentlyContinue
                $portName = [string](Get-SensorObjectProperty -Object $parameters -Name "PortName" -Default "")
                if (
                    [string]::IsNullOrWhiteSpace($portName) -or
                    -not ($ActivePorts -contains $portName)
                ) {
                    continue
                }

                $properties = Get-ItemProperty -LiteralPath $instanceKey.PSPath -ErrorAction SilentlyContinue
                $identityText = [string]$deviceKey.PSChildName
                $usbVid = $null
                $usbPid = $null
                if ($identityText -match '(?i)VID[_&+]([0-9A-F]{4})') {
                    $usbVid = [Convert]::ToInt32($Matches[1], 16)
                }
                if ($identityText -match '(?i)PID[_&+]([0-9A-F]{4})') {
                    $usbPid = [Convert]::ToInt32($Matches[1], 16)
                }

                $serialNumber = $null
                if ($identityText -match '(?i)VID_[0-9A-F]{4}\+PID_[0-9A-F]{4}\+(.+)$') {
                    $serialNumber = $Matches[1]
                }
                elseif ($rootName -eq "USB") {
                    $serialNumber = [string]$instanceKey.PSChildName
                }

                $location = Get-SensorObjectProperty -Object $properties `
                    -Name "LocationInformation" -Default $null
                if ($null -eq $location -and $rootName -eq "FTDIBUS" -and $serialNumber) {
                    $usbDeviceRoot = "HKLM:\SYSTEM\CurrentControlSet\Enum\USB\VID_{0:X4}&PID_{1:X4}" -f $usbVid, $usbPid
                    if (Test-Path -LiteralPath $usbDeviceRoot) {
                        $usbInstance = @(Get-ChildItem -LiteralPath $usbDeviceRoot -ErrorAction SilentlyContinue) |
                            Where-Object {
                                $serialNumber.StartsWith(
                                    [string]$_.PSChildName,
                                    [System.StringComparison]::OrdinalIgnoreCase
                                )
                            } |
                            Select-Object -First 1
                        if ($null -ne $usbInstance) {
                            $usbProperties = Get-ItemProperty -LiteralPath $usbInstance.PSPath -ErrorAction SilentlyContinue
                            $location = Get-SensorObjectProperty -Object $usbProperties `
                                -Name "LocationInformation" -Default $null
                        }
                    }
                }

                $hardwareId = "$rootName\$identityText\$($instanceKey.PSChildName)"
                $records += [pscustomobject]@{
                    port = $portName
                    vid = $usbVid
                    pid = $usbPid
                    serial_number = $serialNumber
                    manufacturer = ConvertFrom-SensorRegistryText (
                        Get-SensorObjectProperty -Object $properties -Name "Mfg" -Default $null
                    )
                    product = ConvertFrom-SensorRegistryText (
                        Get-SensorObjectProperty -Object $properties -Name "DeviceDesc" -Default $null
                    )
                    location = $location
                    hwid = $hardwareId
                }
            }
        }
    }
    return @($records)
}

function Get-SensorSerialPortInventory {
    $ports = @([System.IO.Ports.SerialPort]::GetPortNames())
    $registryRecords = @(Get-SensorRegistryPortInventory -ActivePorts $ports)
    $entities = @()
    try {
        $entities = @(Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop | Where-Object {
            ([string]$_.Name) -match '\((?<Port>COM\d+)\)'
        })
    }
    catch {
        # Port-name-only fallback still supports explicit-port configurations.
    }

    $inventory = @()
    foreach ($port in $ports) {
        $registryRecord = $registryRecords | Where-Object {
            ([string]$_.port).Equals($port, [System.StringComparison]::OrdinalIgnoreCase)
        } | Select-Object -First 1
        $entity = $entities | Where-Object {
            ([string]$_.Name) -match "\($([regex]::Escape($port))\)"
        } | Select-Object -First 1
        $hwid = [string](Get-SensorObjectProperty -Object $entity -Name "PNPDeviceID" -Default (
            Get-SensorObjectProperty -Object $registryRecord -Name "hwid" -Default ""
        ))
        $usbVid = Get-SensorObjectProperty -Object $registryRecord -Name "vid" -Default $null
        $usbPid = Get-SensorObjectProperty -Object $registryRecord -Name "pid" -Default $null
        if ($hwid -match '(?i)VID[_&+]([0-9A-F]{4})') {
            $usbVid = [Convert]::ToInt32($Matches[1], 16)
        }
        if ($hwid -match '(?i)PID[_&+]([0-9A-F]{4})') {
            $usbPid = [Convert]::ToInt32($Matches[1], 16)
        }

        $serialNumber = Get-SensorObjectProperty -Object $registryRecord `
            -Name "serial_number" -Default $null
        if ($null -eq $serialNumber -and $hwid -match '\\([^\\]+)$') {
            $candidate = $Matches[1]
            if ($candidate -notmatch '^\d+&') {
                $serialNumber = $candidate
            }
        }
        if ($null -eq $serialNumber -and $hwid -match '(?i)VID_[0-9A-F]{4}\+PID_[0-9A-F]{4}\+([^\\+]+)') {
            $serialNumber = $Matches[1]
        }

        $inventory += [pscustomobject]@{
            port = $port
            vid = $usbVid
            pid = $usbPid
            serial_number = $serialNumber
            manufacturer = Get-SensorObjectProperty -Object $entity -Name "Manufacturer" -Default (
                Get-SensorObjectProperty -Object $registryRecord -Name "manufacturer" -Default $null
            )
            product = Get-SensorObjectProperty -Object $entity -Name "Description" -Default (
                Get-SensorObjectProperty -Object $registryRecord -Name "product" -Default $null
            )
            location = Get-SensorObjectProperty -Object $entity -Name "LocationInformation" -Default (
                Get-SensorObjectProperty -Object $registryRecord -Name "location" -Default $null
            )
            hwid = $hwid
        }
    }
    return @($inventory | Sort-Object {
        if ($_.port -match '(?i)^COM(\d+)$') { [int]$Matches[1] } else { [int]::MaxValue }
    }, port)
}

function Test-SensorHasPortIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Device
    )

    $identity = Get-SensorObjectProperty -Object $Device -Name "port_identity" -Default $null
    if ($null -eq $identity) {
        return $false
    }
    foreach ($field in @("vid", "pid", "serial_number", "manufacturer", "product", "location", "hwid")) {
        if (
            $identity.PSObject.Properties.Name -contains $field -and
            $null -ne $identity.$field -and
            -not [string]::IsNullOrWhiteSpace([string]$identity.$field)
        ) {
            return $true
        }
    }
    return $false
}

function Resolve-SensorSerialPort {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Device,

        [object[]]$Inventory
    )

    $configuredPort = [string](Get-SensorObjectProperty -Object $Device -Name "port" -Default "")
    $usesAutoPort = (
        [string]::IsNullOrWhiteSpace($configuredPort) -or
        $configuredPort.Trim().ToLowerInvariant() -eq "auto"
    )
    $identity = Get-SensorObjectProperty -Object $Device -Name "port_identity" -Default $null
    $identityFields = @("vid", "pid", "serial_number", "manufacturer", "product", "location", "hwid")
    $criteriaCount = 0
    if ($null -ne $identity) {
        foreach ($field in $identityFields) {
            if (
                $identity.PSObject.Properties.Name -contains $field -and
                $null -ne $identity.$field -and
                -not [string]::IsNullOrWhiteSpace([string]$identity.$field)
            ) {
                $criteriaCount++
            }
        }
    }

    if ($usesAutoPort -and $criteriaCount -eq 0) {
        throw "Serial port 'auto' requires at least one port_identity field."
    }
    if (-not $usesAutoPort -and $criteriaCount -eq 0) {
        return $configuredPort
    }

    if ($null -eq $Inventory) {
        $Inventory = @(Get-SensorSerialPortInventory)
    }
    $matches = @($Inventory | Where-Object {
        $candidate = $_
        if (
            -not $usesAutoPort -and
            -not ([string]$candidate.port).Equals(
                $configuredPort,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        ) {
            return $false
        }

        foreach ($field in $identityFields) {
            if (
                -not ($identity.PSObject.Properties.Name -contains $field) -or
                $null -eq $identity.$field -or
                [string]::IsNullOrWhiteSpace([string]$identity.$field)
            ) {
                continue
            }

            $expected = $identity.$field
            $actual = Get-SensorObjectProperty -Object $candidate -Name $field -Default $null
            if ($field -in @("vid", "pid")) {
                if ($null -eq $actual -or [int]$actual -ne (ConvertTo-SensorUsbId -Value $expected)) {
                    return $false
                }
            }
            elseif (
                $null -eq $actual -or
                -not ([string]$actual).Equals(
                    [string]$expected,
                    [System.StringComparison]::OrdinalIgnoreCase
                )
            ) {
                return $false
            }
        }
        return $true
    })

    $selector = if ($usesAutoPort) { "auto" } else { $configuredPort }
    if ($matches.Count -eq 0) {
        $available = (@($Inventory | ForEach-Object { $_.port }) -join ", ")
        if ([string]::IsNullOrWhiteSpace($available)) { $available = "<none>" }
        throw "No serial port matched '$selector' and its port_identity. Available: $available"
    }
    if ($matches.Count -gt 1) {
        throw "Serial selector '$selector' matched multiple ports: $(@($matches.port) -join ', '). Add serial_number or location."
    }
    return [string]$matches[0].port
}

function Read-SensorConfiguration {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigPath
    )

    if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
        throw "ConfigPath is required. Pass the same sensors_config.json used by production."
    }

    $resolved = (Resolve-Path -LiteralPath $ConfigPath -ErrorAction Stop).Path
    try {
        $config = Get-Content -LiteralPath $resolved -Raw -ErrorAction Stop | ConvertFrom-Json
    }
    catch {
        throw "Cannot parse sensor configuration '$resolved': $($_.Exception.Message)"
    }

    if ($null -eq $config) {
        throw "Sensor configuration '$resolved' is empty."
    }
    return $config
}

function Write-SensorBackupLog {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("INFO", "WARN", "ERROR")]
        [string]$Level,

        [Parameter(Mandatory = $true)]
        [string]$Message,

        [string]$LogPath
    )

    $line = "{0} [{1}] {2}" -f (
        [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
    ), $Level, $Message

    if ($Level -eq "ERROR") {
        [Console]::Error.WriteLine($line)
    }
    elseif ($Level -eq "WARN") {
        Write-Warning $line
    }
    else {
        Write-Host $line
    }

    if (-not [string]::IsNullOrWhiteSpace($LogPath)) {
        Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    }
}

function New-SensorBackupMutex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Identity
    )

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Identity.ToLowerInvariant())
        $digest = [System.BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "")
    }
    finally {
        $sha.Dispose()
    }

    $mutex = New-Object System.Threading.Mutex($false, "Local\GlazingSensorBackup_$digest")
    $acquired = $false
    try {
        $acquired = $mutex.WaitOne(0)
    }
    catch [System.Threading.AbandonedMutexException] {
        $acquired = $true
    }

    if (-not $acquired) {
        $mutex.Dispose()
        throw "Another backup process is already running for '$Identity'."
    }
    return $mutex
}

function Close-SensorBackupMutex {
    param(
        [System.Threading.Mutex]$Mutex
    )

    if ($null -eq $Mutex) {
        return
    }
    try {
        $Mutex.ReleaseMutex()
    }
    catch {
        # The process still owns all files it created even if mutex cleanup fails.
    }
    $Mutex.Dispose()
}

function Write-AtomicUtf8File {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    $temporary = "$Path.partial.$([Guid]::NewGuid().ToString('N'))"
    try {
        [System.IO.File]::WriteAllText(
            $temporary,
            $Content,
            (New-Object System.Text.UTF8Encoding($false))
        )
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            $replaced = "$Path.replaced.$([Guid]::NewGuid().ToString('N'))"
            try {
                [System.IO.File]::Replace($temporary, $Path, $replaced)
            }
            finally {
                if (Test-Path -LiteralPath $replaced) {
                    Remove-Item -LiteralPath $replaced -Force
                }
            }
        }
        else {
            Move-Item -LiteralPath $temporary -Destination $Path -ErrorAction Stop
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Remove-ExpiredSensorBackups {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath,

        [int]$RetentionDays,

        [Parameter(Mandatory = $true)]
        [string[]]$Extensions
    )

    if ($RetentionDays -le 0 -or -not (Test-Path -LiteralPath $RootPath -PathType Container)) {
        return 0
    }

    $cutoff = [DateTime]::UtcNow.AddDays(-$RetentionDays)
    $removed = 0
    Get-ChildItem -LiteralPath $RootPath -Recurse -File | Where-Object {
        ($Extensions -contains $_.Extension.ToLowerInvariant()) -and
        ($_.CreationTimeUtc -lt $cutoff)
    } | ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Force
        $removed++
    }
    return $removed
}

function Resolve-JetiSourcePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfiguredPath,

        [Parameter(Mandatory = $true)]
        [string]$DataDirectory
    )

    if ([System.IO.Path]::IsPathRooted($ConfiguredPath)) {
        return [System.IO.Path]::GetFullPath($ConfiguredPath)
    }

    $relative = $ConfiguredPath
    $segments = $relative -split '[\\/]'
    if ($segments.Count -gt 1 -and $segments[0].ToLowerInvariant() -eq "data") {
        $relative = ($segments[1..($segments.Count - 1)] -join [System.IO.Path]::DirectorySeparatorChar)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $DataDirectory $relative))
}
