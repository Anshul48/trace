@echo off
REM run-trace.bat — clone-and-run launcher for the TRACE interactive explorer.
REM Zero install beyond Python 3: serves docs\ on localhost, opens explorer.
REM Logic parity with tools\run-trace.sh (serve docs\, port fallback, open browser).
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

where python >nul 2>nul
if %errorlevel% neq 0 (
  echo run-trace: python not found on PATH - install Python 3.8+ and retry.
  exit /b 1
)

set PORT=8000
for /l %%p in (8000,1,8100) do (
  python -c "import socket; socket.create_connection(('127.0.0.1',%%p),timeout=1)" >nul 2>nul
  if !errorlevel! neq 0 (
    set PORT=%%p
    goto :serve
  )
)
:serve
set URL=http://127.0.0.1:%PORT%/explorer/
echo run-trace: serving docs\ at http://127.0.0.1:%PORT%/ (Ctrl+C to stop)
echo run-trace: opening explorer: %URL%
start "" "%URL%"
python -m http.server %PORT% --directory docs
