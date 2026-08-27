# ===========================================================================
# E10 - REBUILD THE DATABASE FROM THE NUMBERED FILES ALONE, THEN COMPARE
# Land Intelligence Platform - Geocode Spatial Solutions Ltd
#
# Creates a scratch database, replays every file in 01_database into it in
# order, and reports which files could not replay. Then schema_diff.py
# compares that scratch database against the live one.
#
# The scratch database is DROPPED AND RECREATED each run. The name is checked
# against the live name first, so this cannot be pointed at real data.
#
# Reads the password from 03_etl\.env so psql does not prompt thirteen times.
#
# RUN:
#   powershell -ExecutionPolicy Bypass -File .\rebuild_check.ps1
# ===========================================================================

$ErrorActionPreference = "Continue"

$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $here "..\03_etl\.env"

if (-not (Test-Path $envFile)) { Write-Host "No .env at $envFile" -ForegroundColor Red; exit 1 }

$cfg = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $cfg[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
    }
}

$DBUSER  = if ($cfg['DB_USER']) { $cfg['DB_USER'] } else { 'postgres' }
$DBHOST  = if ($cfg['DB_HOST']) { $cfg['DB_HOST'] } else { 'localhost' }
$DBPORT  = if ($cfg['DB_PORT']) { $cfg['DB_PORT'] } else { '5432' }
$LIVE    = if ($cfg['DB_NAME']) { $cfg['DB_NAME'] } else { 'land_intelligence_kenya' }
$CHECK   = 'land_intelligence_rebuild_check'

if (-not $cfg['DB_PASSWORD']) { Write-Host "DB_PASSWORD not set in .env" -ForegroundColor Red; exit 1 }
$env:PGPASSWORD = $cfg['DB_PASSWORD']

# A control, not a comment. This script drops a database.
if ($CHECK -eq $LIVE) { Write-Host "REFUSING: scratch name equals live name." -ForegroundColor Red; exit 1 }

# psql is on PATH (createdb was not), so every step goes through psql.
function Psql-Cmd($db, $sql) {
    & psql -U $DBUSER -h $DBHOST -p $DBPORT -d $db -v ON_ERROR_STOP=1 -c $sql 2>&1 | Out-String
}

Write-Host "=========================================================================="
Write-Host "E10 REBUILD CHECK"
Write-Host "   live    : $LIVE"
Write-Host "   scratch : $CHECK   (dropped and recreated now)"
Write-Host "=========================================================================="

Write-Host "`n-- dropping and creating the scratch database"
Psql-Cmd "postgres" "DROP DATABASE IF EXISTS $CHECK;"       | Write-Host
Psql-Cmd "postgres" "CREATE DATABASE $CHECK;"               | Write-Host
if ($LASTEXITCODE -ne 0) { Write-Host "Could not create $CHECK - stopping." -ForegroundColor Red; exit 1 }

# postgis ONLY. The first run of this script also created postgis_raster, and
# the diff then showed public.raster_columns / raster_overviews as EXTRA IN
# REBUILT - the scratch database had something live does not.
#
# That is worth recording rather than just deleting: THE LIVE DATABASE HAS NO
# RASTER EXTENSION. Rasters are files on disk, cataloged in
# metadata.raster_catalog by path and sampled with rasterio. Nothing raster
# ever enters Postgres. A serving machine therefore needs neither the
# extension nor a single one of those files.
Write-Host "-- extensions"
Psql-Cmd $CHECK "CREATE EXTENSION IF NOT EXISTS postgis;" | Write-Host

# Order matters. The base dump first, then every migration by number.
$files = @(
    "land_intelligence_schema.sql",
    "02_schema_update_v1.1.sql",
    "03_schema_update_v1.2.sql",
    "04_schema_update_v1.3.sql",
    "05_schema_update_v1.4.sql",
    "06_schema_update_v1.5.sql",
    "07_data_fix_landcover_change.sql",
    "08_reconcile_orphan_etl_runs.sql",
    "09_schema_update_v1.6.sql",
    "10_schema_update_v1.7.sql",
    "11_schema_update_v1.8.sql",
    "12_schema_update_v1.9.sql",
    "13_schema_update_v1.10.sql",
    "14_schema_update_v1.11.sql"
)

# Deliberately does NOT stop at the first failure. A file that cannot replay
# onto a clean database is itself a finding, and we want all of them.
$failed = @()
foreach ($f in $files) {
    $path = Join-Path $here $f
    if (-not (Test-Path $path)) {
        Write-Host "`n=== $f  -- FILE NOT FOUND" -ForegroundColor Red
        $failed += "$f (missing)"
        continue
    }
    Write-Host "`n=== $f"
    & psql -U $DBUSER -h $DBHOST -p $DBPORT -d $CHECK -v ON_ERROR_STOP=1 -f $path 2>&1 |
        Select-Object -Last 12 | Write-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "!!! FAILED TO REPLAY: $f" -ForegroundColor Red
        $failed += $f
    }
}

Write-Host "`n=========================================================================="
if ($failed.Count) {
    Write-Host "$($failed.Count) FILE(S) COULD NOT REPLAY ONTO A CLEAN DATABASE:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "   $_" }
    Write-Host ""
    Write-Host "That is a finding in itself: the runbook says these files build the"
    Write-Host "database, and on an empty database they do not. The diff below is"
    Write-Host "still worth reading - it shows how far they got."
} else {
    Write-Host "All files replayed onto a clean database."
}
Write-Host "=========================================================================="

Write-Host "`n-- comparing catalogues`n"
$venv = Join-Path $here "..\03_etl\venv\Scripts\python.exe"
if (Test-Path $venv) {
    & $venv (Join-Path $here "schema_diff.py") --live $LIVE --rebuilt $CHECK
} else {
    & python (Join-Path $here "schema_diff.py") --live $LIVE --rebuilt $CHECK
}

$env:PGPASSWORD = ""
Write-Host "`nScratch database '$CHECK' left in place for the next run."
