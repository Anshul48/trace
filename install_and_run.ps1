# SPDX-License-Identifier: Apache-2.0
# TRACE: Isolated Local Engine Installer & Runner (20k Prefix)
# License: Apache-2.0
# Note: Verified on Linux via install_and_run.sh. This PowerShell script provides
# the equivalent automation for Windows environments. Zero deletions; preserves all runs.

param(
    [switch]$Rerun = $false,
    [switch]$NoServer = $false,
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "TRACE Research Engine: Local Installer & Runner (20k Token Prefix)" -ForegroundColor Cyan
Write-Host "Candidate Sourcefreeze: 38c66bef (207 files immutable)" -ForegroundColor Cyan
Write-Host "Platform Note: Linux (Python 3.12) is the verified qualification platform." -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Environment Verification (Python >= 3.11 per pyproject.toml)
Write-Host "`n[1/7] Checking Python runtime (floor: 3.11, verified: 3.12)..." -ForegroundColor Yellow
$Py = ""
foreach ($candidate in @("python3.12", "python3.11", "python3", "python")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        $ver = & $candidate -c 'import sys; v=sys.version_info; print("OK" if (v.major==3 and v.minor>=11) else "NO")'
        if ($ver -eq "OK") {
            $Py = $candidate
            Write-Host "  Found suitable Python: $Py" -ForegroundColor Green
            break
        }
    }
}

if (-not $Py) {
    Write-Error "Python >= 3.11 required (Python 3.12 verified baseline). Please install Python 3.11 or 3.12."
    exit 1
}

# 2. Virtual Environment Setup (.trace-demo-env; preserve existing .venv)
$EnvDir = Join-Path $ScriptDir ".trace-demo-env"
$PyBin = Join-Path $EnvDir "Scripts\python.exe"
if (-not (Test-Path $PyBin)) {
    $PyBin = Join-Path $EnvDir "bin/python"
}

Write-Host "`n[2/7] Preparing isolated virtual environment in .trace-demo-env..." -ForegroundColor Yellow
if (-not (Test-Path $EnvDir)) {
    $uv = Get-Command "uv" -ErrorAction SilentlyContinue
    if ($uv) {
        Write-Host "  Creating venv with uv..."
        & uv venv --python $Py $EnvDir
    } else {
        Write-Host "  Creating venv with $Py..."
        & $Py -m venv $EnvDir
    }
}

# 3. Installing Dependencies (numpy, blake3)
Write-Host "`n[3/7] Installing minimal dependencies (numpy, blake3)..." -ForegroundColor Yellow
$uv = Get-Command "uv" -ErrorAction SilentlyContinue
if ($uv) {
    & uv pip install --python $PyBin numpy blake3
} else {
    & $PyBin -m pip install numpy blake3
}

# 4. Source Integrity Check
Write-Host "`n[4/7] Verifying 207 immutable source files against SOURCEFREEZE..." -ForegroundColor Yellow
& $PyBin (Join-Path "tools" "verify_freeze.py")

# 5. Small-Scale Real Prefix Verification
Write-Host "`n[5/7] Verifying 20k token prefix data..." -ForegroundColor Yellow
$DataDir = Join-Path $ScriptDir (Join-Path "repro-20k" "data-20k")
if (-not (Test-Path $DataDir)) {
    $TarPath = Join-Path $ScriptDir (Join-Path "repro-20k" "small-prefix-20k.tar.gz")
    Write-Host "  Unpacking repro-20k/small-prefix-20k.tar.gz..."
    & $PyBin (Join-Path "repro-20k" "prep_small_prefix.py") unpack --tar $TarPath --data-dir $DataDir
}
& $PyBin (Join-Path "repro-20k" "prep_small_prefix.py") verify --tokens 20000 --cand (Join-Path "freeze-src" "cand") --data-dir $DataDir

# 6. Execute Frozen Product Pilot on 20k Prefix (Preserve all runs, NO deletions)
$RunsDir = Join-Path $ScriptDir "local-runs"
if (-not (Test-Path $RunsDir)) {
    New-Item -ItemType Directory -Path $RunsDir | Out-Null
}
$ActivePointer = Join-Path $RunsDir "current_run.json"

Write-Host "`n[6/7] Resolving 20k pilot run (all prior runs preserved)..." -ForegroundColor Yellow

$ActiveRunDir = ""
if ((-not $Rerun) -and (Test-Path $ActivePointer)) {
    $candidate = & $PyBin -c 'import json, sys, os
try:
    d = json.load(open(sys.argv[1]))
    p = d.get("active_run")
    if p and os.path.isdir(p):
        res = json.load(open(os.path.join(p, "result.json")))
        if res.get("status") == "PASS":
            print(p)
except Exception:
    pass' $ActivePointer

    if ($candidate) {
        $ActiveRunDir = $candidate
        Write-Host "  Reusing verified existing 20k run in: $ActiveRunDir" -ForegroundColor Green
    }
}

if ((-not $ActiveRunDir) -and (-not $Rerun)) {
    $legacy = Join-Path $ScriptDir "local-run-20k"
    $legacyRes = Join-Path $legacy "result.json"
    if (Test-Path $legacyRes) {
        $ok = & $PyBin -c 'import json, sys
try:
    res = json.load(open(sys.argv[1]))
    print("OK" if res.get("status") == "PASS" else "NO")
except Exception:
    print("NO")' $legacyRes
        if ($ok -eq "OK") {
            $ActiveRunDir = $legacy
            Write-Host "  Found verified existing 20k run in: $ActiveRunDir" -ForegroundColor Green
        }
    }
}

if ((-not $ActiveRunDir) -or $Rerun) {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $NewRunDir = Join-Path $RunsDir "run-$timestamp"
    Write-Host "  Creating new unique run directory: $NewRunDir" -ForegroundColor Yellow

    Write-Host "  Executing frozen harness product_pilot.py against data-20k..."
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $CandDir = Join-Path $ScriptDir (Join-Path "freeze-src" "cand")
    $p1 = Join-Path $CandDir (Join-Path "fork" "tl-sys")
    $p2 = Join-Path $CandDir (Join-Path "fork" "tl-candidate-batch\candidate")
    $p3 = Join-Path $CandDir "tools"
    $env:PYTHONPATH = "$p1;$p2;$p3"

    $Harness = Join-Path $CandDir (Join-Path "tools" "product_pilot.py")
    & $PyBin -B $Harness --tokens 20000 --profile local --out $NewRunDir --source-root $CandDir --data-dir $DataDir

    $resultJson = Join-Path $NewRunDir "result.json"
    $verdict = & $PyBin -c 'import json, sys; print(json.load(open(sys.argv[1]))["status"])' $resultJson
    if ($verdict -ne "PASS") {
        Write-Error "Pilot run finished with status: $verdict"
        exit 1
    }
    Write-Host "  Pilot execution completed with verdict: PASS" -ForegroundColor Green
    $ActiveRunDir = $NewRunDir

    & $PyBin -c 'import json, sys, time
run_dir, pointer, ledger = sys.argv[1], sys.argv[2], sys.argv[3]
rec = {"active_run": run_dir, "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "status": "PASS"}
json.dump(rec, open(pointer, "w"), indent=2)
open(ledger, "a").write(json.dumps(rec) + "\n")' $ActiveRunDir $ActivePointer (Join-Path $RunsDir "runs.jsonl")
}

# Export run data for explorer
Write-Host "  Exporting run topology and queries for explorer from $ActiveRunDir..."
& $PyBin (Join-Path "tools" "export_20k_viewer.py") --run-dir $ActiveRunDir

# 7. Launch Local Demonstration Server
Write-Host "`n[7/7] Launching local explorer server..." -ForegroundColor Yellow
if ($NoServer) {
    Write-Host "  Skipping server start (-NoServer)."
    Write-Host "  Installation and 20k pilot run verified successfully!" -ForegroundColor Green
    exit 0
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "TRACE Engine Ready! Open in your browser:" -ForegroundColor Green
Write-Host "http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan
& $PyBin (Join-Path "tools" "serve_local.py") --run-dir $ActiveRunDir --port $Port
