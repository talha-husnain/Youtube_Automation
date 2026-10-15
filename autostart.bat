@echo off
rem Starts Shortkaar minimised: the server (Autopilot makes, uploads and
rem checks the daily Shorts on its own) and the dashboard at
rem http://localhost:5180. A shortcut to this file in the Startup folder
rem (Win+R, shell:startup) runs it at every login. Each part is skipped when
rem it is already running.
cd /d "%~dp0"
if not exist output mkdir output
rem The logs are files, not a console: without UTF-8 every emoji the server
rem prints would fail on the Windows code page.
set PYTHONIOENCODING=utf-8
:check
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul || start "Shortkaar server" /min cmd /c ".venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 >> output\server.log 2>&1"
rem Port 5180, not Vite's usual 5173: another project of the owner's took 5173 (15-oct-2026)
rem and this check then skipped starting the dashboard altogether.
netstat -ano | findstr /r /c:":5180 .*LISTENING" >nul || start "Shortkaar dashboard" /min cmd /c "cd /d dashboard && npm run dev -- --host 127.0.0.1 --port 5180 --strictPort >> ..\output\dashboard.log 2>&1"
rem "autostart.bat watch" is the watchdog: it runs the checks above every
rem 5 minutes, so a server that stopped comes back without a new login.
if /i "%~1"=="watch" (
    timeout /t 300 /nobreak >nul
    goto check
)
rem One watchdog only: found by its command line ("tasklist /v" took 2 minutes here).
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"name='cmd.exe'\" | Where-Object { $_.CommandLine -like '*autostart.bat*watch*' }) { exit 0 } else { exit 1 }" >nul 2>&1 || start "Shortkaar watchdog" /min cmd /c ""%~f0" watch"
exit /b 0
