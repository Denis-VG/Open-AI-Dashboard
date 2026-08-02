@echo off
call "%~dp0Scripts\activate.bat"
set "PYTHONPYCACHEPREFIX=%~dp0.pycache"
if not exist "%PYTHONPYCACHEPREFIX%" mkdir "%PYTHONPYCACHEPREFIX%"
python.exe "%~dp0dashboard\server.py"