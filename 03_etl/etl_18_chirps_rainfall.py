"""
============================================================================
ETL 18 - CHIRPS RAINFALL CLIMATOLOGY (climate.rainfall) ~5 km
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does:
  Builds Kenya's MEAN ANNUAL RAINFALL map (mm per year) by downloading CHIRPS
  annual rainfall grids for a 30-year period and averaging them, then saves it
  as a COG and catalogues it as climate.rainfall.

Why a 30-year average and not last year:
  One year tells you about that year's weather. A buyer wants to know the
  CLIMATE of a place: what it normally gets. The world standard for that is a
  30-year "normal" (WMO), here 1991-2020. Averaging 30 annual grids smooths out
  droughts and El Nino years and leaves the underlying signal: wet highlands,
  dry north and east. That is the number that actually predicts what can grow.

Why this layer is cheap to build (good news for your connection):
  CHIRPS is ~5 km resolution, so each annual Africa file is small (a few MB)
  compared with the 30 m soil/terrain rasters. Downloads are SEQUENTIAL whole
  files (which your connection handles well) rather than thousands of random
  remote reads (which it does not). Fully resumable: rerun and it skips what it
  already has.

Resolution note (deliberate, not a shortcut):
  5 km is CHIRPS's NATIVE resolution. There is no finer version to get. Rainfall
  genuinely varies at landscape scale, so this is the best available, and the
  catalogue already specifies 5 km for climate.rainfall.

Licensing: CHIRPS is PUBLIC DOMAIN (UCSB Climate Hazards Center). No commercial
restriction. Cite: Funk et al. (2015), Scientific Data 2:150066.

URL probing:
  The exact CHIRPS directory layout differs between v2.0 and v3.0. Rather than
  hardcode a guess, this script TRIES a list of known URL patterns for one test
  year, reports which one works, and then uses it for all years. If none work it
  tells you clearly instead of failing obscurely.

How to run (from 03_etl with venv active):
  python etl_18_chirps_rainfall.py
============================================================================
"""

import os
import sys
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

# Same PROJ/GDAL fix as etl_17: stop PostgreSQL's older PROJ from hijacking
# rasterio. Must happen BEFORE rasterio is imported.
for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import rasterio
    from rasterio.windows import from_bounds, Window
    from rasterio.shutil import copy as rio_copy
except ImportError:
    sys.exit("ERROR: rasterio missing. With venv active: pip install rasterio")

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
PIPELINE = "etl_18_chirps_rainfall"

RAW_DIR = BASE / "data" / "raw" / "climate" / "chirps"
RAW_DIR.mkdir(parents=True, exist_ok=True)
COG_DIR = PROJECT / "06_rasters" / "cog" / "climate"
COG_DIR.mkdir(parents=True, exist_ok=True)

COG_NAME = "climate_rainfall_chirps_5km_1991-2020.tif"
COG_PATH = COG_DIR / COG_NAME
TMP_PATH = RAW_DIR / "_rainfall_tmp.tif"

YEAR_START, YEAR_END = 1991, 2020        # WMO 30-year normal period
M_PER_DEG = 111320.0
OUT_NODATA = -9999

# Candidate URL patterns, tried in order for a test year. {y} = year.
URL_PATTERNS = [
    "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/annual/africa/tifs/chirps-v3.0.{y}.tif",
    "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/annual/global/tifs/chirps-v3.0.{y}.tif",
    "https://data.chc.ucsb.edu/products/CHIRPS-2.0/africa_annual/tifs/chirps-v2.0.{y}.tif",
    "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_annual/tifs/chirps-v2.0.{y}.tif",
]

ATTRIB = ("CHIRPS (Climate Hazards Center, UC Santa Barbara), public domain. "
          "Funk et al. 2015, Sci Data 2:150066.")


def md5_of(path, chunk=8 * 1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def url_exists(url, timeout=45):
    """HEAD-style check: can we start reading this URL?"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LIP-ETL/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def download(url, dest, retries=5, timeout=120):
    """Sequential chunked download with retries. Returns True on success."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LIP-ETL/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
            tmp.replace(dest)
            return True
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                tmp.unlink(missing_ok=True)
                return False
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        tmp.unlink(missing_ok=True)
        time.sleep(2 * attempt)
    return False


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
    # 1. Work out which CHIRPS URL pattern is live, using one test year.
    # -----------------------------------------------------------------------
    print("\nProbing CHIRPS URL patterns ...")
    pattern = None
    for p in URL_PATTERNS:
        test = p.format(y=2020)
        ok = url_exists(test)
        print(f"  {'OK  ' if ok else 'no  '} {test}")
        if ok:
            pattern = p
            break
    if pattern is None:
        raise SystemExit(
            "None of the known CHIRPS URL patterns responded. The layout may "
            "have changed. Open https://data.chc.ucsb.edu/products/ in a browser, "
            "find the annual rainfall .tif folder, and tell me the URL.")
    print(f"Using: {pattern}")

    # -----------------------------------------------------------------------
    # 2. Download the annual grids (sequential, resumable).
    # -----------------------------------------------------------------------
    years = list(range(YEAR_START, YEAR_END + 1))
    have, missing = [], []
    for i, y in enumerate(years, 1):
        dest = RAW_DIR / f"chirps_annual_{y}.tif"
        if dest.exists() and dest.stat().st_size > 1024:
            have.append((y, dest))
            print(f"  [{i:>2}/{len(years)}] {y}  already have it")
            continue
        if download(pattern.format(y=y), dest):
            have.append((y, dest))
            print(f"  [{i:>2}/{len(years)}] {y}  {dest.stat().st_size/1e6:.1f} MB")
        else:
            missing.append(y)
            print(f"  [{i:>2}/{len(years)}] {y}  NOT AVAILABLE, skipping")

    # A "30-year normal" is a claim with a definition behind it. If years are
    # missing we must not quietly publish a 20-year average under that label,
    # so we refuse below 25 years and say so in the catalogue entry above 25.
    if len(have) < 25:
        raise SystemExit(
            f"Only {len(have)} of 30 annual grids available. That is not a "
            f"climate normal and should not be catalogued as one. Missing: "
            f"{missing}. Check the source layout before rerunning.")
    if missing:
        print(f"\nWARNING: {len(missing)} year(s) missing: {missing}. The "
              f"average will be over {len(have)} years and the catalogue entry "
              f"will say so rather than claim a full 30-year normal.")
    years_used = [y for y, _ in have]
    print(f"\n{len(have)} annual grids ready ({min(years_used)}-{max(years_used)})")

    # -----------------------------------------------------------------------
    # 3. Average them over Kenya's window.
    #    CHIRPS is already EPSG:4326, so no reprojection needed.
    # -----------------------------------------------------------------------
    with engine.connect() as conn:
        xmin, xmax, ymin, ymax = conn.execute(text("""
            SELECT ST_XMin(e), ST_XMax(e), ST_YMin(e), ST_YMax(e)
            FROM (SELECT ST_Extent(geom) AS e FROM admin.country) t
        """)).one()
    pad = 0.1
    xmin, xmax, ymin, ymax = xmin - pad, xmax + pad, ymin - pad, ymax + pad
    print(f"Kenya bbox: lon {xmin:.3f}..{xmax:.3f}, lat {ymin:.3f}..{ymax:.3f}")

    total = None
    count = None
    ref_profile = None
    ref_grid = None
    for i, (yr, f) in enumerate(have, 1):
        with rasterio.open(f) as src:
            # EVERY year must sit on exactly the same grid as the first one.
            # We cut Kenya's window once, by pixel offset, and then reuse that
            # window for all 30 files. That is only valid if the files share a
            # grid. If CHIRPS ever mixes an Africa file with a global one, the
            # same pixel offsets would point at a different part of the planet
            # and we would average Kenya with somewhere else, producing a map
            # that looks perfectly plausible and is wrong. So we check.
            if ref_grid is not None:
                same = (src.transform.almost_equals(ref_grid[0], precision=1e-9)
                        and src.width == ref_grid[1]
                        and src.height == ref_grid[2])
                if not same:
                    raise SystemExit(
                        f"{yr} sits on a different grid from the reference year "
                        f"({src.width}x{src.height} vs {ref_grid[1]}x"
                        f"{ref_grid[2]}). Refusing to average mismatched grids. "
                        f"Delete {f.name} and rerun, or we handle both layouts.")
            if ref_profile is None:
                win = from_bounds(xmin, ymin, xmax, ymax, src.transform)
                win = win.round_offsets().round_lengths()
                c0 = max(0, int(win.col_off)); r0 = max(0, int(win.row_off))
                w = min(int(win.width), src.width - c0)
                h = min(int(win.height), src.height - r0)
                base_win = Window(c0, r0, w, h)
                ref_profile = {
                    "driver": "GTiff", "dtype": "int16", "count": 1,
                    "crs": src.crs, "transform": src.window_transform(base_win),
                    "width": w, "height": h, "nodata": OUT_NODATA,
                    "tiled": True, "blockxsize": 512, "blockysize": 512,
                }
                px_deg = src.transform.a
                total = np.zeros((h, w), dtype="float64")
                count = np.zeros((h, w), dtype="int32")
                ref_grid = (src.transform, src.width, src.height)
                print(f"Kenya window: {w} x {h} px (~{px_deg * M_PER_DEG / 1000:.1f} km)")

            arr = src.read(1, window=base_win).astype("float32")
            good = np.isfinite(arr) & (arr >= 0)     # CHIRPS uses -9999 for nodata
            total[good] += arr[good]
            count[good] += 1
        if i % 5 == 0 or i == len(have):
            print(f"  averaged {i}/{len(have)} years")

    # Average, then REJECT anything physically impossible instead of clipping
    # it into range. Nowhere on earth averages above 15 m of rain a year, so a
    # pixel above that is a broken pixel, not a very wet one. Clipping it to
    # 15000 would hide the breakage behind a number that looks like data.
    RAIN_MAX_MM = 15000
    mean_mm = np.full(total.shape, OUT_NODATA, dtype="int16")
    valid = count > 0
    avg = np.zeros(total.shape, dtype="float64")
    avg[valid] = total[valid] / count[valid]
    impossible = valid & (avg > RAIN_MAX_MM)
    if impossible.any():
        print(f"  WARNING: {int(impossible.sum())} pixels averaged above "
              f"{RAIN_MAX_MM} mm/year and were marked nodata, not clipped.")
        valid &= ~impossible
    mean_mm[valid] = np.rint(avg[valid]).astype("int16")

    v = mean_mm[valid]
    print(f"\nMean annual rainfall over Kenya: min {v.min()} mm, max {v.max()} mm, "
          f"mean {v.mean():.0f} mm  (averaged over {len(have)} years)")
    print("  (sanity check: Kenyan ASALs ~150-400 mm, Nairobi ~900 mm, "
          "western/highlands ~1200-2000 mm)")
    print(f"  pixels with no valid year at all: {int((count == 0).sum())}")

    with rasterio.open(TMP_PATH, "w", **ref_profile) as dst:
        dst.write(mean_mm, 1)

    print("Converting to COG ...")
    if COG_PATH.exists():
        COG_PATH.unlink()
    rio_copy(str(TMP_PATH), str(COG_PATH), driver="COG",
             compress="DEFLATE", predictor=2, overview_resampling="average")
    TMP_PATH.unlink(missing_ok=True)
    size_mb = COG_PATH.stat().st_size / 1_000_000
    print(f"COG written: {COG_PATH.name}  ({size_mb:.1f} MB)")
    checksum = md5_of(COG_PATH)

    # -----------------------------------------------------------------------
    # 4. Catalogue it.
    # -----------------------------------------------------------------------
    with engine.connect() as conn:
        source_id = conn.execute(text(
            "SELECT source_id FROM metadata.sources WHERE name = 'CHIRPS'"
        )).scalar()
        dataset_id = conn.execute(text(
            "SELECT dataset_id FROM metadata.datasets WHERE code = 'climate.rainfall'"
        )).scalar()
    if source_id is None or dataset_id is None:
        raise SystemExit("CHIRPS source or climate.rainfall dataset missing. Run etl_04.")

    with rasterio.open(COG_PATH) as s:
        l, b, r, t = s.bounds.left, s.bounds.bottom, s.bounds.right, s.bounds.top

    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM metadata.raster_catalog
            WHERE dataset_id = :did AND variable = 'rainfall'
        """), {"did": dataset_id})
        conn.execute(text("""
            INSERT INTO metadata.raster_catalog
                (dataset_id, name, variable, storage_url, format, pixel_size_m,
                 band_count, nodata_value, temporal_start, temporal_end, bbox,
                 checksum, source_id, source_date, confidence)
            VALUES
                (:did, :name, 'rainfall', :url, 'COG', :px, 1, :nodata,
                 :ts, :te, ST_MakeEnvelope(:l, :b, :r, :t, 4326),
                 :chk, :sid, CURRENT_DATE, 3)
        """), {
            "did": dataset_id,
            # Name the period we ACTUALLY averaged, not the one we intended.
            "name": (f"Mean annual rainfall mm/year, averaged over "
                     f"{len(have)} annual CHIRPS grids covering "
                     f"{min(years_used)}-{max(years_used)}"
                     + ("" if not missing else
                        f" (missing {len(missing)}: {missing})")
                     + ". " + ATTRIB),
            "url": str(COG_PATH),
            "px": round(px_deg * M_PER_DEG, 1),
            "nodata": OUT_NODATA,
            "ts": f"{min(years_used)}-01-01", "te": f"{max(years_used)}-12-31",
            "l": l, "b": b, "r": r, "t": t,
            "chk": checksum, "sid": source_id,
        })
        conn.execute(text("""
            UPDATE metadata.datasets SET etl_status = 'ingested', updated_at = now()
            WHERE code = 'climate.rainfall'
        """))
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = 1
            WHERE run_id = :id
        """), {"id": run_id})

    print(f"\nDONE. Run {run_id} logged as success.")
    print(f"Rainfall catalogued: {COG_PATH}")
    print("QGIS: wet west/highlands (Kakamega, Kericho, Mt Kenya) should be "
          "high; Turkana, Marsabit, Wajir, Garissa low. Compare with the DEM: "
          "rainfall should track the highlands closely.")

# BaseException, NOT Exception, and this is load-bearing.
# This script's own guards raise SystemExit, and Ctrl+C raises
# KeyboardInterrupt. Both inherit from BaseException, so an
# `except Exception` handler never fires for them and the
# metadata.etl_runs row is left at 'running' forever. That bug left 12
# orphan rows across a month of work, including runs PROGRESS.md
# documents as failures. The trailing `raise` is unchanged: this logs
# the failure and then gets out of the way.
except BaseException as exc:
    TMP_PATH.unlink(missing_ok=True)
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'failed', error_message = :e
            WHERE run_id = :id
        """), {"e": str(exc)[:2000], "id": run_id})
    raise
