@echo off
REM WP-CAP-MOD01 DeepSeek Flash V4 0731 Bake-Off via Sail Research API
REM Isolated detached runner: writes strictly to docs\program\inbox\cap-mod01-deepseek-flash\
REM Does NOT touch ongoing local Ollama runs.
setlocal
cd /d C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace || (echo [FAIL] repo path not found & pause & exit /b 1)

where python >nul 2>nul || (echo [FAIL] python not on PATH & pause & exit /b 1)

if not defined SAIL_API_KEY (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /r "^SAIL_API_KEY=" .env 2^>nul`) do set SAIL_API_KEY=%%B
)

if not defined SAIL_API_KEY (
  echo ======================================================================
  echo Sail Research API Key Required
  echo ======================================================================
  python benchmarks\enter_sail_key.py
  if errorlevel 1 (echo [FAIL] Key setup cancelled & pause & exit /b 1)
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /r "^SAIL_API_KEY=" .env 2^>nul`) do set SAIL_API_KEY=%%B
)

echo [1/3] Checking API key validity...
python benchmarks\run_deepseek_flash_bakeoff.py --check-key
if errorlevel 1 (echo [FAIL] Sail Research API key pre-flight check failed & pause & exit /b 1)

echo [2/3] Running DeepSeek Flash V4 0731 Bake-Off across 100 frozen clusters...
python benchmarks\run_deepseek_flash_bakeoff.py --manifest docs\program\inbox\cap-mod01\bakeoff_clusters_v1.json --clusters 100
if errorlevel 1 (echo [FAIL] Bake-off run crashed - check error output & pause & exit /b 1)

echo [3/3] Verifying receipt and artifacts...
python benchmarks\run_deepseek_flash_bakeoff.py --verify-receipt
if errorlevel 1 (echo [FAIL] Receipt did not verify & pause & exit /b 1)

echo ======================================================================
echo [DONE] DeepSeek Flash V4 0731 Bake-Off complete!
echo Artifacts stored in docs\program\inbox\cap-mod01-deepseek-flash\
echo ======================================================================
pause
