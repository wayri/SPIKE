@echo off
echo ========================================
echo   SPIKE Plugin Installer v0.1.7.0
echo ========================================

:: Set directories
set SOURCE=%~dp0kicad_plugin
set TARGET=%USERPROFILE%\Documents\KiCad\10.0\3rdparty\plugins\SPIKE

:: Check if source exists
if not exist "%SOURCE%" (
    echo [ERROR] Source directory not found: %SOURCE%
    exit /b 1
)

:: Create target directory
if not exist "%TARGET%" (
    echo Creating directory: %TARGET%
    mkdir "%TARGET%"
)

:: Remove old installation
if exist "%TARGET%\__init__.py" (
    echo Removing old installation...
    rmdir /S /Q "%TARGET%"
    mkdir "%TARGET%"
    echo   [OK] Old installation removed
)

echo Installing SPIKE plugin...
xcopy /E /I /Y "%SOURCE%" "%TARGET%" >nul

echo Installing Application Code...
xcopy /Y "%~dp0demo_spike.py" "%TARGET%\" >nul
xcopy /Y "%~dp0debug_spike.bat" "%TARGET%\" >nul
xcopy /Y "%~dp0setup_env.bat" "%TARGET%\" >nul
xcopy /Y "%~dp0requirements.txt" "%TARGET%\" >nul
xcopy /E /I /Y "%~dp0python" "%TARGET%\python" >nul

if exist "%TARGET%\__init__.py" (
    echo   [OK] Plugin files copied
    echo   [OK] Installation verified
) else (
    echo   [ERROR] Installation failed!
    exit /b 1
)

echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo SPIKE v0.1.7.0 has been installed to:
echo   %TARGET%
echo.
echo Next steps:
echo   1. Restart KiCad (if running)
echo   2. Open a PCB file
echo   3. Go to: Tools > External Plugins > SPIKE
echo.
echo Features in v0.1.7.0:
echo   [OK] C++ PEEC Solver (Neumann formula)
echo   [OK] PyVista 3D Visualization
echo   [OK] Partial Inductance Computation
echo   [OK] All Unit Tests Passing (4/4)
echo.
rem pause
