"""
============================================================================
ETL 15 - TERRAIN SLOPE (terrain.slope, degrees) - step 3 of terrain
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does:
  Reads the national DEM we built in etl_14 and calculates, for every pixel,
  how STEEP the ground is, in degrees (0 = dead flat, 45 = a very steep hill).
  Saves the result as a COG in 06_rasters/cog/terrain and catalogues it as
  terrain.slope. No download, no new tools (rasterio + numpy already present).

Why slope matters for the product:
  Steepness is one of the strongest "can you actually build here / what will it
  cost" signals. Flat land is cheap to develop; steep land means retaining
  walls, erosion risk, access problems. Slope also feeds the wetness index
  (etl_16) and the final suitability score.

How steepness is measured (Horn's method):
  For each pixel we look at its 8 neighbours (a 3x3 window) and measure how fast
  the height changes left-to-right and top-to-bottom. Combine those two rates
  and you get the slope. This is the same maths QGIS and ArcGIS use.

The one subtlety we handle carefully (degrees vs metres):
  The DEM is stored in degrees of longitude/latitude, but slope must be computed
  in METRES. A pixel is ~30.9 m tall everywhere in Kenya, but its WIDTH in
  metres shrinks the further you are from the equator (because lines of
  longitude squeeze together). So we compute the true ground width of a pixel
  for each row using that row's latitude. Ignoring this would tilt every slope
  slightly. We keep the output in EPSG:4326 to match the rest of the schema.

Memory:
  We never load the whole 1.28-billion-pixel grid. We sweep down the country in
  horizontal strips, reading a one-pixel overlap so slope is seamless across
  strip edges. Peak memory stays around 1 GB.

How to run (from 03_etl with venv active):
  python etl_15_terrain_slope.py
============================================================================
"""

import os
import sys
import math
import hashlib
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import rasterio
    from rasterio.windows import Window
    from rasterio.shutil import copy as rio_copy
except ImportError:
    sys.exit("ERROR: rasterio missing. With venv active: pip install rasterio")

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
PIPELINE = "etl_15_terrain_slope"

COG_DIR = PROJECT / "06_rasters" / "cog" / "terrain"
COG_DIR.mkdir(parents=True, exist_ok=True)
COG_NAME = "terrain_slope_derived_glo30_2021.tif"
COG_PATH = COG_DIR / COG_NAME
TMP_PATH = BASE / "data" / "raw" / "terrain" / "_slope_tmp.tif"

STRIP = 1024                 # rows processed at a time (keeps memory ~1 GB)
OUT_NODATA_I16 = -32768      # nodata sentinel for the Int16 output
SCALE = 0.01                 # stored value * 0.01 = degrees (0.01 deg precision)
M_PER_DEG = 111320.0         # metres per degree of latitude (good global mean)


def md5_of(path, chunk=8 * 1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


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
    # Find the DEM by ASKING THE CATALOGUE where it is. The catalogue is the
    # single source of truth for raster locations, so we honour it here.
    # -----------------------------------------------------------------------
    with engine.connect() as conn:
        dem_path = conn.execute(text("""
            SELECT storage_url FROM metadata.raster_catalog
            WHERE variable = 'elevation' AND status = 'active'
            ORDER BY raster_id DESC LIMIT 1
        """)).scalar()
    if not dem_path or not Path(dem_path).exists():
        raise SystemExit("DEM not found via catalogue. Run etl_14 first.")
    print(f"DEM: {dem_path}")

    with rasterio.open(dem_path) as dem:
        width, height = dem.width, dem.height
        px = dem.transform.a          # pixel width in degrees (+)
        py = -dem.transform.e         # pixel height in degrees (+)
        out_top = dem.transform.f     # top edge latitude
        src_nodata = dem.nodata
        profile = dem.profile.copy()

        cell_y = py * M_PER_DEG       # pixel height in metres (constant)

        profile.update(
            driver="GTiff", dtype="int16", count=1, nodata=OUT_NODATA_I16,
            tiled=True, blockxsize=512, blockysize=512, bigtiff="YES",
            compress=None,
        )

        print(f"Computing slope over {width} x {height} px in strips of {STRIP} rows ...")
        with rasterio.open(TMP_PATH, "w", **profile) as dst:
            dst.scales = (SCALE,)          # tag so 0.01-unit values read as degrees
            for r0 in range(0, height, STRIP):
                r1 = min(r0 + STRIP, height)
                sh = r1 - r0

                # Read the strip with a 1-pixel halo all around (boundless), so
                # the 3x3 window has neighbours even at strip/country edges.
                win = Window(-1, r0 - 1, width + 2, sh + 2)
                a = dem.read(1, window=win, boundless=True,
                             fill_value=np.nan).astype("float32")
                if src_nodata is not None:
                    a[a == src_nodata] = np.nan

                # Ground width of a pixel, per output row, from that row's lat.
                rows = np.arange(r0, r1)
                lat = out_top - (rows + 0.5) * py
                cell_x = (px * M_PER_DEG * np.cos(np.radians(lat))).astype("float32")
                cell_x = cell_x.reshape(-1, 1)      # column vector to broadcast

                # Horn's 3x3 gradients on the interior (maps to rows r0..r1-1).
                dzdx = ((a[0:-2, 2:] + 2 * a[1:-1, 2:] + a[2:, 2:]) -
                        (a[0:-2, 0:-2] + 2 * a[1:-1, 0:-2] + a[2:, 0:-2])) / (8.0 * cell_x)
                dzdy = ((a[2:, 0:-2] + 2 * a[2:, 1:-1] + a[2:, 2:]) -
                        (a[0:-2, 0:-2] + 2 * a[0:-2, 1:-1] + a[0:-2, 2:])) / (8.0 * cell_y)

                slope = np.degrees(np.arctan(np.sqrt(dzdx * dzdx + dzdy * dzdy)))

                # Store as Int16 hundredths-of-a-degree (0.01 deg precision) so
                # the file stays small; the 0.01 scale tag set above means QGIS
                # still shows real degrees. Edges / no-data -> -32768.
                out = np.full(slope.shape, OUT_NODATA_I16, dtype="int16")
                valid = ~np.isnan(slope)
                out[valid] = np.rint(np.clip(slope[valid], 0, 90) * 100.0).astype("int16")

                dst.write(out, 1, window=Window(0, r0, width, sh))
                if (r0 // STRIP) % 8 == 0:
                    print(f"  rows {r0:>6}..{r1:<6} done")

    # Convert the working GeoTIFF into a compressed COG with overviews.
    print("Converting slope to COG ...")
    if COG_PATH.exists():
        COG_PATH.unlink()
    rio_copy(str(TMP_PATH), str(COG_PATH), driver="COG",
             compress="DEFLATE", predictor=2,   # predictor 2 suits integers
             overview_resampling="average", BIGTIFF="YES")
    TMP_PATH.unlink(missing_ok=True)

    size_mb = COG_PATH.stat().st_size / 1_000_000
    print(f"COG written: {COG_PATH.name}  ({size_mb:.0f} MB)")
    print("Fingerprinting (md5) ...")
    checksum = md5_of(COG_PATH)

    # -----------------------------------------------------------------------
    # Catalogue as a DERIVED product under Geocode Spatial Solutions.
    # -----------------------------------------------------------------------
    with engine.connect() as conn:
        source_id = conn.execute(text(
            "SELECT source_id FROM metadata.sources WHERE name = 'Geocode Spatial Solutions'"
        )).scalar()
        dataset_id = conn.execute(text(
            "SELECT dataset_id FROM metadata.datasets WHERE code = 'terrain.slope'"
        )).scalar()
    if source_id is None or dataset_id is None:
        raise SystemExit("Geocode source or terrain.slope dataset missing. Run etl_04.")

    with rasterio.open(COG_PATH) as s:
        l, b, r, t = s.bounds.left, s.bounds.bottom, s.bounds.right, s.bounds.top

    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM metadata.raster_catalog
            WHERE dataset_id = :did AND variable = 'slope'
        """), {"did": dataset_id})
        conn.execute(text("""
            INSERT INTO metadata.raster_catalog
                (dataset_id, name, variable, storage_url, format, pixel_size_m,
                 band_count, nodata_value, temporal_start, temporal_end, bbox,
                 checksum, source_id, source_date, confidence)
            VALUES
                (:did, :name, 'slope', :url, 'COG', :px,
                 1, :nodata, DATE '2010-01-01', DATE '2018-12-31',
                 ST_MakeEnvelope(:l, :b, :r, :t, 4326),
                 :chk, :sid, CURRENT_DATE, 4)
        """), {
            "did": dataset_id,
            "name": ("Slope, Int16 centi-degrees (scale 0.01 = degrees), "
                     "derived from Copernicus GLO-30 DEM (Horn 3x3)."),
            "url": str(COG_PATH),
            "px": round(px * M_PER_DEG, 1),
            "nodata": OUT_NODATA_I16,
            "l": l, "b": b, "r": r, "t": t,
            "chk": checksum, "sid": source_id,
        })
        conn.execute(text("""
            UPDATE metadata.datasets SET etl_status = 'ingested', updated_at = now()
            WHERE code = 'terrain.slope'
        """))
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = 1
            WHERE run_id = :id
        """), {"id": run_id})

    print(f"\nDONE. Run {run_id} logged as success.")
    print(f"Slope catalogued: {COG_PATH}")
    print("Verify in QGIS: add the slope .tif. Flat basins ~0 deg (dark), the "
          "Rift Valley escarpments and Mt Kenya/Aberdares flanks bright/steep.")
    print("Next: etl_16 derives TWI (wetness) at ~90 m from the DEM.")

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
