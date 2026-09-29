# ===========================================================================
# THE RESTORE DRILL - PROVE THE BACKUP IS A BACKUP
# Land Intelligence Platform - Geocode Spatial Solutions Ltd
#
# WHY THIS EXISTS
#   backup_01_full.ps1 verifies that an archive is READABLE - pg_restore
#   --list parses its table of contents, which fails on a truncated file.
#   That is more than most people do and it is still not a backup.
#
#   A backup is a thing you have restored. Until then it is a belief, and the
#   day you test the belief is the worst possible day to discover it was
#   wrong. DEPLOY.md has carried "Backup restore drill: never performed" since
#   the deployment kit was written.
#
#   This performs it: newest dump -> a scratch database -> compared against
#   live on schema AND on row counts.
#
# WHY ROW COUNTS AND NOT JUST SCHEMA
#   A restore that produced every table and no rows would pass every
#   structural check ever written. That is precisely the failure a drill
#   exists to catch, because nothing else would ever notice it.
#
# IT NEVER TOUCHES THE LIVE DATABASE
#   It reads live to count rows. It writes only to the scratch database, whose
#   name is checked against the live name before anything is dropped.
#
# RUN:
#   powershell -ExecutionPolicy Bypass -File .\restore_drill.ps1
#   powershell -ExecutionPolicy Bypass -File .\restore_drill.ps1 -Backups "E:\geocode-backups"
#
# Takes a few minutes. The row counting is exact and deliberately unhurried.
# ===========================================================================

param(
    [string]$Backups = "E:\geocode-backups",
    [string]$Scratch = "land_intelligence_restore_test",
    [switch]$KeepAfter
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
$LIVE   = if ($cfg['DB_NAME']) { $cfg['DB_NAME'] } else { 'land_intelligence_kenya' }

if (-not $cfg['DB_PASSWORD']) { Write-Host "DB_PASSWORD not set in .env" -ForegroundColor Red; exit 1 }
$env:PGPASSWORD = $cfg['DB_PASSWORD']

# A control, not a comment. This script drops a database.
if ($Scratch -eq $LIVE) {
    Write-Host "REFUSING: scratch name equals live name." -ForegroundColor Red
    exit 1
}

function Resolve-PgTool($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $g = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\$name.exe" -ErrorAction SilentlyContinue
    if ($g) { return ($g | Sort-Object FullName -Descending)[0].FullName }
    return $null
}

$PSQL      = Resolve-PgTool "psql"
$PGRESTORE = Resolve-PgTool "pg_restore"
foreach ($t in @(@("psql", $PSQL), @("pg_restore", $PGRESTORE))) {
    if (-not $t[1]) {
        Write-Host "Could not find $($t[0]).exe on PATH or under C:\Program Files\PostgreSQL\*\bin" -ForegroundColor Red
        exit 1
    }
}

# NEWEST DUMP, chosen by the script rather than typed by hand. The one you
# would actually reach for in an emergency is the most recent one, so that is
# the one that gets tested.
if (-not (Test-Path $Backups)) {
    Write-Host "No backup folder at $Backups" -ForegroundColor Red
    Write-Host "Run backup_01_full.ps1 first, or pass -Backups <path>."
    exit 1
}
$dump = Get-ChildItem $Backups -Filter "*.dump" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $dump) {
    Write-Host "No .dump file in $Backups" -ForegroundColor Red
    exit 1
}

$ageH = [math]::Round(((Get-Date) - $dump.LastWriteTime).TotalHours, 1)

Write-Host "=========================================================================="
Write-Host "RESTORE DRILL"
Write-Host "   dump    : $($dump.Name)"
Write-Host "   size    : $([math]::Round($dump.Length / 1MB, 1)) MB"
Write-Host "   age     : $ageH hour(s) old"
Write-Host "   into    : $Scratch   (dropped and recreated now)"
Write-Host "   against : $LIVE      (read only)"
Write-Host "=========================================================================="

Write-Host "`n-- creating the scratch database"
& $PSQL -U $DBUSER -h $DBHOST -p $DBPORT -d postgres -v ON_ERROR_STOP=1 `
        -c "DROP DATABASE IF EXISTS $Scratch;" 2>&1 | Out-Null
& $PSQL -U $DBUSER -h $DBHOST -p $DBPORT -d postgres -v ON_ERROR_STOP=1 `
        -c "CREATE DATABASE $Scratch;" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not create $Scratch." -ForegroundColor Red
    $env:PGPASSWORD = ""; exit 1
}
& $PSQL -U $DBUSER -h $DBHOST -p $DBPORT -d $Scratch `
        -c "CREATE EXTENSION IF NOT EXISTS postgis;" 2>&1 | Out-Null

Write-Host "-- restoring (several minutes; --jobs 4 to keep it bearable)"
$t0 = Get-Date

# --no-owner and --no-privileges because the roles on a recovery machine will
# not be these ones. That is the whole point of restoring somewhere else.
& $PGRESTORE -U $DBUSER -h $DBHOST -p $DBPORT -d $Scratch `
             --no-owner --no-privileges --jobs 4 $dump.FullName 2>&1 |
    Select-Object -Last 25 | Write-Host

$mins = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
Write-Host "`n-- restore finished in $mins minute(s)"
Write-Host "   (pg_restore warnings about extensions or comments are normal"
Write-Host "    and do not mean rows are missing - that is what the count"
Write-Host "    comparison below is for.)"

Write-Host "`n-- comparing schema and row counts against live`n"
$py = Join-Path $here "..\03_etl\venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py (Join-Path $here "schema_diff.py") --live $LIVE --rebuilt $Scratch `
      --rows --dump-age-hours $ageH
$verdict = $LASTEXITCODE

$env:PGPASSWORD = ""

Write-Host ""
if ($KeepAfter) {
    Write-Host "Scratch database '$Scratch' left in place."
} else {
    Write-Host "To remove the scratch database when you are done looking:"
    Write-Host "  psql -U $DBUSER -d postgres -c `"DROP DATABASE $Scratch;`""
}
exit $verdict
