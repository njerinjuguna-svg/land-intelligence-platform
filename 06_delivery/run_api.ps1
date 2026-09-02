# ===========================================================================
# START THE WIDGET API                                    (Stage 0, window 1)
# Land Intelligence Platform - Geocode Spatial Solutions Ltd
#
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File "E:\Land Intelligence Platform Geocode\Land Intelligence Platform\06_delivery\run_api.ps1"
#
# Leave it running. Ctrl-C stops it.
# ===========================================================================

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$py = Join-Path $here "..\03_etl\venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No venv at $py" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $here ".env"))) {
    Write-Host "No 06_delivery\.env - the API would fall back to the ETL's" -ForegroundColor Red
    Write-Host "superuser credentials and refuse to start. Copy .env.example" -ForegroundColor Red
    Write-Host "to .env and point it at landiq_api." -ForegroundColor Red
    exit 1
}

# Is one already running? Windows reports a busy port as "only one usage of
# each socket address is normally permitted", which is true and unhelpful.
# The useful answer is almost always "you already started it in another
# window" - and if it IS ours, starting a second is not just unnecessary, it
# would fail after printing a successful-looking startup banner.
try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 `
            -Uri "http://127.0.0.1:8000/v1/health"
    Write-Host "THE API IS ALREADY RUNNING on port 8000." -ForegroundColor Yellow
    Write-Host "  $($r.Content)"
    Write-Host "`nIt is in another window. If that is what you wanted, go" -ForegroundColor Yellow
    Write-Host "straight to start_tunnel.cmd - there is nothing to do here." -ForegroundColor Yellow
    Write-Host "" -ForegroundColor Yellow
    Write-Host "TO PICK UP A CHANGED .env OR CHANGED CODE you must restart it:" -ForegroundColor Yellow
    Write-Host "  double-click stop_api.cmd, then start_api.cmd" -ForegroundColor Yellow
    Write-Host "" -ForegroundColor Yellow
    Write-Host "The API reads its configuration once, at startup. A new" -ForegroundColor Yellow
    Write-Host "GOOGLE_MAPS_KEY in a file it has already read changes nothing." -ForegroundColor Yellow
    exit 0
} catch {
    # Not running, or running and unhealthy. Either way, carry on and let
    # uvicorn give the real reason.
}

Write-Host "Starting the embed API on http://127.0.0.1:8000"
Write-Host "Expect: connected as 'landiq_api' (not a superuser)`n"

# The venv's python, called directly - nothing needs to be on PATH.
& $py -m uvicorn api_01_embed:app --port 8000
