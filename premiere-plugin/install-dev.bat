@echo off
rem Double-click to install the plugin for testing. Pass -Uninstall to remove it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-dev.ps1" %*
echo.
pause
