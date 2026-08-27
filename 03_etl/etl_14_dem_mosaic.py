"""
============================================================================
ETL 14 - COPERNICUS GLO-30 DEM: MOSAIC + CATALOGUE (step 2 of 3 for terrain)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does:
  Takes the 96 separate 1-degree elevation tiles that etl_13 downloaded and
  stitches them into ONE seamless national elevation map, saved as a Cloud
  Optimized GeoTIFF (COG) in 06_rasters/cog/terrain/. Then it records that
  file in metadata.raster_catalog so the rest of the platform knows it exists,
  where it lives, and who to credit.

The memory-safe method (the important idea):
  A national 30 m grid is about 28,800 x 35,100 pixels. Held all at once that
  is ~4 GB of RAM, enough to freeze a laptop. So we DO NOT load it all. We:
    1. work out the size of the full national canvas from the tile edges,
    2. create an empty GeoTIFF of that size on DISK,
    3. copy tiles in ONE AT A TIME, each into its correct window,
       so only ~40 MB is in memory at any moment,
    4. convert that stitched file into a compressed COG with overviews,
    5. delete the big temporary file.
  Step 4 needs the temp file plus the COG on disk briefly, so make sure E:
  has a few GB free. Both are removed/finalised by the end.

New tool needed (install once, venv active):
  pip install rasterio
  (rasterio bundles the GDAL engine, so there is no separate GDAL install.)

Licensing note carried onto the catalogue row (Copernicus, required):
  produced using Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and
  (c) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by
  the European Union and ESA; all rights reserved.

Note this is a DSM (surface model: includes tree canopy and buildings), not a
bare-earth DTM. Good enough for slope and relative wetness; confidence 4.

How to run (from 03_etl with venv active, after: pip install rasterio):
  python etl_14_dem_mosaic.py
============================================================================
"""

import os
import sys
import hashlib
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import rasterio
    from rasterio.windows import Window
except ImportError:
    sys.exit("ERROR: rasterio is not installed. With the venv active run:\n"
             "    pip install rasterio\n"
             "then run this script again.")

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
PIPELINE = "etl_14_dem_mosaic"

RAW_DIR = BASE / "data" / "raw" / "terrain" / "copernicus_glo30"
COG_DIR = PROJECT / "06_rasters" / "cog" / "terrain"
COG_DIR.mkdir(parents=True, exist_ok=True)

COG_NAME = "terrain_dem_copernicus_glo30_2021.tif"
COG_PATH = COG_DIR / COG_NAME
TMP_PATH = RAW_DIR / "_mosaic_tmp.tif"   # big scratch file, deleted at the end

ATTRIBUTION = (
    "produced using Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and "
    "(c) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by "
    "the European Union and ESA; all rights reserved."
)


def md5_of(path, chunk=8 * 1024 * 1024):
    """Fingerprint the finished file so we can detect corruption later."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Connect + open the run record
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
    tiles = sorted(RAW_DIR.glob("Copernicus_DSM_COG_10_*_DEM.tif"))
    if not tiles:
        raise SystemExit(f"No tiles found in {RAW_DIR}. Run etl_13 first.")
    print(f"Found {len(tiles)} tiles to stitch.")

    # -----------------------------------------------------------------------
    # 1. Measure the full national canvas from every tile's edges, and confirm
    #    all tiles share one pixel grid (they do: all EPSG:4326, 1 arc-second,
    #    aligned to whole degrees, because Kenya sits near the equator).
    # -----------------------------------------------------------------------
    lefts, rights, tops, bottoms = [], [], [], []
    ref = None
    for t in tiles:
        with rasterio.open(t) as src:
            b = src.bounds
            lefts.append(b.left); rights.append(b.right)
            tops.append(b.top); bottoms.append(b.bottom)
            if ref is None:
                ref = {
                    "crs": src.crs,
                    "dtype": src.dtypes[0],
                    "nodata": src.nodata,
                    "px": src.transform.a,        # pixel width  (deg, +)
                    "py": -src.transform.e,       # pixel height (deg, +)
                }
    out_left, out_right = min(lefts), max(rights)
    out_top, out_bottom = max(tops), min(bottoms)
    px, py = ref["px"], ref["py"]
    width = int(round((out_right - out_left) / px))
    height = int(round((out_top - out_bottom) / py))
    out_transform = rasterio.transform.from_origin(out_left, out_top, px, py)
    print(f"National canvas: {width} x {height} px "
          f"(~{width * height / 1e9:.2f} billion pixels), "
          f"pixel ~{px * 111320:.1f} m")

    # -----------------------------------------------------------------------
    # 2/3. Create the empty canvas on disk, then paste tiles in one by one.
    # -----------------------------------------------------------------------
    profile = {
        "driver": "GTiff",
        "dtype": ref["dtype"],
        "count": 1,
        "crs": ref["crs"],
        "transform": out_transform,
        "width": width,
        "height": height,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "bigtiff": "YES",       # the file is over 4 GB of addressable space
    }
    if ref["nodata"] is not None:
        profile["nodata"] = ref["nodata"]

    print("Stitching tiles into a temporary national GeoTIFF ...")
    with rasterio.open(TMP_PATH, "w", **profile) as dst:
        for i, t in enumerate(tiles, 1):
            with rasterio.open(t) as src:
                # Where does this tile's top-left corner land in the canvas?
                col_off = int(round((src.bounds.left - out_left) / px))
                row_off = int(round((out_top - src.bounds.top) / py))
                window = Window(col_off, row_off, src.width, src.height)
                dst.write(src.read(1), 1, window=window)  # ~one tile in memory
            if i % 12 == 0 or i == len(tiles):
                print(f"  placed {i}/{len(tiles)} tiles")

    # -----------------------------------------------------------------------
    # 4. Convert the stitched file into a proper COG (compressed + overviews).
    #    rasterio.shutil.copy with the COG driver streams block-by-block, so
    #    this stays memory-light too.
    # -----------------------------------------------------------------------
    print("Converting to Cloud Optimized GeoTIFF (compress + overviews) ...")
    from rasterio.shutil import copy as rio_copy
    if COG_PATH.exists():
        COG_PATH.unlink()
    rio_copy(
        str(TMP_PATH), str(COG_PATH),
        driver="COG",
        compress="DEFLATE",
        predictor=3,            # best for floating-point elevation
        overview_resampling="average",
        BIGTIFF="YES",
    )

    # 5. Bin the big temporary file.
    TMP_PATH.unlink(missing_ok=True)

    size_mb = COG_PATH.stat().st_size / 1_000_000
    print(f"COG written: {COG_PATH.name}  ({size_mb:.0f} MB)")
    print("Fingerprinting the file (md5) ...")
    checksum = md5_of(COG_PATH)

    # -----------------------------------------------------------------------
    # 6. Catalogue it. Reuse the Copernicus source and the terrain.dem dataset
    #    already loaded by etl_04. Idempotent: clear any prior elevation row
    #    for this dataset first, so reruns replace cleanly.
    # -----------------------------------------------------------------------
    with engine.connect() as conn:
        source_id = conn.execute(text(
            "SELECT source_id FROM metadata.sources WHERE name = 'Copernicus DEM'"
        )).scalar()
        dataset_id = conn.execute(text(
            "SELECT dataset_id FROM metadata.datasets WHERE code = 'terrain.dem'"
        )).scalar()
    if source_id is None or dataset_id is None:
        raise SystemExit("Copernicus DEM source or terrain.dem dataset missing "
                         "from metadata. Run etl_04 (catalogue loader) first.")

    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM metadata.raster_catalog
            WHERE dataset_id = :did AND variable = 'elevation'
        """), {"did": dataset_id})
        conn.execute(text("""
            INSERT INTO metadata.raster_catalog
                (dataset_id, name, variable, storage_url, format, pixel_size_m,
                 band_count, nodata_value, temporal_start, temporal_end, bbox,
                 checksum, source_id, source_date, confidence)
            VALUES
                (:did, :name, 'elevation', :url, 'COG', :px,
                 1, :nodata, DATE '2010-01-01', DATE '2018-12-31',
                 ST_MakeEnvelope(:l, :b, :r, :t, 4326),
                 :chk, :sid, DATE '2021-01-01', 4)
        """), {
            "did": dataset_id,
            "name": "Copernicus GLO-30 DEM Kenya (DSM). " + ATTRIBUTION,
            "url": str(COG_PATH),
            "px": round(px * 111320, 1),
            "nodata": ref["nodata"],
            "l": out_left, "b": out_bottom, "r": out_right, "t": out_top,
            "chk": checksum,
            "sid": source_id,
        })
        conn.execute(text("""
            UPDATE metadata.datasets SET etl_status = 'ingested', updated_at = now()
            WHERE code = 'terrain.dem'
        """))
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = 1
            WHERE run_id = :id
        """), {"id": run_id})

    print(f"\nDONE. Run {run_id} logged as success.")
    print(f"National DEM catalogued: {COG_PATH}")
    print("Verify: QGIS -> add the .tif; it should shade Kenya's whole relief "
          "(bright Mt Kenya/Aberdares/Rift highlands, dark coast and Turkana).")
    print("Next: etl_15 derives slope + TWI from this DEM (no new download).")

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
