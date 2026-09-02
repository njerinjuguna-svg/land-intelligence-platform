# ===========================================================================
# STOP WHATEVER IS HOLDING PORT 8000
# Land Intelligence Platform - Geocode Spatial Solutions Ltd
#
# Ctrl-C in the right window is the tidy way. This is for when you no longer
# know which window that is - which happens the moment you have started the
# API twice, and after a while every session has three terminals open.
#
# It stops the process LISTENING ON PORT 8000, whatever it is, rather than
# every python.exe on the machine. Killing all of those would take the ETL
# or an enrichment run down with it.
# ===========================================================================

$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue

if (-not $conns) {
    Write-Host "Nothing is listening on port 8000. The API is not running."
    exit 0
}

foreach ($pid_ in ($conns.OwningProcess | Select-Object -Unique)) {
    $p = Get-Process -Id $pid_ -ErrorAction SilentlyContinue
    if ($p) {
        Write-Host "Stopping $($p.ProcessName) (PID $pid_)"
        Stop-Process -Id $pid_ -Force
    }
}

Start-Sleep -Milliseconds 600

if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Port 8000 is STILL in use. Close the window running it by hand." -ForegroundColor Red
} else {
    Write-Host "Port 8000 is free. Start the API again with start_api.cmd" -ForegroundColor Green
}
