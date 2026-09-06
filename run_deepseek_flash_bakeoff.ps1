# WP-CAP-MOD01 DeepSeek Flash V4 0731 Bake-Off via Sail Research API (PowerShell)
# Isolated detached runner: writes strictly to docs/program/inbox/cap-mod01-deepseek-flash/
# Does NOT touch ongoing local Ollama runs.

$ErrorActionPreference = "Stop"
$RepoRoot = "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace"
Set-Location -Path $RepoRoot

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "TRACE-CAP-001: DeepSeek Flash V4 0731 Bake-Off (Sail Research)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$apiKey = $env:SAIL_API_KEY
if (-not $apiKey -and (Test-Path ".env")) {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^SAIL_API_KEY=(.+)$") {
            $apiKey = $matches[1].Trim().Trim("`"'")
        }
    }
}

if (-not $apiKey) {
    Write-Host "No SAIL_API_KEY found. Launching secure key setup..." -ForegroundColor Yellow
    python benchmarks\enter_sail_key.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ABORT] Key setup failed or was cancelled." -ForegroundColor Red
        exit 1
    }
}

Write-Host "`n[1/3] Checking Sail Research API credentials..." -ForegroundColor Yellow
python benchmarks\run_deepseek_flash_bakeoff.py --check-key
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Sail Research API key pre-flight check failed." -ForegroundColor Red
    exit 1
}

Write-Host "`n[2/3] Running DeepSeek Flash V4 0731 Bake-Off across 100 frozen clusters..." -ForegroundColor Yellow
python benchmarks\run_deepseek_flash_bakeoff.py --manifest docs\program\inbox\cap-mod01\bakeoff_clusters_v1.json --clusters 100
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Bake-off execution failed. Check logs above." -ForegroundColor Red
    exit 1
}

Write-Host "`n[3/3] Verifying receipt and artifacts..." -ForegroundColor Yellow
python benchmarks\run_deepseek_flash_bakeoff.py --verify-receipt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Receipt verification failed." -ForegroundColor Red
    exit 1
}

Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "[DONE] DeepSeek Flash V4 0731 Bake-Off completed and verified!" -ForegroundColor Green
Write-Host "Artifacts stored in: docs\program\inbox\cap-mod01-deepseek-flash\" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
