@echo off
setlocal

echo [Trace OS] Finding available ports...

python -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" > "%TEMP%\port1.txt"
set /p BACKEND_PORT=<"%TEMP%\port1.txt"
del "%TEMP%\port1.txt"

python -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" > "%TEMP%\port2.txt"
set /p FRONTEND_PORT=<"%TEMP%\port2.txt"
del "%TEMP%\port2.txt"

echo [Trace OS] Backend Port: %BACKEND_PORT%
echo [Trace OS] Frontend Port: %FRONTEND_PORT%

set VITE_API_URL=http://localhost:%BACKEND_PORT%

echo [Trace OS] Starting Backend API in background...
start /B uv run uvicorn main_api:app --host 0.0.0.0 --port %BACKEND_PORT% --reload

echo [Trace OS] Starting Frontend UI...
echo [Trace OS] Open http://localhost:%FRONTEND_PORT% in your browser.
cd frontend
npm run dev -- --port %FRONTEND_PORT%

endlocal
