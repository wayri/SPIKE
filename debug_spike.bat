@echo off
echo ========================================
echo   SPIKE GUI Debug Launcher
echo ========================================

:: Check for local Python environment
set VENV_PYTHON=%~dp0.venv\Scripts\python.exe

if not exist "%VENV_PYTHON%" (
    echo [INFO] Local Python environment not found.
    echo Running setup_env.bat...
    call "%~dp0setup_env.bat"
    
    if errorlevel 1 goto :ERROR
)

echo.
echo Launching GUI using local venv...
echo Python: %VENV_PYTHON%
echo.

"%VENV_PYTHON%" demo_spike.py

if errorlevel 1 (
    :ERROR
    echo.
    echo [ERROR] Launch Failed!
    echo Check the messages above for details.
    pause
) else (
    echo.
    echo [SUCCESS] Application closed normally.
    pause
)
