#Requires -Version 5.1
<#
collector.ps1 — build a diagnostic bundle per CONTRACT.md (contract v1).
Windows PowerShell port of collector.sh.

Dependency-free PowerShell. Runs on the sick client machine. Reads the targets
registered by setup.ps1 (collect.conf.json), captures system/network state,
tails the registered logs, copies the registered problem folder(s), and writes
a manifest.json describing every file in the bundle. The bundle lands in
outbox/ next to this script — which, when this folder lives on a USB stick,
means the bundle is already on the stick.

Never runs automatically. A human invokes it.

Usage: .\collector.ps1 [-Conf FILE] [-Outbox DIR]
  -Conf FILE     config file to use (default: collect.conf.json next to this script)
  -Outbox DIR    where to write the bundle (default: outbox\ next to this script)
#>
[CmdletBinding()]
param(
    [string]$Conf   = (Join-Path $PSScriptRoot 'collect.conf.json'),
    [string]$Outbox = (Join-Path $PSScriptRoot 'outbox')
)

$CollectorVersion = '0.1.0'
$ContractVersion  = '1'
$ErrorActionPreference = 'Continue'

if (-not (Test-Path -LiteralPath $Conf -PathType Leaf)) {
    Write-Error "config not found: $Conf`nRun .\setup.ps1 first to register your problem folder and log files."
    exit 1
}

$cfg = Get-Content -LiteralPath $Conf -Raw | ConvertFrom-Json
$ProblemDirs  = @($cfg.problem_dirs)  | Where-Object { $_ }
$LogFiles     = @($cfg.log_files)     | Where-Object { $_ }
$Services     = @($cfg.services)      | Where-Object { $_ }
$DocsDir      = [string]$cfg.docs_dir
$LogTailLines = if ($cfg.log_tail_lines) { [int]$cfg.log_tail_lines } else { 500 }
$MaxFileBytes = if ($cfg.max_file_bytes) { [long]$cfg.max_file_bytes } else { 5242880 }

# ---------------------------------------------------------------- helpers ---

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Write-TextFile([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, $script:Utf8NoBom)
}
function Add-TextFile([string]$Path, [string]$Content) {
    [System.IO.File]::AppendAllText($Path, $Content, $script:Utf8NoBom)
}

# Append delimited command output per contract: ### CMD: <label> ###
function Invoke-Capture([string]$OutFile, [string]$Label, [scriptblock]$Body) {
    $text = "### CMD: $Label ###`r`n"
    try {
        $out = (& $Body 2>&1 | Out-String).TrimEnd()
        if ($out) { $text += $out + "`r`n" }
    } catch [System.Management.Automation.CommandNotFoundException] {
        $text += "[command not available on this system]`r`n"
    } catch {
        $text += "[command failed: $($_.Exception.Message)]`r`n"
    }
    Add-TextFile $OutFile ($text + "`r`n")
}

function Add-Note([string]$Msg) { Add-TextFile (Join-Path $BundleDir 'NOTES.txt') ($Msg + "`r`n") }

# ---------------------------------------------------------------- prepare ---

$hostRaw = try { [System.Net.Dns]::GetHostName() } catch { 'unknown-host' }
$BundleHost = $hostRaw -replace '[^A-Za-z0-9._-]', '-'
$now       = [DateTime]::UtcNow
$Ts        = $now.ToString('yyyyMMddTHHmmssZ')
$CreatedAt = $now.ToString('yyyy-MM-ddTHH:mm:ssZ')
$OsDesc = try {
    $o = Get-CimInstance Win32_OperatingSystem
    "$($o.Caption) $($o.Version) $($o.OSArchitecture)".Trim()
} catch { [System.Environment]::OSVersion.VersionString }

$BundleName = "bundle-$BundleHost-$Ts"
$BundleDir  = Join-Path $Outbox $BundleName

if (Test-Path -LiteralPath $BundleDir) {
    Write-Error "$BundleDir already exists (two runs in one second?). Retry."
    exit 1
}
New-Item -ItemType Directory -Force -Path $BundleDir | Out-Null
Write-TextFile (Join-Path $BundleDir 'NOTES.txt') ''

Write-Host "==> Building $BundleName"
Write-Host "    collector v$CollectorVersion, contract v$ContractVersion"

# ------------------------------------------------------- system + network ---

Write-Host "==> Capturing system state (missing commands are noted, not fatal)"
$Sys = Join-Path $BundleDir 'system.txt'
Write-TextFile $Sys ''
Invoke-Capture $Sys 'systeminfo' { systeminfo }
Invoke-Capture $Sys 'uptime (last boot)' {
    $os = Get-CimInstance Win32_OperatingSystem
    "boot: $($os.LastBootUpTime)   now: $(Get-Date)   up: $((Get-Date) - $os.LastBootUpTime)"
}
Invoke-Capture $Sys 'disk usage (Win32_LogicalDisk)' {
    Get-CimInstance Win32_LogicalDisk |
        Select-Object DeviceID, VolumeName,
            @{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}},
            @{n='FreeGB';e={[math]::Round($_.FreeSpace/1GB,1)}} |
        Format-Table -AutoSize
}
Invoke-Capture $Sys 'memory (Win32_OperatingSystem)' {
    Get-CimInstance Win32_OperatingSystem |
        Select-Object @{n='TotalMB';e={[math]::Round($_.TotalVisibleMemorySize/1KB)}},
                      @{n='FreeMB'; e={[math]::Round($_.FreePhysicalMemory/1KB)}} |
        Format-Table -AutoSize
}
Invoke-Capture $Sys 'failed services (auto-start, not running)' {
    Get-CimInstance Win32_Service -Filter "StartMode='Auto' AND State<>'Running'" |
        Select-Object Name, DisplayName, State, Status | Format-Table -AutoSize
}
Invoke-Capture $Sys 'processes (Get-Process, top CPU)' {
    Get-Process | Sort-Object CPU -Descending |
        Select-Object Id, ProcessName, CPU,
            @{n='WS_MB';e={[math]::Round($_.WorkingSet64/1MB,1)}} |
        Format-Table -AutoSize
}

Write-Host "==> Capturing network state"
$Net = Join-Path $BundleDir 'network.txt'
Write-TextFile $Net ''
Invoke-Capture $Net 'ipconfig /all'   { ipconfig /all }
Invoke-Capture $Net 'route print'     { route print }
Invoke-Capture $Net 'netstat -ano'    { netstat -ano }
Invoke-Capture $Net 'listening TCP (Get-NetTCPConnection)' {
    Get-NetTCPConnection -State Listen |
        Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table -AutoSize
}
Invoke-Capture $Net 'DNS servers (Get-DnsClientServerAddress)' {
    Get-DnsClientServerAddress |
        Where-Object { $_.ServerAddresses } |
        Select-Object InterfaceAlias, AddressFamily,
            @{n='Servers';e={$_.ServerAddresses -join ', '}} |
        Format-Table -AutoSize
}
Invoke-Capture $Net 'netsh advfirewall show allprofiles' { netsh advfirewall show allprofiles }

# --------------------------------------------------------------- services ---

foreach ($svc in $Services) {
    Write-Host "==> Capturing service: $svc"
    $d = Join-Path (Join-Path $BundleDir 'services') $svc
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    $statusFile = Join-Path $d 'status.txt'
    Write-TextFile $statusFile ''
    Invoke-Capture $statusFile "Get-Service $svc" {
        Get-Service -Name $svc -ErrorAction Stop | Format-List Name, DisplayName, Status, StartType
    }
    Invoke-Capture $statusFile "sc.exe qc $svc" { sc.exe qc $svc }
    $journalFile = Join-Path $d 'journal.txt'
    Write-TextFile $journalFile ''
    Invoke-Capture $journalFile "System event log entries mentioning '$svc' (last 200 scanned)" {
        Get-WinEvent -LogName System -MaxEvents 200 -ErrorAction Stop |
            Where-Object { $_.Message -match [regex]::Escape($svc) } |
            Format-List TimeCreated, Id, LevelDisplayName, Message
    }
}

# --------------------------------------------------------------- app logs ---

$appLogs = Join-Path $BundleDir 'app_logs'
New-Item -ItemType Directory -Force -Path $appLogs | Out-Null
$Sources = Join-Path $appLogs 'SOURCES.txt'
Write-TextFile $Sources ''
$i = 0
foreach ($lf in $LogFiles) {
    $i++
    if (Test-Path -LiteralPath $lf -PathType Leaf) {
        $base = Split-Path -Leaf $lf
        $destRel = 'app_logs/{0:D2}-{1}' -f $i, $base
        $totalLines = (Get-Content -LiteralPath $lf | Measure-Object -Line).Lines
        $tail = Get-Content -LiteralPath $lf -Tail $LogTailLines
        Write-TextFile (Join-Path $BundleDir ($destRel -replace '/', '\')) (($tail -join "`r`n") + "`r`n")
        $truncated = 'no'
        if ($totalLines -gt $LogTailLines) { $truncated = 'yes' }
        Add-TextFile $Sources "$destRel <- $lf (source $totalLines lines, kept last $LogTailLines, truncated=$truncated)`r`n"
        Write-Host "==> Log captured: $lf ($totalLines lines, truncated=$truncated)"
    } else {
        Add-TextFile $Sources "MISSING <- $lf (not readable at collection time)`r`n"
        Add-Note "WARNING: registered log not readable: $lf"
        Write-Host "==> WARNING: log not readable, skipped: $lf"
    }
}

# ---------------------------------------------------------- problem dirs ----

$problemRoot = Join-Path $BundleDir 'problem'
New-Item -ItemType Directory -Force -Path $problemRoot | Out-Null
$Skipped = Join-Path $problemRoot 'SKIPPED.txt'
Write-TextFile $Skipped ''
foreach ($pd in $ProblemDirs) {
    $pd = $pd.TrimEnd('\', '/')
    if (-not (Test-Path -LiteralPath $pd -PathType Container)) {
        Add-Note "WARNING: registered problem dir missing: $pd"
        Write-Host "==> WARNING: problem dir missing, skipped: $pd"
        continue
    }
    $base = Split-Path -Leaf $pd
    Write-Host "==> Copying problem folder: $pd"
    $copied = 0
    foreach ($f in (Get-ChildItem -LiteralPath $pd -Recurse -File -Force)) {
        $rel = $f.FullName.Substring($pd.Length).TrimStart('\', '/')
        if ($f.Length -gt $MaxFileBytes) {
            Add-TextFile $Skipped "$pd\$rel ($($f.Length) bytes > cap $MaxFileBytes)`r`n"
            continue
        }
        $dest = Join-Path (Join-Path $problemRoot $base) $rel
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        Copy-Item -LiteralPath $f.FullName -Destination $dest
        $copied++
    }
    Write-Host "    $copied file(s) copied"
}

# ------------------------------------------------------------------- docs ---

if ($DocsDir) {
    if (Test-Path -LiteralPath $DocsDir -PathType Container) {
        Write-Host "==> Copying docs corpus: $DocsDir"
        $docsDest = Join-Path $BundleDir 'docs'
        New-Item -ItemType Directory -Force -Path $docsDest | Out-Null
        Copy-Item -Path (Join-Path $DocsDir '*') -Destination $docsDest -Recurse -Force
    } else {
        Add-Note "WARNING: registered docs dir missing: $DocsDir"
    }
}

# --------------------------------------------------------------- manifest ---

Write-Host "==> Generating manifest.json"

function Get-Kind([string]$rel) {
    switch -Regex ($rel) {
        '^system\.txt$'        { return 'system' }
        '^network\.txt$'       { return 'network' }
        '^NOTES\.txt$'         { return 'meta' }
        '^app_logs/SOURCES\.txt$' { return 'meta' }
        '^app_logs/'           { return 'log' }
        '^services/'           { return 'service' }
        '^problem/SKIPPED\.txt$' { return 'meta' }
        '^problem/'            { return 'problem' }
        '^docs/'               { return 'knowledge' }
        default                { return 'other' }
    }
}

$bundleRootLen = (Get-Item -LiteralPath $BundleDir).FullName.Length
$entries = @()
$totalBytes = [long]0
foreach ($f in (Get-ChildItem -LiteralPath $BundleDir -Recurse -File -Force | Sort-Object FullName)) {
    $rel = $f.FullName.Substring($bundleRootLen).TrimStart('\').Replace('\', '/')
    if ($rel -eq 'manifest.json') { continue }
    $hash = try { (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLower() } catch { '' }
    $entries += [ordered]@{
        path   = $rel
        bytes  = [long]$f.Length
        sha256 = $hash
        kind   = Get-Kind $rel
    }
    $totalBytes += $f.Length
}

$countsByKind = [ordered]@{}
foreach ($g in ($entries | Group-Object { $_.kind } | Sort-Object Name)) {
    $countsByKind[$g.Name] = $g.Count
}

$manifest = [ordered]@{
    contract_version  = $ContractVersion
    collector_version = $CollectorVersion
    bundle            = $BundleName
    hostname          = $BundleHost
    created_at_utc    = $CreatedAt
    os                = $OsDesc
    targets           = [ordered]@{
        problem_dirs = @($ProblemDirs)
        log_files    = @($LogFiles)
        docs_dir     = $DocsDir
        services     = @($Services)
    }
    log_tail_lines = $LogTailLines
    file_count     = $entries.Count
    total_bytes    = $totalBytes
    counts_by_kind = $countsByKind
    files          = @($entries)
}

# UTF-8 WITHOUT BOM — receive_bundle.py parses this with strict utf-8.
Write-TextFile (Join-Path $BundleDir 'manifest.json') ((ConvertTo-Json -InputObject $manifest -Depth 6) + "`n")

# ---------------------------------------------------------------- summary ---

Write-Host ""
Write-Host "=============================================================="
Write-Host " Bundle ready: $BundleDir"
Write-Host "   files: $($entries.Count)   total: $totalBytes bytes"
Write-Host ""
Write-Host " Next step (USB mode): eject this drive, plug it into the"
Write-Host " workstation (Brain), and run:"
Write-Host "   python receive_bundle.py <path-to-this-outbox>"
Write-Host ""
Write-Host " Next step (SSH mode): from the Brain, run pull.ps1 against"
Write-Host " this machine; it fetches manifest.json first, then the bundle."
Write-Host "=============================================================="
