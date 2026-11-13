@echo off
REM ============================================================
REM  register_task.bat
REM  Registers a Windows Scheduled Task that runs the
REM  Currency Exchange Rate daily updater every day at 06:00.
REM
REM  Run this file once from any Command Prompt or File Explorer
REM  double-click. Administrator privileges are NOT required.
REM
REM  To remove the task later:
REM      schtasks /delete /tn "CurrencyTrackerDailyUpdate" /f
REM
REM  To view task status:
REM      schtasks /query /tn "CurrencyTrackerDailyUpdate" /fo list /v
REM ============================================================

setlocal

REM --- Resolve project directory dynamically from batch file's own location ---
set "SCRIPT_DIR=%~dp0"
set "UPDATER_SCRIPT=%SCRIPT_DIR%daily_rate_updater.py"
set "TASK_NAME=CurrencyTrackerDailyUpdate"
set "TASK_TIME=06:00"

REM --- Detect Python interpreter dynamically (prioritizing project virtual environments) ---
set "PYTHON_EXE="

REM 1. Check for local virtual environment (.venv or venv) in project directory
if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%venv\Scripts\python.exe"
) else (
    REM 2. Look for installed python in system PATH, filtering out WindowsApps store alias
    for /f "usebackq delims=" %%I in (`where python 2^>nul`) do (
        if not defined PYTHON_EXE (
            echo "%%I" | findstr /i "WindowsApps" >nul
            if errorlevel 1 (
                set "PYTHON_EXE=%%I"
            )
        )
    )
    REM 3. Fallback to first python found in PATH if none selected
    if not defined PYTHON_EXE (
        for /f "usebackq delims=" %%I in (`where python 2^>nul`) do (
            if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
        )
    )
    REM 4. Fallback to py.exe launcher if python is not in PATH
    if not defined PYTHON_EXE (
        for /f "usebackq delims=" %%I in (`where py 2^>nul`) do (
            if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
        )
    )
)

REM --- Verify python executable was found ---
if not defined PYTHON_EXE (
    echo [ERROR] Python was not found in your system PATH or project virtual environment.
    echo Please install Python 3 or ensure python.exe is added to your PATH environment variable.
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python path resolved but executable does not exist: %PYTHON_EXE%
    pause
    exit /b 1
)

REM --- Verify updater script exists ---
if not exist "%UPDATER_SCRIPT%" (
    echo [ERROR] Updater script not found at: %UPDATER_SCRIPT%
    echo Make sure daily_rate_updater.py is in the same folder as this batch file.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Currency Exchange Tracker — Daily Rate Updater Scheduler
echo ============================================================
echo.
echo Project Dir : %SCRIPT_DIR%
echo Python Path : %PYTHON_EXE%
echo Script Path : %UPDATER_SCRIPT%
echo Task Name   : %TASK_NAME%
echo Schedule    : Daily at %TASK_TIME%
echo.

REM --- Register (or overwrite) the scheduled task using /f ---
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /sc daily ^
    /st %TASK_TIME% ^
    /tr "\"%PYTHON_EXE%\" \"%UPDATER_SCRIPT%\"" ^
    /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Task "%TASK_NAME%" registered successfully.
    echo      It will run every day at %TASK_TIME%.
    echo.
    echo      Logs are written to: %SCRIPT_DIR%updater.log
    echo.
    echo      To run the updater right now manually:
    echo      schtasks /run /tn "%TASK_NAME%"
    echo.
    echo      To remove this task:
    echo      schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo.
    echo [ERROR] Task registration failed. Error code: %ERRORLEVEL%
    echo         Try running this file as Administrator if the error persists.
)

endlocal
pause
