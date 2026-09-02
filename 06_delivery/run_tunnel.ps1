# ===========================================================================
# PUT THE WIDGET ON THE PUBLIC INTERNET                   (Stage 0, window 2)
# Land Intelligence Platform - Geocode Spatial Solutions Ltd
#
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File "E:\Land Intelligence Platform Geocode\Land Intelligence Platform\06_delivery\run_tunnel.ps1"
#
# run_api.ps1 must already be running in another window.
#
# WHY --protocol http2
#   The first tunnel ran on QUIC (UDP) and dropped every few minutes with
#   "timeout: no recent network activity", reconnecting each time. That is
#   UDP being throttled or lost on the local network, not a fault in the
#   tunnel - but each drop is a few seconds where a client's page shows
#   nothing. HTTP/2 runs over TCP and survives the same conditions.
#
# THE HOSTNAME CHANGES EVERY RUN
#   A quick tunnel is anonymous and ephemeral by design. That is right for
#   demos and testing, and wrong for a client, who needs a stable address.
#   For that, DEPLOY.md's Stage 0 section covers the named tunnel on
#   embed.geocode.co.ke - which requires moving the domain's nameservers to
#   Cloudflare, so do it on a day when briefly disturbing the Netlify site is
#   acceptable.
#
# WHILE THIS RUNS, YOUR LAPTOP IS REACHABLE FROM THE INTERNET.
#   Ctrl-C when you are done testing. The API key is what scopes access, so
#   a key that has been shared anywhere should be revoked before this starts.
# ===========================================================================

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$exe = Join-Path $here "cloudflared.exe"

# Nothing on this machine has been reliable on PATH - createdb was missing
# while psql worked, python answers with a Store stub. So the binary lives
# beside this script and is fetched if absent.
if (-not (Test-Path $exe)) {
    Write-Host "cloudflared.exe not here - downloading it (about 30 MB)..."
    try {
        Invoke-WebRequest -UseBasicParsing `
            -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
            -OutFile $exe
    } catch {
        Write-Host "Download failed: $_" -ForegroundColor Red
        exit 1
    }
}

# Fail early and clearly if the API is not up, rather than handing out a
# public URL that answers 502 to everyone who tries it.
try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 `
            -Uri "http://127.0.0.1:8000/v1/health"
    Write-Host "API is up: $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host "THE API IS NOT RUNNING on http://127.0.0.1:8000" -ForegroundColor Red
    Write-Host "Start it first, in another window:" -ForegroundColor Red
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$here\run_api.ps1`"" -ForegroundColor Red
    exit 1
}

Write-Host "`nStarting the tunnel. Watch for the boxed https://...trycloudflare.com URL."
Write-Host "Ctrl-C closes it and takes your laptop back off the internet.`n"

& $exe tunnel --protocol http2 --url http://127.0.0.1:8000
