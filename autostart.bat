@echo off
rem Starts Shortkaar minimised: the server (Autopilot makes, uploads and
rem checks the daily Shorts on its own) and the dashboard at
rem http://localhost:5180. A shortcut to this file in the Startup folder
rem (Win+R, shell:startup) runs it at every login. Each part is skipped when
rem it is already running.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
if not exist output mkdir output
rem The logs are files, not a console: without UTF-8 every emoji the server
rem prints would fail on the Windows code page.
set PYTHONIOENCODING=utf-8
rem Unbuffered: server.log shows what happens as it happens, not in 8 KB lumps.
set PYTHONUNBUFFERED=1
set "MODE=%~1"
set /a misses=0

:check
call :port_state 8000 python
if "!port!"=="free" call :start_server
if "!port!"=="ours" set /a misses=0
if "!port!"=="taken" call :port_taken 8000
rem Port 5180, not Vite's usual 5173: another project of the owner's took 5173 (15-oct-2026)
rem and this check then skipped starting the dashboard altogether.
call :port_state 5180 node
if "!port!"=="free" call :start_dashboard
rem "autostart.bat watch" is the watchdog: it runs the checks above every
rem 5 minutes, so a server that stopped comes back without a new login.
if /i "%MODE%"=="watch" (
    timeout /t 300 /nobreak >nul
    goto check
)
rem One watchdog only: found by its command line ("tasklist /v" took 2 minutes here).
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"name='cmd.exe'\" | Where-Object { $_.CommandLine -like '*autostart.bat*watch*' }) { exit 0 } else { exit 1 }" >nul 2>&1 || start "Shortkaar watchdog" /min cmd /c ""%~f0" watch"
exit /b 0

rem port = free (nothing listens), ours (the expected program does) or taken
rem (another program, e.g. a Docker container from docker-compose.yml, which
rem publishes 8000 with restart: unless-stopped). netstat decides free/listening
rem as before; ops\port_check.ps1 only tells ours from taken, and when it
rem cannot run the port counts as ours (the old behaviour).
:port_state
set "port=ours"
set "owner="
netstat -ano | findstr /r /c:":%~1 .*LISTENING" >nul || (set "port=free" & exit /b 0)
for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -File "ops\port_check.ps1" -Port %~1 -Expect %~2 2^>nul`) do set "owner=%%A"
if defined owner set "port=taken"
exit /b 0

:start_server
rem server.log is appended to forever; start a fresh one past 50 MB (only here,
rem when no server holds it open).
call :rotate "output\server.log" 52428800
rem In watch mode the server tells the owner it had stopped, once it is up: restart_notice.py
if /i "%MODE%"=="watch" (
    set /a misses+=1
    >>output\watchdog.log echo %date% %time% server not answering on 8000, starting it - check !misses! in a row
    set "SHORTKAAR_RESTART=watchdog"
)
start "Shortkaar server" /min cmd /c ".venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 >> output\server.log 2>&1"
set "SHORTKAAR_RESTART="
rem Three checks in a row (~15 min) and still nothing: it cannot start (an
rem import error, a broken venv), so the server's own notice never comes.
if /i "%MODE%"=="watch" if !misses! GEQ 3 (
    .venv\Scripts\python.exe restart_notice.py down !misses! >>output\watchdog.log 2>&1
)
exit /b 0

:port_taken
>>output\watchdog.log echo %date% %time% port %~1 is held by !owner!, Shortkaar's server cannot start
.venv\Scripts\python.exe restart_notice.py taken !owner! >>output\watchdog.log 2>&1
exit /b 0

:start_dashboard
call :rotate "output\dashboard.log" 10485760
if /i "%MODE%"=="watch" >>output\watchdog.log echo %date% %time% dashboard not answering on 5180, starting it
start "Shortkaar dashboard" /min cmd /c "cd /d dashboard && npm run dev -- --host 127.0.0.1 --port 5180 --strictPort >> ..\output\dashboard.log 2>&1"
exit /b 0

:rotate
rem A missing file has no size: the comparison would read empty and be a syntax error.
if not exist "%~1" exit /b 0
if %~z1 GTR %~2 move /y "%~1" "%~1.1" >nul 2>&1
exit /b 0
