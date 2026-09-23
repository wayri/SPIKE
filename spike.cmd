@echo off
setlocal
set "SPIKE_ROOT=%~dp0"
python -m python.spike_cli %*
exit /b %ERRORLEVEL%
