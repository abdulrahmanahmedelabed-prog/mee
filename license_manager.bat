@echo off
cd /d "%~dp0"
REM Developer only: issue activation keys for customers. Never give this file or the tools folder to customers.
python tools\license_manager.py
if errorlevel 1 pause
