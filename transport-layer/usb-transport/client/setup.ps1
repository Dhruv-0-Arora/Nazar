#Requires -Version 5.1
<#
setup.ps1 — register what to collect from this (sick) client machine.
Windows PowerShell port of setup.sh.

Super-simple CLI: asks which problem/working folder(s) to track, which log
file(s) to tail, optionally a docs corpus dir and Windows service names.
Writes collect.conf.json next to this script, then (optionally) runs
collector.ps1 to build the bundle + manifest immediately.

Nothing here runs automatically on USB plug-in. The FDE copies this folder
to the client laptop (or runs it straight off the stick) and invokes it.

Interactive:      .\setup.ps1
Non-interactive:  .\setup.ps1 -ProblemDir C:\path\to\problems -Log C:\logs\backend.log -Run

  -ProblemDir DIR...  folder(s) to register — the working folder of problems,
                      configs, broken app, etc. (comma-separate for several)
  -Log FILE...        log file(s) to track
  -DocsDir DIR        company-docs corpus directory (optional)
  -Service NAME...    Windows service(s) to capture
  -Tail N             keep last N lines of each log (default 500)
  -Run                run collector.ps1 immediately after writing config
  -NoRun              write config only
#>
[CmdletBinding()]
param(
    [string[]]$ProblemDir = @(),
    [string[]]$Log        = @(),
    [string]$DocsDir      = '',
    [string[]]$Service    = @(),
    [int]$Tail            = 500,
    [switch]$Run,
    [switch]$NoRun
)

$SetupVersion = '0.1.0'
$ErrorActionPreference = 'Stop'
$ConfPath = Join-Path $PSScriptRoot 'collect.conf.json'
$MaxFileBytes = 5242880

$interactive = ($PSBoundParameters.Count -eq 0)

Write-Host "=============================================================="
Write-Host " FDE War-Room Client Setup v$SetupVersion (PowerShell)"
Write-Host " Registers what this machine will hand to the Brain."
Write-Host "=============================================================="

if ($interactive) {
    Write-Host ""
    Write-Host "Which folder(s) hold the problem — the broken app, its configs,"
    Write-Host "its working directory? (blank line to finish)"
    while ($true) {
        $p = Read-Host '  problem folder path'
        if (-not $p) { break }
        if (Test-Path -LiteralPath $p -PathType Container) { $ProblemDir += $p }
        else { Write-Host '  !! not a directory, try again' }
    }

    Write-Host ""
    Write-Host "Which log file(s) should be tracked? (blank line to finish)"
    while ($true) {
        $p = Read-Host '  log file path'
        if (-not $p) { break }
        if (Test-Path -LiteralPath $p -PathType Leaf) { $Log += $p }
        else { Write-Host '  !! not a file, try again' }
    }

    Write-Host ""
    $DocsDir = Read-Host 'Company-docs corpus dir (optional, blank to skip)'

    Write-Host ""
    Write-Host "Windows service names to capture, e.g. 'Spooler' (blank to finish):"
    while ($true) {
        $p = Read-Host '  service name'
        if (-not $p) { break }
        $Service += $p
    }
}

if ($ProblemDir.Count -eq 0 -and $Log.Count -eq 0) {
    Write-Error 'nothing registered — need at least one problem folder or log file.'
    exit 1
}

# Resolve everything to absolute paths so collector.ps1 works from any cwd.
$resolvedDirs = @()
foreach ($p in $ProblemDir) {
    $a = Resolve-Path -LiteralPath $p -ErrorAction SilentlyContinue
    if (-not $a) { Write-Error "cannot resolve dir: $p"; exit 1 }
    $resolvedDirs += $a.Path
}
$resolvedLogs = @()
foreach ($p in $Log) {
    $a = Resolve-Path -LiteralPath $p -ErrorAction SilentlyContinue
    if (-not $a -or -not (Test-Path -LiteralPath $a.Path -PathType Leaf)) {
        Write-Error "log file not found: $p"; exit 1
    }
    $resolvedLogs += $a.Path
}
if ($DocsDir) {
    $a = Resolve-Path -LiteralPath $DocsDir -ErrorAction SilentlyContinue
    if (-not $a) { Write-Error "docs dir not found: $DocsDir"; exit 1 }
    $DocsDir = $a.Path
}

# ------------------------------------------------------------ write conf ----

$conf = [ordered]@{
    generated_by   = "setup.ps1 v$SetupVersion"
    generated_at   = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    problem_dirs   = @($resolvedDirs)
    log_files      = @($resolvedLogs)
    services       = @($Service)
    docs_dir       = $DocsDir
    log_tail_lines = $Tail
    max_file_bytes = $MaxFileBytes
}
$json = (ConvertTo-Json -InputObject $conf -Depth 4) + "`n"
[System.IO.File]::WriteAllText($ConfPath, $json, (New-Object System.Text.UTF8Encoding($false)))

Write-Host ""
Write-Host "Registered targets written to: $ConfPath"
Write-Host "  problem folders: $($resolvedDirs.Count)"
Write-Host "  log files:       $($resolvedLogs.Count)"
Write-Host "  services:        $($Service.Count)"
if ($DocsDir) { Write-Host "  docs corpus:     $DocsDir" } else { Write-Host "  docs corpus:     <none>" }

# ------------------------------------------------------------ run collector -

$runAfter = ''
if ($Run)   { $runAfter = 'yes' }
if ($NoRun) { $runAfter = 'no' }

if (-not $runAfter -and $interactive) {
    Write-Host ""
    $ans = Read-Host 'Run collection now and build the bundle + manifest? [Y/n]'
    if (-not $ans -or $ans -match '^[Yy]') { $runAfter = 'yes' } else { $runAfter = 'no' }
}

if ($runAfter -eq 'yes') {
    Write-Host ""
    & (Join-Path $PSScriptRoot 'collector.ps1') -Conf $ConfPath
    exit $LASTEXITCODE
} else {
    Write-Host ""
    Write-Host 'Config saved. Build the bundle any time with:  .\collector.ps1'
}
