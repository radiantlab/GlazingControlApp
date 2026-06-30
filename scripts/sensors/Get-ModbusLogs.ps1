<#
.SYNOPSIS
    Downloads all files from /var/log/modbus on an FTP data logger to a local folder.

.DESCRIPTION
    Uses curl.exe (built into Windows 11) rather than ftp.exe or Invoke-WebRequest,
    because curl handles FTP LIST/RETR more predictably and gives clear exit codes
    per file. Requires plain anonymous-free FTP auth (user:pass), as confirmed
    working in your ftp.exe test.

.PARAMETER FtpHost
    IP or hostname of the data logger. Defaults to 192.168.40.50

.PARAMETER Username
    FTP username. Deafults to admin.

.PARAMETER Password
    FTP password. Defaults to admin. If omitted, you will be prompted (not echoed to screen).

.PARAMETER RemotePath
    Remote directory to mirror. Defaults to /var/log/modbus.

.PARAMETER LocalPath
    Local destination directory. Created if it does not exist.

.EXAMPLE
    .\Get-ModbusLogs.ps1 -Username svc_ftp -LocalPath C:\Logs\modbus

.NOTES
    - Explicitly calls curl.exe (not the PowerShell 5.1 alias for Invoke-WebRequest).
    - Skips directory entries when parsing the LIST output (lines starting with 'd').
    - Existing local files with the same name are overwritten.
#>

[CmdletBinding()]
param(
    [string]$FtpHost = "192.168.40.50",
    [string]$Username = "admin",
    [securestring]$Password = (ConvertTo-SecureString "admin" -AsPlainText -Force),
    [string]$RemotePath = "/var/log/modbus",
    [string]$LocalPath = ".\modbus_logs"
)

$ErrorActionPreference = "Stop"

function ConvertTo-FtpAbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $normalizedPath = $Path.Replace('\', '/').TrimEnd('/')
    if (-not $normalizedPath.StartsWith('/')) {
        $normalizedPath = "/$normalizedPath"
    }

    $segments = $normalizedPath.TrimStart('/').Split('/', [System.StringSplitOptions]::RemoveEmptyEntries)
    $escapedSegments = foreach ($segment in $segments) {
        [System.Uri]::EscapeDataString($segment)
    }

    # curl FTP URLs use a path relative to the login directory by default.
    # Encoding the leading slash makes this an absolute server path, like ftp.exe "cd /path".
    if ($escapedSegments.Count -eq 0) {
        return "%2F"
    }

    return "%2F$($escapedSegments -join '/')"
}

# Confirm curl.exe (the real one) is present, not just the IWR alias.
$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if (-not $curl) {
    throw "curl.exe not found. It ships with Windows 11 by default (System32\curl.exe) — check PATH."
}

if (-not $Password) {
    $Password = Read-Host -Prompt "FTP password for $Username" -AsSecureString
}
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
$plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

$userArg = "${Username}:${plainPassword}"
$remotePathForUrl = ConvertTo-FtpAbsolutePath -Path $RemotePath
$remoteDirUrl = "ftp://$FtpHost/$remotePathForUrl/"

if (-not (Test-Path -LiteralPath $LocalPath)) {
    New-Item -ItemType Directory -Path $LocalPath -Force | Out-Null
}

Write-Host "Listing $remoteDirUrl ..."
$listingRaw = & $curl.Source -s --user $userArg $remoteDirUrl
if ($LASTEXITCODE -ne 0) {
    throw "curl LIST failed against $remoteDirUrl (exit code $LASTEXITCODE). Check path/credentials."
}

if (-not $listingRaw) {
    Write-Warning "Directory listing came back empty. Nothing to download."
    return
}

# Parse standard Unix-style LIST output. Skip directory entries (leading 'd')
# and anything that doesn't look like a regular file line.
$files = @()
foreach ($line in $listingRaw -split "`r?`n") {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line.StartsWith("d")) { continue }   # subdirectory, not a file
    if ($line.StartsWith("l")) { continue }   # symlink, skip unless you want it followed
    $name = ($line -split '\s+', 9)[-1]
    if ($name) { $files += $name }
}

if ($files.Count -eq 0) {
    Write-Warning "No regular files parsed out of the listing. Raw output below for inspection:"
    Write-Host $listingRaw
    return
}

Write-Host "Found $($files.Count) file(s). Downloading to $LocalPath ..."

$failed = @()
foreach ($name in $files) {
    $remoteUrl = "$remoteDirUrl$([System.Uri]::EscapeDataString($name))"
    $localFile = Join-Path $LocalPath $name
    Write-Host "  -> $name"
    & $curl.Source -s --user $userArg -o "$localFile" "$remoteUrl"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "     FAILED (curl exit $LASTEXITCODE): $name"
        $failed += $name
    }
}

if ($failed.Count -gt 0) {
    Write-Warning "$($failed.Count) of $($files.Count) file(s) failed: $($failed -join ', ')"
} else {
    Write-Host "All $($files.Count) file(s) downloaded successfully to $LocalPath"
}
