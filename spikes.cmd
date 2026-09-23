@echo off
setlocal
set "SPIKES_ROOT=%~dp0"
pushd "%SPIKES_ROOT%" >nul
if errorlevel 1 exit /b 1
python -m python.spikes %*
set "SPIKES_EXIT=%ERRORLEVEL%"
popd
exit /b %SPIKES_EXIT%
