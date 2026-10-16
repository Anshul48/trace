# SPDX-License-Identifier: Apache-2.0
# TRACE: Isolated Local Engine Installer & Runner (20k Prefix)
# License: Apache-2.0
# Note: Windows native support is UNVERIFIED and UNSUPPORTED due to POSIX locking semantics
# in the frozen research engine. This script delegates to WSL/Linux automatically.

param(
    [switch]$Rerun = $false,
    [switch]$NoServer = $false,
    [int]$Port = 8765,
    [switch]$Native = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "TRACE Research Engine: Local Installer & Runner (20k Token Prefix)" -ForegroundColor Cyan
Write-Host "Candidate Sourcefreeze: 38c66bef (207 files immutable)" -ForegroundColor Cyan
Write-Host "Platform Note: Linux (Python 3.12) is the verified qualification platform." -ForegroundColor Cyan
Write-Host "Platform Status: Windows native environment is UNVERIFIED / UNSUPPORTED." -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan

# Validate port numeric 1..65535
if ($Port -lt 1 -or $Port -gt 65535) {
    Write-Error "Invalid port: $Port. Must be an integer between 1 and 65535."
    exit 1
}

# If user explicitly requests native Windows execution, reject with honest unsupported error
if ($Native) {
    Write-Error "Native Windows execution is unsupported: the frozen research engine relies on Linux/POSIX file locking semantics (flock). Please run under WSL or Linux."
    exit 1
}

# Delegate to WSL/Linux
$wsl = Get-Command "wsl" -ErrorAction SilentlyContinue
if ($wsl) {
    Write-Host "Delegating execution to WSL/Linux environment..." -ForegroundColor Green
    $argsList = @()
    if ($Rerun) { $argsList += "--rerun" }
    if ($NoServer) { $argsList += "--no-server" }
    if ($Port -ne 8765) { $argsList += "--port=$Port" }
    
    # Run bash wrapper inside WSL, quoting script dir path with spaces safely
    $wslPath = (& wsl wslpath -a "$ScriptDir").Trim()
    $cmd = "cd '$wslPath' && ./install_and_run.sh $($argsList -join ' ')"
    & wsl bash -c "$cmd"
    exit $LASTEXITCODE
} else {
    Write-Error "WSL (Windows Subsystem for Linux) is required on Windows systems because the frozen engine requires POSIX locking semantics. Please install WSL or run directly on Linux."
    exit 1
}
