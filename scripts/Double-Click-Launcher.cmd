@echo off
rem Double-click launcher for the production Control Center (#108).
rem Point a desktop shortcut at this file; see DEV-SETUP.md.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0control-center\Open-ControlCenter.ps1"
exit /b %ERRORLEVEL%
