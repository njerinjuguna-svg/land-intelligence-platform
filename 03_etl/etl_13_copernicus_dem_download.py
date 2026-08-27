"""
============================================================================
ETL 13 - COPERNICUS GLO-30 DEM: DOWNLOAD (step 1 of 3 for terrain)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does:
  Downloads the Copernicus GLO-30 elevation tiles that cover Kenya, and only
  those tiles, from the free AWS open-data bucket into
  03_etl/data/raw/terrain/copernicus_glo30/.

  It does NOTHING else. No mosaic, no database load. Getting ~4 GB down is the
  slow part, so we isolate it: this script needs no special tools (only Python
  built-ins), it is resumable (rerun and it skips whatever is already on disk),
  and it cannot corrupt the database because it barely touches it.

Where this sits in the terrain pipeline:
  etl_13  (this)  download Kenya's DEM tiles           <- no new tools
  etl_14  (next)  stitch tiles into one national COG   <- installs GDAL tools
                  and catalogue it in metadata.raster_catalog
  etl_15  (after) derive slope + TWI from the DEM      <- no new download

Why one tile per 1x1 degree, and why we skip some:
  Copernicus ships the world as 1-degree square tiles. Ocean squares simply do
  not exist in the bucket. We read the bucket's own tileList.txt (the authoritative
  list of tiles that DO exist), keep only the ones that overlap Kenya's real
  outline (admin.country), and download those. That way we never chase a tile
  that is not there.

Licensing (Copernicus GLO-30, "Full, Free and Open"):
  Free for commercial use WITH attribution. When we publish anything derived
  from this DEM we must carry the notice:
    "produced using Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and
     (c) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by
     the European Union and ESA; all rights reserved."
  etl_14 will stamp this onto the catalogue row. Recorded here so it is not
  forgotten.

How to run (from 03_etl with venv active):
  python etl_13_copernicus_dem_download.py
============================================================================
"""

import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
PIPELINE = "etl_13_copernicus_dem_download"

# Where the raw tiles land. Raw downloads stay under data/raw (scratch space);
# the cleaned national COG will live in 06_rasters/cog/terrain later (etl_14).
RAW_DIR = BASE / "data" / "raw" / "terrain" / "copernicus_glo30"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
TILELIST_URL = f"{BUCKET}/tileList.txt"

# Matches e.g. Copernicus_DSM_COG_10_S05_00_E039_00_DEM
TILE_RE = re.compile(r"Copernicus_DSM_COG_10_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM")


def tile_bounds(ns, latval, ew, lonval):
    """Return (lon_min, lat_min, lon_max, lat_max) for a 1-degree tile.
    A tile named N04 spans latitude 4..5; S05 spans -5..-4;
    E039 spans longitude 39..40; W010 spans -10..-9."""
    lat_min = latval if ns == "N" else -latval
    lon_min = lonval if ew == "E" else -lonval
    return lon_min, lat_min, lon_min + 1, lat_min + 1


def http_get(url, retries=5, timeout=120):
    """Small GET returning bytes (used for the text tile list).
    Retries on ANY network hiccup, including read timeouts."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LIP-ETL/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(2 * attempt)
    raise last


def download_tile(url, dest, retries=5, timeout=120):
    """Stream one tile to `dest` in small chunks. Returns:
        'ok'      saved successfully
        'missing' bucket said 404/403 (tile not there) -> skip
        'failed'  network kept timing out after every retry -> skip, rerun later

    Why chunks instead of one big read: the crash last time was a read timeout,
    the connection stalled while trying to pull a whole 40 MB tile inside a single
    timeout window. Reading 256 KB at a time gives each small read its own fresh
    window, so a slow-but-alive connection stays healthy instead of dying."""
    tmp = dest.with_suffix(".tif.part")
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LIP-ETL/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(262144)  # 256 KB
                    if not chunk:
                        break
                    f.write(chunk)
            tmp.replace(dest)  # atomic: the .tif appears only when fully written
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                tmp.unlink(missing_ok=True)
                return "missing"
            last = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        tmp.unlink(missing_ok=True)   # bin the half-written part before retrying
        time.sleep(2 * attempt)       # back off a little longer each time
    return "failed"


# ---------------------------------------------------------------------------
# Connect (only to read Kenya's bounding box and to log the run)
# ---------------------------------------------------------------------------
load_dotenv(BASE / ".env")
pw = os.getenv("DB_PASSWORD")
if not pw or pw == "put_your_password_here":
    sys.exit("ERROR: edit the .env file and set DB_PASSWORD first.")

url = (
    f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{pw}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
    f"/{os.getenv('DB_NAME', 'land_intelligence_kenya')}"
)
engine = create_engine(url)
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
print("Connected to database:", os.getenv("DB_NAME", "land_intelligence_kenya"))

with engine.begin() as conn:
    run_id = conn.execute(text("""
        INSERT INTO metadata.etl_runs (pipeline, started_at, run_status)
        VALUES (:p, now(), 'running') RETURNING run_id
    """), {"p": PIPELINE}).scalar()
print(f"ETL run opened (run_id={run_id})")

try:
    # -----------------------------------------------------------------------
    # 1. Kenya's bounding box, straight from our own national outline.
    #    We add a tiny margin so a tile that only clips the border is kept.
    # -----------------------------------------------------------------------
    with engine.connect() as conn:
        xmin, xmax, ymin, ymax = conn.execute(text("""
            SELECT ST_XMin(e), ST_XMax(e), ST_YMin(e), ST_YMax(e)
            FROM (SELECT ST_Extent(geom) AS e FROM admin.country) t
        """)).one()
    margin = 0.05
    xmin, xmax, ymin, ymax = xmin - margin, xmax + margin, ymin - margin, ymax + margin
    print(f"Kenya bbox: lon {xmin:.3f}..{xmax:.3f}, lat {ymin:.3f}..{ymax:.3f}")

    # -----------------------------------------------------------------------
    # 2. The authoritative list of tiles that actually exist in the bucket.
    # -----------------------------------------------------------------------
    print("Fetching bucket tileList.txt ...")
    lines = http_get(TILELIST_URL).decode("utf-8", "ignore").splitlines()

    # -----------------------------------------------------------------------
    # 3. Keep only tiles overlapping Kenya.
    # -----------------------------------------------------------------------
    wanted = []
    for line in lines:
        m = TILE_RE.search(line.strip())
        if not m:
            continue
        ns, latval, ew, lonval = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        t_lonmin, t_latmin, t_lonmax, t_latmax = tile_bounds(ns, latval, ew, lonval)
        overlaps = not (t_lonmax <= xmin or t_lonmin >= xmax
                        or t_latmax <= ymin or t_latmin >= ymax)
        if overlaps:
            wanted.append(m.group(0))  # the full tile folder name
    wanted = sorted(set(wanted))
    print(f"{len(wanted)} Kenya tiles to fetch (ocean squares excluded automatically).")

    # -----------------------------------------------------------------------
    # 4. Download each tile. Skip anything already on disk (resumable).
    # -----------------------------------------------------------------------
    got, skipped, missing = 0, 0, 0
    failed_tiles = []
    for i, folder in enumerate(wanted, 1):
        dest = RAW_DIR / f"{folder}.tif"
        if dest.exists() and dest.stat().st_size > 1024:
            skipped += 1
            print(f"  [{i:>3}/{len(wanted)}] {folder}  already have it, skip")
            continue
        tile_url = f"{BUCKET}/{folder}/{folder}.tif"
        status = download_tile(tile_url, dest)
        if status == "ok":
            got += 1
            mb = dest.stat().st_size / 1_000_000
            print(f"  [{i:>3}/{len(wanted)}] {folder}  {mb:6.1f} MB")
        elif status == "missing":
            missing += 1
            print(f"  [{i:>3}/{len(wanted)}] {folder}  not in bucket, skip")
        else:  # failed
            failed_tiles.append(folder)
            print(f"  [{i:>3}/{len(wanted)}] {folder}  network kept timing out, "
                  f"will grab on rerun")

    on_disk = len(list(RAW_DIR.glob("Copernicus_DSM_COG_10_*_DEM.tif")))
    print(f"\nThis run: {got} downloaded, {skipped} already had, "
          f"{missing} not-in-bucket, {len(failed_tiles)} still to retry.")
    print(f"{on_disk} of {len(wanted)} Kenya tiles now on disk.")
    if failed_tiles:
        print("Some tiles timed out. Just run the script again: it keeps every "
              "tile you already have and only fetches the missing ones.")

    # 'partial' is an honest status: the run worked but not every tile is down yet.
    final_status = "success" if not failed_tiles else "partial"
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = :st, rows_out = :r
            WHERE run_id = :id
        """), {"st": final_status, "r": on_disk, "id": run_id})

    print(f"\nDONE. Run {run_id} logged as {final_status}.")
    print(f"Tiles are in: {RAW_DIR}")
    print("Next: etl_14 stitches these into one national COG and catalogues it.")

# BaseException, NOT Exception, and this is load-bearing.
# This script's own guards raise SystemExit, and Ctrl+C raises
# KeyboardInterrupt. Both inherit from BaseException, so an
# `except Exception` handler never fires for them and the
# metadata.etl_runs row is left at 'running' forever. That bug left 12
# orphan rows across a month of work, including runs PROGRESS.md
# documents as failures. The trailing `raise` is unchanged: this logs
# the failure and then gets out of the way.
except BaseException as exc:
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'failed', error_message = :e
            WHERE run_id = :id
        """), {"e": str(exc)[:2000], "id": run_id})
    raise
