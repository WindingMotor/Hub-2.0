@echo off
setlocal
if defined SIMULATION_PYTHON (
    "%SIMULATION_PYTHON%" "%~dp0run.py" %*
    goto finished
)
for %%V in (3.12 3.13 3.11) do (
    py -%%V -c "import sys; sys.exit(not ((3,11) <= sys.version_info[:2] <= (3,13)))" >nul 2>&1
    if not errorlevel 1 (
        py -%%V "%~dp0run.py" %*
        goto finished
    )
)
python -c "import sys; sys.exit(not ((3,11) <= sys.version_info[:2] <= (3,13)))" >nul 2>&1
if not errorlevel 1 (
    python "%~dp0run.py" %*
    goto finished
)
echo Install Python 3.12 with the Python launcher, or set SIMULATION_PYTHON.
exit /b 2
:finished
set "simulation_exit=%errorlevel%"
if not "%simulation_exit%"=="0" (
    echo Simulation exited with code %simulation_exit%.
    pause
)
exit /b %simulation_exit%
