@echo off
rem Starts the Shortkaar server minimised, so Autopilot can make the daily
rem Shorts without you opening anything. To run it at every login, press
rem Win+R, type shell:startup, and put a shortcut to this file in that folder.
rem The dashboard itself still opens with start.bat (option 1 or 3).
cd /d "%~dp0"
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul && exit /b 0
if not exist output mkdir output
rem The log is a file, not a console: without UTF-8 every emoji the server
rem prints would fail on the Windows code page.
set PYTHONIOENCODING=utf-8
start "Shortkaar server" /min cmd /c ".venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 >> output\server.log 2>&1"
