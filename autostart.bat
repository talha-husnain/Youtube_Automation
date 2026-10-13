@echo off
rem Starts Shortkaar minimised: the server (Autopilot makes, uploads and
rem checks the daily Shorts on its own) and the dashboard at
rem http://localhost:5173. A shortcut to this file in the Startup folder
rem (Win+R, shell:startup) runs it at every login. Each part is skipped when
rem it is already running.
cd /d "%~dp0"
if not exist output mkdir output
rem The logs are files, not a console: without UTF-8 every emoji the server
rem prints would fail on the Windows code page.
set PYTHONIOENCODING=utf-8
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul || start "Shortkaar server" /min cmd /c ".venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 >> output\server.log 2>&1"
netstat -ano | findstr /r /c:":5173 .*LISTENING" >nul || start "Shortkaar dashboard" /min cmd /c "cd /d dashboard && npm run dev -- --host 127.0.0.1 --port 5173 >> ..\output\dashboard.log 2>&1"
exit /b 0
