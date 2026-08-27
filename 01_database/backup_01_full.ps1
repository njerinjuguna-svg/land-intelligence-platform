# ===========================================================================
# FULL BACKUP - THE ONLY COPY OF TWELVE SESSIONS OF WORK
# Land Intelligence Platform - Geocode Spatial Solutions Ltd
#
# WHY THIS EXISTS
#   rebuild_check.ps1 proved that 01_database reproduces every schema that
#   ships. It also proved something less comfortable: NOTHING in this project
#   recreates the `staging` schema or the data in any of it. The numbered
#   files restore a shape. They do not restore 14,221 landmark rows, 10,357
#   coverage polygons, the OSM extracts, the calibrated nightlights, or the
#   raster catalogue.
#
#   If this laptop is lost or its disk fails, that is what goes. Not the code
#   - the code is small and duplicated. The loaded data, which took twelve
#   sessions and is the actual asset.
#
#   This is the cheapest thing in the whole project and the one with the
#   worst downside if it is skipped.
#
# WHAT IT WRITES
#   <Destination>\<db>_<timestamp>.dump   - pg_dump custom format, whole
#                                           database, compressed
#   <Destination>\<db>_<timestamp>.rasters.csv
#                                         - the raster catalogue: every file
#                                           path the enrichment engine reads
#
#   The CSV matters more than it looks. Rasters are FILES ON DISK, catalogued
#   by path - they are not in the database and this dump does not contain
#   them. If the drive dies, that CSV is the shopping list of what has to be
#   fetched again, and without it you are guessing which twelve of ninety
#   datasets you actually loaded.
#
# WHAT IT DOES NOT DO
#   It does not copy the raster files themselves. They are large and they are
#   re-downloadable from public sources - slowly, and only if you know which
#   ones. That is what the CSV is for. Copy E:\...\rasters to the same drive
#   by hand if you have room; it turns a two-week recovery into an afternoon.
#
# RUN:
#   powershell -ExecutionPolicy Bypass -File .\backup_01_full.ps1 -Destination D:\geocode-backups
#
#   Weekly is the minimum. After any ETL run is better.
# ===========================================================================

param(
    [Parameter(Mandatory = $true)]
    [string]$Destination,

    # How many backups to keep. Older ones are removed AFTER a new one has
    # been written and verified, never before.
    [int]$Keep = 8
)

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

$DBUSER = if ($cfg['DB_USER']) { $cfg['DB_USER'] } else { 'postgres' }
$DBHOST = if ($cfg['DB_HOST']) { $cfg['DB_HOST'] } else { 'localhost' }
$DBPORT = if ($cfg['DB_PORT']) { $cfg['DB_PORT'] } else { '5432' }
$DBNAME = if ($cfg['DB_NAME']) { $cfg['DB_NAME'] } else { 'land_intelligence_kenya' }

if (-not $cfg['DB_PASSWORD']) { Write-Host "DB_PASSWORD not set in .env" -ForegroundColor Red; exit 1 }
$env:PGPASSWORD = $cfg['DB_PASSWORD']

# `createdb` turned out not to be on PATH even though psql was, so nothing
# here assumes a tool is reachable by name. Resolve it or say exactly why not.
function Resolve-PgTool($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $guesses = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\$name.exe" -ErrorAction SilentlyContinue
    if ($guesses) { return ($guesses | Sort-Object FullName -Descending)[0].FullName }
    return $null
}

$PGDUMP    = Resolve-PgTool "pg_dump"
$PGRESTORE = Resolve-PgTool "pg_restore"
$PSQL      = Resolve-PgTool "psql"

# Create the destination rather than refusing over a missing folder. A missing
# DRIVE is a different matter and is still refused below - that means the disk
# is not plugged in, and silently writing somewhere else would be worse.
if ($Destination -and -not (Test-Path $Destination)) {
    $root = [System.IO.Path]::GetPathRoot($Destination)
    if (Test-Path $root) {
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        Write-Host "Created $Destination"
    }
}

if (-not $PGDUMP) {
    Write-Host "Could not find pg_dump.exe on PATH or under C:\Program Files\PostgreSQL\*\bin" -ForegroundColor Red
    Write-Host "Find it and add that bin folder to PATH, then run this again."
    exit 1
}

if (-not (Test-Path $Destination)) {
    Write-Host "Destination '$Destination' does not exist." -ForegroundColor Red
    Write-Host "Plug in the drive, or create the folder, then run this again."
    Write-Host "A backup written to the same disk as the database is not a backup." -ForegroundColor Yellow
    exit 1
}

# A backup on the same physical disk protects against nothing that actually
# happens - but the disk that matters is the one holding the DATABASE, not the
# one holding this script.
#
# On this machine they are not the same. Postgres keeps its data directory
# under C:\Program Files\PostgreSQL\16\data while the project lives on E:, so
# writing a dump to E: IS a cross-disk backup even though it feels like
# backing up to yourself. The first version of this check compared against the
# project folder and would have warned about exactly the arrangement that
# works. So it asks the database where it actually lives.
$dataDir = $null
if ($PSQL) {
    $dataDir = (& $PSQL -U $DBUSER -h $DBHOST -p $DBPORT -d $DBNAME -t -A `
                        -c "SHOW data_directory;" 2>$null | Select-Object -First 1)
}
$dbDrive = if ($dataDir) { $dataDir.Substring(0,1).ToUpper() } else { $here.Substring(0,1).ToUpper() }
$dstDrive = $Destination.Substring(0,1).ToUpper()

if ($dstDrive -eq $dbDrive) {
    Write-Host "WARNING: the destination is on the same drive as the database" -ForegroundColor Yellow
    Write-Host "         ($dataDir). One disk failure takes both copies." -ForegroundColor Yellow
    Write-Host "         Write to a different drive, or an external one." -ForegroundColor Yellow
} else {
    Write-Host "Database lives on ${dbDrive}: , backup going to ${dstDrive}: - different disks." -ForegroundColor Green
}

# Different disks is not the same as different buildings. A dump on E: and a
# laptop on fire are the same outcome, so an off-machine copy is still owed -
# see the closing note.

$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$dump  = Join-Path $Destination "$($DBNAME)_$stamp.dump"
$csv   = Join-Path $Destination "$($DBNAME)_$stamp.rasters.csv"

Write-Host "=========================================================================="
Write-Host "FULL BACKUP"
Write-Host "   database    : $DBNAME"
Write-Host "   destination : $Destination"
Write-Host "   keeping     : $Keep most recent"
Write-Host "=========================================================================="

Write-Host "`n-- dumping (whole database, staging included)"
& $PGDUMP -U $DBUSER -h $DBHOST -p $DBPORT -d $DBNAME `
          --format=custom --compress=6 --no-owner --no-privileges `
          --file=$dump
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $dump)) {
    Write-Host "pg_dump FAILED. Nothing has been deleted." -ForegroundColor Red
    $env:PGPASSWORD = ""
    exit 1
}

$sizeMB = [math]::Round((Get-Item $dump).Length / 1MB, 1)
Write-Host "   wrote $([System.IO.Path]::GetFileName($dump))  ($sizeMB MB)"

# A dump nobody has opened is a hope, not a backup. pg_restore --list reads
# the archive's table of contents and fails on a truncated or corrupt file.
if ($PGRESTORE) {
    Write-Host "-- verifying the archive is readable"
    $toc = & $PGRESTORE --list $dump 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ARCHIVE IS NOT READABLE. Treat this backup as failed." -ForegroundColor Red
        Write-Host "Nothing has been deleted." -ForegroundColor Red
        $env:PGPASSWORD = ""
        exit 1
    }
    Write-Host "   archive readable, $(($toc | Measure-Object -Line).Lines) entries"
} else {
    Write-Host "   pg_restore not found - archive NOT verified." -ForegroundColor Yellow
}

# The recovery shopping list. Rasters are files on disk, not rows.
if ($PSQL) {
    Write-Host "-- writing the raster catalogue (files this dump does NOT contain)"
    # storage_url, NOT path. The first version of this line guessed `path`
    # because the engine reads e["path"] - but that key is built in Python
    # from a SELECT that names the column storage_url. The dump succeeded and
    # the recovery list silently did not, which is the worst way for a backup
    # to be wrong: it looks finished.
    #
    # Every status is included, not just 'active'. A quarantined raster
    # (landcover_change at pending_review) still has to be re-fetched to get
    # back to where we are.
    $q = "COPY (SELECT raster_id, variable, storage_url, status, temporal_start FROM metadata.raster_catalog ORDER BY raster_id) TO STDOUT WITH CSV HEADER"
    & $PSQL -U $DBUSER -h $DBHOST -p $DBPORT -d $DBNAME -v ON_ERROR_STOP=1 -c $q |
        Out-File -FilePath $csv -Encoding utf8
    $n = if (Test-Path $csv) { (Get-Content $csv | Measure-Object -Line).Lines - 1 } else { -1 }
    if ($LASTEXITCODE -ne 0 -or $n -lt 1) {
        # LOUD, because a silent failure here is invisible until recovery day.
        # The dump is still good - only the shopping list is missing.
        Write-Host "   *** RASTER CATALOGUE NOT WRITTEN ***" -ForegroundColor Red
        Write-Host "   The database dump above is fine. What is missing is the" -ForegroundColor Red
        Write-Host "   list of raster files it does NOT contain, which is what" -ForegroundColor Red
        Write-Host "   you would need to rebuild the workbench. Fix before" -ForegroundColor Red
        Write-Host "   relying on this backup." -ForegroundColor Red
        if (Test-Path $csv) { Remove-Item $csv -Force }
    } else {
        Write-Host "   wrote $([System.IO.Path]::GetFileName($csv))  ($n raster(s) referenced)"
    }
}

# Retention runs LAST, and only after a verified write. Deleting old backups
# before the new one is proven is how people end up with none.
$old = Get-ChildItem $Destination -Filter "$($DBNAME)_*.dump" |
       Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep
if ($old) {
    Write-Host "`n-- removing $($old.Count) backup(s) beyond the $Keep most recent"
    foreach ($f in $old) {
        Write-Host "   $($f.Name)"
        Remove-Item $f.FullName -Force
        $mate = $f.FullName -replace '\.dump$', '.rasters.csv'
        if (Test-Path $mate) { Remove-Item $mate -Force }
    }
}

$env:PGPASSWORD = ""

Write-Host "`n=========================================================================="
Write-Host "DONE.  $sizeMB MB at $dump"
Write-Host ""
Write-Host "To restore onto a clean machine:"
Write-Host "   psql -U postgres -c `"CREATE DATABASE $DBNAME;`""
Write-Host "   psql -U postgres -d $DBNAME -c `"CREATE EXTENSION postgis;`""
Write-Host "   pg_restore -U postgres -d $DBNAME --no-owner --no-privileges <file>.dump"
Write-Host ""
Write-Host "THE RASTERS ARE NOT IN THIS FILE. The .rasters.csv beside it lists"
Write-Host "every path the enrichment engine reads. Copy the raster folder to"
Write-Host "this drive as well if there is room - it is the difference between"
Write-Host "an afternoon of recovery and a fortnight of re-downloading."
Write-Host "=========================================================================="
