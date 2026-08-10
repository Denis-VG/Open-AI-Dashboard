@echo off
call "%~dp0Scripts\activate.bat"
rem Set up a separate folder for compiled Python files to keep your source code clutter-free.
set "PYTHONPYCACHEPREFIX=%~dp0.pycache"
if not exist "%PYTHONPYCACHEPREFIX%" mkdir "%PYTHONPYCACHEPREFIX%"
python.exe "%~dp0dashboard\server.py"
