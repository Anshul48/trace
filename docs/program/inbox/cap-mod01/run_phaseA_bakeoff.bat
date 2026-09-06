@echo off
REM WP-CAP-MOD01: Phase A is SUPERSEDED by Phase B (see PHASE_B_FINALISTS_PLAN.md).
REM This redirector prevents accidental Phase A execution and runs Phase B instead.
REM Original Phase A batch script is preserved at run_phaseA_bakeoff.bat.archived.
setlocal
echo ===============================================================================
echo [NOTICE] Phase A has been SUPERSEDED by Phase B (see PHASE_B_FINALISTS_PLAN.md).
echo Automatically redirecting execution to active finalists bake-off:
echo   run_phaseB_bakeoff.bat
echo ===============================================================================
echo.
call "%~dp0run_phaseB_bakeoff.bat" %*
exit /b %ERRORLEVEL%
