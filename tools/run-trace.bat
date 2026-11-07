@echo off
rem run-trace.bat - Windows launcher for the TRACE interactive explorer.
rem Zero install beyond Python 3.8+: serves docs/ on localhost and opens the
rem explorer in your browser. Every argument is forwarded to run_explorer.py:
rem   run-trace.bat [--dataset 20k] [--port N] [--host ADDR] [--no-browser]
rem   run-trace.bat --download 10m
rem Exit code is run_explorer.py's exit code (0 ok, 1 error, 2 bad flags).
setlocal
cd /d "%~dp0.."
where py >nul 2>nul
if errorlevel 1 goto :trypython
py -3 run_explorer.py %*
exit /b %errorlevel%
:trypython
where python >nul 2>nul
if errorlevel 1 goto :nopython
python run_explorer.py %*
exit /b %errorlevel%
:nopython
echo run-trace: no Python 3 found - install Python 3.8+ from https://www.python.org/downloads/ and retry. 1>&2
exit /b 1
