@echo off
echo ========================================
echo   SPIKE Dependency Manager v0.1.7.0
echo ========================================
echo.

:: Define local environment
set VENV_DIR=%~dp0.venv
set REQ_FILE=%~dp0requirements.txt

:: 1. LOCATE COMPATIBLE PYTHON (3.12)
echo [1/3] Locating Python 3.12...

:: Check vcpkg python first (preferred as it matches build)
set PYTHON_EXE=C:\vcpkg\installed\x64-windows\tools\python3\python.exe
if exist "%PYTHON_EXE%" goto :FOUND_PYTHON

:: Check standard install via py launcher
py -3.12 --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_EXE=py -3.12
    goto :FOUND_PYTHON
)

:: Check if default python is 3.12
python --version 2>&1 | findstr "3.12" >nul
if %ERRORLEVEL% equ 0 (
    set PYTHON_EXE=python
    goto :FOUND_PYTHON
)

echo [ERROR] Python 3.12 is required but not found!
echo Please install Python 3.12 or ensure vcpkg is configured.
pause
exit /b 1

:FOUND_PYTHON
echo   [OK] Using: %PYTHON_EXE%

:: 2. CREATE VIRTUAL ENVIRONMENT
echo.
echo [2/3] Creating local environment (.venv)...
if not exist "%VENV_DIR%" (
    "%PYTHON_EXE%" -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo   [OK] Environment created.
) else (
    echo   [OK] Environment exists.
)

:: 3. INSTALL DEPENDENCIES
echo.
echo [3/3] Installing dependencies...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >nul
"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%REQ_FILE%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo You can now launch the GUI.
pause
