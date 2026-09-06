@echo off
REM Phase B: finalists-only bake-off (gemma4:26b + qwen3.8:27b, schema-on, resume).
REM Local-only. Teacher ABSENT. See PHASE_B_FINALISTS_PLAN.md.
REM Order: fast model (26B MoE, ~1h left) first, then 27B dense (~6h, overnight OK).
REM Live status: python -u streams per-cluster scores; progress.json updates live.
setlocal
set PYTHONUNBUFFERED=1

if exist "%~dp0..\..\..\..\benchmarks\run_model_bakeoff.py" (
    cd /d "%~dp0..\..\..\.."
) else (
    cd /d C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace || (echo [FAIL] repo path not found & pause & exit /b 1)
)

where python >nul 2>nul || (echo [FAIL] python not on PATH & pause & exit /b 1)
ollama --version >nul 2>nul || (echo [FAIL] ollama CLI not found - install/start Ollama first & pause & exit /b 1)
curl.exe -s -m 8 http://127.0.0.1:11434/api/tags >nul 2>nul || (echo [FAIL] Ollama not serving on 127.0.0.1:11434 - start the Ollama app first & pause & exit /b 1)

echo ===============================================================================
echo [1/5] PREFLIGHT: finalist weights only (gemma4:26b, qwen3.8:27b):
echo ===============================================================================
ollama list
set MISSING=
for %%M in (gemma4:26b qwen3.8:27b) do (
  ollama list | findstr /i /c:"%%M" >nul || (echo [MISSING] %%M & set MISSING=1)
)
if defined MISSING (echo [FAIL] restore the exact missing tag above, then re-run. Do NOT substitute. & pause & exit /b 1)

set MANIFEST=docs\program\inbox\cap-mod01\bakeoff_clusters_v1.json
set CKPT=docs\program\inbox\cap-mod01\bakeoff_checkpoint.json
set BACKUP=docs\program\inbox\cap-mod01\bakeoff_checkpoint.pre-schema-baseline.json

echo.
echo ===============================================================================
echo [2/5] BASELINE BACKUP (keeps pre-schema clusters as honest split):
echo ===============================================================================
if not exist "%BACKUP%" (
  if exist "%CKPT%" (
    copy "%CKPT%" "%BACKUP%" >nul || (echo [FAIL] could not back up checkpoint & pause & exit /b 1)
    echo [OK] backed up to %BACKUP%
  ) else (
    echo [INFO] Fresh start from cluster 0 - no pre-existing checkpoint
  )
) else (
  echo [OK] backup already exists, keeping it.
)

echo.
echo ===============================================================================
echo [3/5] STEP 1/2: gemma4:26b (clusters 0-99, resume skips cached; live per-cluster scores):
echo Progress also streams to docs\program\inbox\cap-mod01\progress.json
echo ===============================================================================
python -u benchmarks\run_model_bakeoff.py --manifest %MANIFEST% --model gemma4:26b --cluster-start 0 --cluster-end 100 --resume
if errorlevel 1 (echo [FAIL] gemma4:26b run failed - paste traceback back & pause & exit /b 1)

echo.
echo ===============================================================================
echo [4/5] STEP 2/2: qwen3.8:27b (clusters 0-99, resume skips cached; live per-cluster scores):
echo ===============================================================================
python -u benchmarks\run_model_bakeoff.py --manifest %MANIFEST% --model qwen3.8:27b --cluster-start 0 --cluster-end 100 --resume
if errorlevel 1 (echo [FAIL] qwen3.8:27b run failed - paste traceback back & pause & exit /b 1)

echo.
echo ===============================================================================
echo [5/5] VERIFICATION (must exit 0):
echo ===============================================================================
python -u benchmarks\run_model_bakeoff.py --manifest %MANIFEST% --verify-receipt
if errorlevel 1 (echo [FAIL] receipt did not verify - paste every error line back & pause & exit /b 1)

echo.
echo ===============================================================================
echo [DONE] Phase B complete. Paste back: per-model coverage, fail-closed point
echo + 95%% CI + width, conditional grounding, invalid rate, warm tok/s,
echo P95 latency, wall time, $0.00 spend, champion + rationale, verify output.
echo ===============================================================================
pause
