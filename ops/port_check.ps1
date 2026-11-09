# Used by autostart.bat. Prints the name of the program listening on -Port
# when it is NOT the expected one (-Expect, e.g. python), and nothing when the
# port is free or ours. Docker Desktop starts at login and this repo's
# docker-compose.yml publishes 8000 with "restart: unless-stopped": a leftover
# container there made the old "is 8000 listening?" check skip the real server.
param([int]$Port = 8000, [string]$Expect = 'python')
$c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $c) { exit 0 }
$p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
if ($p -and $p.ProcessName -like "$Expect*") { exit 0 }
if ($p) { Write-Output $p.ProcessName } else { Write-Output "process $($c.OwningProcess)" }
exit 0
