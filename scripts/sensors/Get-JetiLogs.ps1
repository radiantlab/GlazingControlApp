#requires -Version 5.1

<#
.SYNOPSIS
Incrementally backs up an active JETI LiVal capture file.

.DESCRIPTION
Reads the line-oriented LiVal capture file while LiVal is still writing it.
Only complete rows appended since the previous run are written to a new,
immutable backup chunk. Cursor state under DataDirectory makes scheduled daily
runs incremental and restart-safe.

The source suffix is irrelevant. A LiVal capture named .xlsx is capture text,
not necessarily an Excel workbook.

On the first run, all existing complete rows are backed up. Later runs copy only
new complete rows. Source data is never modified, renamed, or deleted.

.PARAMETER SourceFile
Exact path to the active LiVal capture file.

.PARAMETER DataDirectory
Destination directory for backup chunks, cursor state, and operational logs.

.NOTES
Exit codes: 0 success or no new rows, 2 invocation/backup error,
5 another copy is already running.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceFile,

    [Parameter(Mandatory = $true)]
    [string]$DataDirectory
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Get-SensorSafeName {
    param([Parameter(Mandatory = $true)][string]$Value)

    $safe = [regex]::Replace($Value.Trim(), '[^A-Za-z0-9._-]', '_')
    if ([string]::IsNullOrWhiteSpace($safe)) {
        return "unknown"
    }
    return $safe
}

function Write-SensorBackupLog {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("INFO", "ERROR")]
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
    else {
        Write-Host $line
    }
    if (-not [string]::IsNullOrWhiteSpace($LogPath)) {
        Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    }
}

function New-JetiBackupMutex {
    param([Parameter(Mandatory = $true)][string]$Identity)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes(
            $Identity.ToLowerInvariant()
        )
        $digest = [System.BitConverter]::ToString(
            $sha.ComputeHash($bytes)
        ).Replace("-", "")
    }
    finally {
        $sha.Dispose()
    }

    $mutex = New-Object System.Threading.Mutex(
        $false,
        "Local\GlazingJetiBackup_$digest"
    )
    try {
        if (-not $mutex.WaitOne(0)) {
            $mutex.Dispose()
            throw "Another JETI backup is already running."
        }
    }
    catch [System.Threading.AbandonedMutexException] {
        # An abandoned mutex is acquired by the current process.
    }
    return $mutex
}

function Close-JetiBackupMutex {
    param([System.Threading.Mutex]$Mutex)

    if ($null -eq $Mutex) {
        return
    }
    try {
        $Mutex.ReleaseMutex()
    }
    catch {
        # Process exit still releases the mutex.
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
            Move-Item -LiteralPath $temporary -Destination $Path `
                -ErrorAction Stop
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Get-JetiBackupIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath
    )

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes(
            $SourcePath.ToLowerInvariant()
        )
        return [System.BitConverter]::ToString(
            $sha.ComputeHash($bytes)
        ).Replace("-", "").Substring(0, 12).ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Write-JetiBackupCursor {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$SourcePath,

        [Parameter(Mandatory = $true)]
        [string]$SourceCreationUtc,

        [Parameter(Mandatory = $true)]
        [long]$Offset
    )

    $cursor = [ordered]@{
        version = 1
        source_path = $SourcePath
        source_creation_utc = $SourceCreationUtc
        offset = $Offset
        updated_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    Write-AtomicUtf8File -Path $Path -Content ($cursor | ConvertTo-Json)
}

function Backup-JetiCaptureDelta {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationRoot
    )

    $sourceInfo = Get-Item -LiteralPath $SourcePath -ErrorAction Stop
    $safeBase = Get-SensorSafeName -Value $sourceInfo.BaseName
    $identity = Get-JetiBackupIdentity -SourcePath $SourcePath
    $stateDirectory = Join-Path $DestinationRoot ".state"
    $statePath = Join-Path $stateDirectory (
        "{0}-{1}.cursor.json" -f $safeBase, $identity
    )
    $sourceCreationUtc = $sourceInfo.CreationTimeUtc.ToString("o")
    $offset = [long]0

    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        try {
            $state = Get-Content -LiteralPath $statePath -Raw -ErrorAction Stop |
                ConvertFrom-Json
            if (
                [string]$state.source_path -eq $SourcePath -and
                [string]$state.source_creation_utc -eq $sourceCreationUtc
            ) {
                $offset = [long]$state.offset
            }
        }
        catch {
            throw "Cannot read JETI backup cursor '$statePath': $($_.Exception.Message)"
        }
    }

    $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    $stream = [System.IO.FileStream]::new(
        $SourcePath,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        $share
    )
    try {
        $snapshotLength = [long]$stream.Length
        if ($offset -lt 0 -or $offset -gt $snapshotLength) {
            $offset = [long]0
        }

        $available = $snapshotLength - $offset
        if ($available -eq 0) {
            return [pscustomobject]@{
                Status = "unchanged"
                Path = $null
                StartOffset = $offset
                EndOffset = $offset
                Bytes = 0
            }
        }
        if ($available -gt [int]::MaxValue) {
            throw "JETI backup exceeds the 2 GiB per-run safety limit."
        }

        [void]$stream.Seek($offset, [System.IO.SeekOrigin]::Begin)
        $buffer = New-Object byte[] ([int]$available)
        $totalRead = 0
        while ($totalRead -lt $buffer.Length) {
            $read = $stream.Read($buffer, $totalRead, $buffer.Length - $totalRead)
            if ($read -eq 0) {
                break
            }
            $totalRead += $read
        }

        $lastNewline = -1
        for ($index = $totalRead - 1; $index -ge 0; $index--) {
            if ($buffer[$index] -eq 10) {
                $lastNewline = $index
                break
            }
        }
        if ($lastNewline -lt 0) {
            return [pscustomobject]@{
                Status = "incomplete"
                Path = $null
                StartOffset = $offset
                EndOffset = $offset
                Bytes = 0
            }
        }

        $completeLength = $lastNewline + 1
        $endOffset = $offset + $completeLength
        $completeBytes = New-Object byte[] $completeLength
        [Array]::Copy($buffer, 0, $completeBytes, 0, $completeLength)

        $backupName = (
            "{0}-{1}-bytes-{2:D12}-{3:D12}.capture.txt" -f
            $safeBase,
            [DateTime]::UtcNow.ToString("yyyyMMdd"),
            $offset,
            $endOffset
        )
        $backupFile = Join-Path $DestinationRoot $backupName
        if (Test-Path -LiteralPath $backupFile -PathType Leaf) {
            if ((Get-Item -LiteralPath $backupFile).Length -ne $completeLength) {
                throw "Existing JETI backup chunk has an unexpected size: $backupFile"
            }
        }
        else {
            $temporary = "$backupFile.partial.$([Guid]::NewGuid().ToString('N'))"
            try {
                [System.IO.File]::WriteAllBytes($temporary, $completeBytes)
                Move-Item -LiteralPath $temporary -Destination $backupFile `
                    -ErrorAction Stop
            }
            finally {
                if (Test-Path -LiteralPath $temporary) {
                    Remove-Item -LiteralPath $temporary -Force
                }
            }
        }

        Write-JetiBackupCursor -Path $statePath -SourcePath $SourcePath `
            -SourceCreationUtc $sourceCreationUtc -Offset $endOffset

        return [pscustomobject]@{
            Status = "copied"
            Path = $backupFile
            StartOffset = $offset
            EndOffset = $endOffset
            Bytes = $completeLength
        }
    }
    finally {
        $stream.Dispose()
    }
}

$mutex = $null
$logPath = $null
try {
    $resolvedSource = (Resolve-Path -LiteralPath $SourceFile -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath $resolvedSource -PathType Leaf)) {
        throw "LiVal SourceFile must be a file: $resolvedSource"
    }

    if (-not (Test-Path -LiteralPath $DataDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $DataDirectory -Force | Out-Null
    }
    $resolvedData = (Resolve-Path -LiteralPath $DataDirectory).Path
    $logPath = Join-Path $resolvedData (
        "Get-JetiLogs-{0}.log" -f [DateTime]::UtcNow.ToString("yyyyMMdd")
    )

    try {
        $mutex = New-JetiBackupMutex -Identity (
            "jeti-lival|{0}|{1}" -f $resolvedSource, $resolvedData
        )
    }
    catch {
        Write-SensorBackupLog -Level ERROR -Message $_.Exception.Message `
            -LogPath $logPath
        exit 5
    }

    Write-SensorBackupLog -Level INFO -Message (
        "Incremental LiVal backup: source={0}, data-directory={1}" -f
        $resolvedSource, $resolvedData
    ) -LogPath $logPath

    $result = Backup-JetiCaptureDelta -SourcePath $resolvedSource `
        -DestinationRoot $resolvedData
    if ($result.Status -eq "copied") {
        Write-SensorBackupLog -Level INFO -Message (
            "Backed up {0} new bytes ({1}..{2}) -> {3}" -f
            $result.Bytes, $result.StartOffset, $result.EndOffset, $result.Path
        ) -LogPath $logPath
    }
    elseif ($result.Status -eq "incomplete") {
        Write-SensorBackupLog -Level INFO -Message (
            "No complete new LiVal row is available; cursor was unchanged."
        ) -LogPath $logPath
    }
    else {
        Write-SensorBackupLog -Level INFO -Message (
            "LiVal capture is unchanged at byte {0}." -f $result.EndOffset
        ) -LogPath $logPath
    }
    exit 0
}
catch {
    if ($logPath) {
        Write-SensorBackupLog -Level ERROR -Message $_.Exception.Message `
            -LogPath $logPath
    }
    else {
        [Console]::Error.WriteLine($_.Exception.Message)
    }
    exit 2
}
finally {
    Close-JetiBackupMutex -Mutex $mutex
}
