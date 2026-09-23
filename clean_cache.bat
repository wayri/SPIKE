@echo off
echo ========================================
echo   SPIKE Plugin Cache Cleaner
echo ========================================
echo.

set PLUGIN_DIR=%USERPROFILE%\Documents\KiCad\9.0\3rdparty\plugins\SPIKE

echo Cleaning Python cache...

if exist "%PLUGIN_DIR%\__pycache__" (
    echo Removing __pycache__...
    rmdir /S /Q "%PLUGIN_DIR%\__pycache__"
    echo   [OK] Cache removed
) else (
    echo   [INFO] No cache found
)

if exist "%PLUGIN_DIR%\*.pyc" (
    echo Removing .pyc files...
    del /Q "%PLUGIN_DIR%\*.pyc"
    echo   [OK] .pyc files removed
)

echo.
echo ========================================
echo   Cache Cleaned!
echo ========================================
echo.
echo Next steps:
echo   1. Close KiCad COMPLETELY
echo   2. Wait 5 seconds
echo   3. Restart KiCad
echo   4. Open a PCB and check plugin version
echo.
pause
