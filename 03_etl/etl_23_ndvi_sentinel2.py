"""
============================================================================
ETL 23 - NDVI FROM SENTINEL-2 GEOMEDIAN (satellite.ndvi) at ~40 m
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does:
  Finds Digital Earth Africa's Sentinel-2 annual geomedian tiles covering
  Kenya, reads the red and near-infrared bands, computes NDVI itself, mosaics
  the result and catalogues it as satellite.ndvi.

WHY NDVI MATTERS MORE THAN IT LOOKS
  This is not a "nice to have" vegetation picture. It is the fix for a hole we
  found in etl_19. WorldCover mapped only 4.46% of Kenya as cropland, because
  its cropland class under-detects smallholder mosaic farming: small mixed
  plots with scrub and trees between them get classified as shrubland. That is
  most of Kenyan agriculture. So land cover alone would let us tell a buyer
  "this is not farmland" about a shamba someone farms.
  NDVI does not classify anything. It measures how much living vegetation is
  actually there, from the physics: healthy leaves reflect near-infrared
  strongly and absorb red. Cultivated ground shows up as vegetation regardless
  of whether a classifier recognised the field pattern.

WHY A GEOMEDIAN AND NOT A DATE
  A single satellite image tells you about one day, including its clouds. A
  geomedian is the statistical centre of every clear observation in a year, so
  it is cloud-free by construction and represents the typical condition rather
  than a moment. This is the same reasoning that made us average 30 years of
  CHIRPS instead of taking last year's rainfall.

WHY SENTINEL-2 AND NOT THE LANDSAT NDVI CLIMATOLOGY
  DE Africa also publishes a 1984-2020 Landsat NDVI climatology, which would
  have been the closer parallel to our rainfall normal. We did not use it, on
  their own advice: their specification warns that because of sparse Landsat 5
  coverage and persistent cloud over equatorial Africa, the baseline quality
  is poor there and it should not be used where clear-observation counts fall
  below about 30. Kenya IS equatorial Africa. Sentinel-2 from 2017 onward has
  dense enough observations that the problem does not arise.

RESOLUTION: ~40 m, DELIBERATELY, AND HERE IS THE ARITHMETIC
  The source is 10 m. Kenya at 10 m across two bands is tens of gigabytes,
  which this connection cannot fetch in a working session. We therefore read
  at 1/4 resolution DIRECTLY FROM THE COG OVERVIEWS, which fetches roughly
  1/16 of the bytes rather than downloading everything and throwing most away.
  NDVI is a landscape signal, not an edge-detection problem, and 40 m still
  resolves a quarter-acre plot into about six pixels. Set DOWNSAMPLE = 1 below
  if you ever want the full 10 m and have the hours.

TILE DISCOVERY VIA STAC, NOT GUESSWORK
  Three times this session, hardcoding a remote layout cost us a run. So this
  script asks DE Africa's STAC catalogue which tiles cover Kenya and what
  their asset URLs are, prints what it found, and stops with instructions if
  the answer is empty. It also prints the asset key names of the first item,
  so if the band naming has changed we see it immediately.

GRID ALIGNMENT (the etl_19 lesson, applied in advance)
  The canvas is snapped to the 96 km source tile grid, so every tile edge
  lands exactly on a block boundary. Combined with a 480 pixel block size
  (96,000 m / 40 m = 2,400 px per tile, and 2,400 / 480 = 5 exactly) this means
  no tile ever writes into a block another tile has already written, which is
  what makes writing a COMPRESSED mosaic tile by tile safe here.

How to run (from 03_etl with venv active):
  python etl_23_ndvi_sentinel2.py
============================================================================
"""

import os
import sys
import time
import json
import math
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import rasterio
    from rasterio.crs import CRS
    from rasterio.windows import Window, from_bounds
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    from rasterio.shutil import copy as rio_copy
except ImportError:
    sys.exit("ERROR: rasterio missing. With venv active: pip install rasterio")

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
PIPELINE = "etl_23_ndvi_sentinel2"

RAW_DIR = BASE / "data" / "raw" / "satellite" / "ndvi"
RAW_DIR.mkdir(parents=True, exist_ok=True)
COG_DIR = PROJECT / "06_rasters" / "cog" / "satellite"
COG_DIR.mkdir(parents=True, exist_ok=True)

NATIVE = RAW_DIR / "native_ndvi_6933.tif"
TMP = RAW_DIR / "_ndvi_tmp.tif"

STAC = "https://explorer.digitalearth.africa/stac/search"
COLLECTION = "gm_s2_annual"
YEARS_TO_TRY = [2024, 2023, 2022, 2021, 2020, 2019]

DOWNSAMPLE = 4                 # 10 m -> 40 m. Set to 1 for full resolution.
TILE_M = 96_000                # DE Africa tile size in metres
PAD_DEG = 0.05
SCALE = 0.0001                 # Int16 storage: NDVI = stored * 0.0001
NODATA = -32768
BLOCK = 480                    # divides 2,400 px per tile exactly

RED_KEYS = ["B04", "b04", "red", "nbart_red", "band_04"]
NIR_KEYS = ["B08", "b08", "nir", "nir_1", "nbart_nir_1", "band_08"]

ATTRIB = ("Digital Earth Africa Sentinel-2 Annual GeoMAD (geomedian), "
          "CC-BY-4.0. Contains modified Copernicus Sentinel data. "
          "Digital Earth Africa, https://www.digitalearthafrica.org.")


def md5_of(path, chunk=8 * 1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def stac_search(bbox, year, limit=400):
    """Ask DE Africa which tiles cover our bbox in this year."""
    body = json.dumps({
        "collections": [COLLECTION],
        "bbox": list(bbox),
        "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
        "limit": limit,
    }).encode()
    req = urllib.request.Request(
        STAC, data=body,
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "LIP-ETL/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def pick_asset(assets, keys):
    """Find a band asset by any of several plausible names."""
    lower = {k.lower(): k for k in assets}
    for k in keys:
        if k.lower() in lower:
            return assets[lower[k.lower()]]
    return None


def href_to_vsicurl(href):
    if href.startswith("s3://"):
        rest = href[5:]
        bucket, _, key = rest.partition("/")
        href = f"https://{bucket}.s3.af-south-1.amazonaws.com/{key}"
    return "/vsicurl/" + href


load_dotenv(BASE / ".env")
pw = os.getenv("DB_PASSWORD")
if not pw or pw == "put_your_password_here":
    sys.exit("ERROR: edit the .env file and set DB_PASSWORD first.")

engine = create_engine(
    f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
    f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
    f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
print("Connected to database:", os.getenv("DB_NAME", "land_intelligence_kenya"))

with engine.begin() as conn:
    run_id = conn.execute(text("""
        INSERT INTO metadata.etl_runs (pipeline, started_at, run_status)
        VALUES (:p, now(), 'running') RETURNING run_id
    """), {"p": PIPELINE}).scalar()
print(f"ETL run opened (run_id={run_id})")

GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    GDAL_HTTP_MULTIRANGE="NO",          # session 4 lesson, do not change
    GDAL_HTTP_MAX_RETRY="10",
    GDAL_HTTP_RETRY_DELAY="2",
    GDAL_HTTP_TIMEOUT="180",
    GDAL_CACHEMAX=512,
    CPL_VSIL_CURL_CACHE_SIZE=268435456,
    VSI_CACHE="TRUE",
    VSI_CACHE_SIZE=134217728,
)

try:
    with engine.connect() as conn:
        xmin, xmax, ymin, ymax = conn.execute(text("""
            SELECT ST_XMin(e), ST_XMax(e), ST_YMin(e), ST_YMax(e)
            FROM (SELECT ST_Extent(geom) AS e FROM admin.country) t
        """)).one()
        source_id = conn.execute(text(
            "SELECT source_id FROM metadata.sources "
            "WHERE name IN ('Sentinel-2','Digital Earth Africa') LIMIT 1"
        )).scalar()
        dataset_id = conn.execute(text(
            "SELECT dataset_id FROM metadata.datasets "
            "WHERE code = 'satellite.ndvi'")).scalar()
    if dataset_id is None:
        raise SystemExit("satellite.ndvi dataset missing. Run etl_04 first.")
    if source_id is None:
        raise SystemExit(
            "No source row named 'Sentinel-2' or 'Digital Earth Africa' in "
            "metadata.sources. Add one to 02_data_catalogue/sources.csv and "
            "rerun etl_04, so this layer can be attributed properly.")

    xmin, xmax = float(xmin) - PAD_DEG, float(xmax) + PAD_DEG
    ymin, ymax = float(ymin) - PAD_DEG, float(ymax) + PAD_DEG
    print(f"Kenya bbox (padded): lon {xmin:.3f}..{xmax:.3f}, "
          f"lat {ymin:.3f}..{ymax:.3f}")

    # -----------------------------------------------------------------------
    # 1. Ask STAC what exists. Never guess a remote layout.
    # -----------------------------------------------------------------------
    print(f"\nAsking DE Africa's STAC catalogue for '{COLLECTION}' tiles ...")
    items, year = [], None
    for y in YEARS_TO_TRY:
        try:
            res = stac_search((xmin, ymin, xmax, ymax), y)
        except Exception as e:
            print(f"  {y}: request failed ({type(e).__name__})")
            continue
        feats = res.get("features", [])
        print(f"  {y}: {len(feats)} tiles")
        if feats:
            items, year = feats, y
            break
    if not items:
        raise SystemExit(
            "STAC returned no tiles for any year tried.\n"
            "Check the collection name at "
            "https://explorer.digitalearth.africa/products/gm_s2_annual\n"
            "and the STAC endpoint at https://explorer.digitalearth.africa/stac\n"
            "Nothing was downloaded and nothing was catalogued.")
    print(f"\nUsing year {year}: {len(items)} tiles cover Kenya.")
    print(f"  asset keys on the first tile: "
          f"{sorted(items[0].get('assets', {}).keys())}")

    pairs = []
    for it in items:
        a = it.get("assets", {})
        red, nir = pick_asset(a, RED_KEYS), pick_asset(a, NIR_KEYS)
        if not red or not nir:
            continue
        pairs.append((it.get("id", "?"),
                      href_to_vsicurl(red["href"]),
                      href_to_vsicurl(nir["href"])))
    if not pairs:
        raise SystemExit(
            f"Tiles were found but no red/NIR assets matched the expected "
            f"names.\nAsset keys present: "
            f"{sorted(items[0].get('assets', {}).keys())}\n"
            f"Add the correct names to RED_KEYS and NIR_KEYS at the top of "
            f"this script.")
    print(f"  {len(pairs)} tiles have both red and NIR bands.")

    # -----------------------------------------------------------------------
    # 2. Build the national canvas in the SOURCE projection
    # -----------------------------------------------------------------------
    if NATIVE.exists() and NATIVE.stat().st_size > 1_000_000:
        print(f"\nAlready have {NATIVE.name}, skipping the fetch.")
    else:
        with rasterio.Env(**GDAL_ENV):
            with rasterio.open(pairs[0][1]) as s0:
                src_crs = s0.crs
                px_native = abs(s0.transform.a)
                print(f"\nSource: {s0.width} x {s0.height} px, {s0.dtypes[0]}, "
                      f"nodata {s0.nodata}, {px_native:.0f} m, crs {src_crs}")
                src_nodata = s0.nodata
                overviews = s0.overviews(1)
                print(f"  overviews available: {overviews}")
                if DOWNSAMPLE > 1 and not overviews:
                    print("  WARNING: no overviews on the source, so reading at "
                          "reduced resolution will\n  fetch FULL resolution "
                          "bytes and throw most away. Expect it to be slow.")

            px = px_native * DOWNSAMPLE
            bx0, by0, bx1, by1 = transform_bounds(
                "EPSG:4326", src_crs, xmin, ymin, xmax, ymax, densify_pts=51)
            # Snap the canvas to the 96 km tile grid so every tile edge lands
            # on a block boundary (see the header note on grid alignment).
            x0 = math.floor(bx0 / TILE_M) * TILE_M
            y1 = math.ceil(by1 / TILE_M) * TILE_M
            x1 = math.ceil(bx1 / TILE_M) * TILE_M
            y0 = math.floor(by0 / TILE_M) * TILE_M
            W = int(round((x1 - x0) / px))
            H = int(round((y1 - y0) / px))
            print(f"  canvas: {W:,} x {H:,} px at {px:.0f} m "
                  f"({W*H/1e6:.0f} million)")

            prof = {
                "driver": "GTiff", "dtype": "int16", "count": 1,
                "crs": src_crs,
                "transform": rasterio.Affine(px, 0, x0, 0, -px, y1),
                "width": W, "height": H, "nodata": NODATA,
                "tiled": True, "blockxsize": BLOCK, "blockysize": BLOCK,
                "compress": "DEFLATE", "predictor": 2, "bigtiff": "YES",
            }

            t_start = time.time()
            with rasterio.Env(**GDAL_ENV):
                with rasterio.open(NATIVE, "w", **prof) as dst:
                    for i, (tid, rurl, nurl) in enumerate(pairs, 1):
                        arr = None
                        for attempt in range(1, 9):
                            try:
                                with rasterio.open(rurl) as rs, \
                                        rasterio.open(nurl) as ns:
                                    ow = rs.width // DOWNSAMPLE
                                    oh = rs.height // DOWNSAMPLE
                                    red = rs.read(
                                        1, out_shape=(oh, ow),
                                        resampling=Resampling.average
                                    ).astype("float32")
                                    nir = ns.read(
                                        1, out_shape=(oh, ow),
                                        resampling=Resampling.average
                                    ).astype("float32")
                                    tx, ty = rs.transform.c, rs.transform.f
                                break
                            except rasterio.errors.RasterioIOError:
                                if attempt == 8:
                                    raise
                                print(f"    ... {tid} hiccup, retry {attempt}",
                                      flush=True)
                                time.sleep(min(3 * attempt, 20))

                        # NDVI = (NIR - red) / (NIR + red). Guard the divide:
                        # where both bands are zero or nodata the denominator
                        # is zero, and 0/0 is not "no vegetation", it is "no
                        # observation". Those become nodata, not zero.
                        valid = np.ones(red.shape, dtype=bool)
                        if src_nodata is not None:
                            valid &= (red != src_nodata) & (nir != src_nodata)
                        denom = nir + red
                        valid &= denom > 0
                        out = np.full(red.shape, NODATA, dtype="int16")
                        ndvi = np.zeros(red.shape, dtype="float32")
                        np.divide(nir - red, denom, out=ndvi, where=valid)
                        np.clip(ndvi, -1.0, 1.0, out=ndvi)
                        out[valid] = np.rint(ndvi[valid] / SCALE).astype("int16")

                        col = int(round((tx - x0) / px))
                        row = int(round((y1 - ty) / px))
                        cf, rf = max(0, col), max(0, row)
                        ct, rt = min(W, col + ow), min(H, row + oh)
                        if ct > cf and rt > rf:
                            dst.write(out[rf - row:rt - row, cf - col:ct - col],
                                      1, window=Window(cf, rf, ct - cf, rt - rf))
                        del red, nir, denom, ndvi, out, valid

                        el = time.time() - t_start
                        frac = i / len(pairs)
                        print(f"  [{i:>3}/{len(pairs)}] {tid[:28]:28} "
                              f"{100*frac:5.1f}%  {el/60:.1f} min  "
                              f"ETA {(el/frac - el)/60:.0f} min", flush=True)
        print(f"  saved {NATIVE.name} ({NATIVE.stat().st_size/1e6:.0f} MB)")

    # -----------------------------------------------------------------------
    # 3. Reproject locally to EPSG:4326 (fetch-then-reproject, etl_17 pattern)
    # -----------------------------------------------------------------------
    print("\nReprojecting locally to EPSG:4326 ...")
    stats = {"n": 0, "sum": 0.0, "min": 32767, "max": -32768}
    with rasterio.open(NATIVE) as src:
        with WarpedVRT(src, crs="EPSG:4326", resampling=Resampling.bilinear,
                       src_nodata=NODATA, nodata=NODATA) as vrt:
            win = from_bounds(xmin, ymin, xmax, ymax, vrt.transform)
            win = win.round_offsets().round_lengths()
            c0, r0 = max(0, int(win.col_off)), max(0, int(win.row_off))
            w = min(int(win.width), vrt.width - c0)
            h = min(int(win.height), vrt.height - r0)
            px_deg = vrt.transform.a
            print(f"  output: {w:,} x {h:,} px (~{px_deg*111320:.0f} m)")
            prof = {
                "driver": "GTiff", "dtype": "int16", "count": 1,
                "crs": "EPSG:4326",
                "transform": vrt.window_transform(Window(c0, r0, w, h)),
                "width": w, "height": h, "nodata": NODATA,
                "tiled": True, "blockxsize": 512, "blockysize": 512,
                "compress": "DEFLATE", "predictor": 2, "bigtiff": "YES",
            }
            with rasterio.open(TMP, "w", **prof) as dst:
                dst.scales = (SCALE,)
                for r in range(0, h, 512):
                    rh = min(512, h - r)
                    a = vrt.read(1, window=Window(c0, r0 + r, w, rh))
                    dst.write(a, 1, window=Window(0, r, w, rh))
                    good = a[a != NODATA]
                    if good.size:
                        stats["n"] += good.size
                        stats["sum"] += float(good.sum())
                        stats["min"] = min(stats["min"], int(good.min()))
                        stats["max"] = max(stats["max"], int(good.max()))
                    del a, good

    if stats["n"] == 0:
        raise SystemExit("Every pixel is nodata. Nothing usable was produced.")
    mn, mx = stats["min"] * SCALE, stats["max"] * SCALE
    mean = (stats["sum"] / stats["n"]) * SCALE
    print(f"\n  NDVI: min {mn:.3f}  max {mx:.3f}  mean {mean:.3f}  "
          f"({stats['n']:,} pixels)")
    print("  Expect: water and bare rock near or below 0, desert 0.05-0.15,")
    print("  savanna 0.2-0.4, cropland 0.4-0.6, closed forest 0.7-0.9.")
    print("  A national mean around 0.3-0.45 is right for Kenya, which is")
    print("  mostly rangeland with a green west and highlands.")
    if not (-1.0 <= mn <= 1.0 and -1.0 <= mx <= 1.0):
        raise SystemExit("NDVI outside the physical range -1 to 1. "
                         "Refusing to catalogue.")
    if mean < 0.05 or mean > 0.75:
        raise SystemExit(f"National mean NDVI of {mean:.3f} is not credible "
                         f"for Kenya. Refusing to catalogue.")

    print("\n  Converting to COG ...")
    cog_name = f"satellite_ndvi_s2geomedian_{int(px_deg*111320)}m_{year}.tif"
    cog_path = COG_DIR / cog_name
    if cog_path.exists():
        cog_path.unlink()
    rio_copy(str(TMP), str(cog_path), driver="COG", compress="DEFLATE",
             predictor=2, overview_resampling="average", BIGTIFF="YES")
    TMP.unlink(missing_ok=True)
    print(f"  COG: {cog_path.name} ({cog_path.stat().st_size/1e6:.0f} MB)")

    with rasterio.open(cog_path) as s:
        b = s.bounds

    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM metadata.raster_catalog
            WHERE dataset_id = :did AND variable = 'ndvi'
        """), {"did": dataset_id})
        conn.execute(text("""
            INSERT INTO metadata.raster_catalog
                (dataset_id, name, variable, storage_url, format, pixel_size_m,
                 band_count, nodata_value, temporal_start, temporal_end, bbox,
                 checksum, source_id, source_date, confidence)
            VALUES
                (:did, :name, 'ndvi', :url, 'COG', :px, 1, :nodata,
                 :ts, :te, ST_MakeEnvelope(:l, :b, :r, :t, 4326),
                 :chk, :sid, CURRENT_DATE, 4)
        """), {
            "did": dataset_id,
            "name": (f"NDVI from the Sentinel-2 annual geomedian, {year}. "
                     f"Int16 with scale {SCALE}: NDVI = stored * {SCALE}. "
                     f"Computed as (NIR - red)/(NIR + red) from bands B08 and "
                     f"B04. Cloud-free by construction (geomedian of all clear "
                     f"observations in the year). Read at 1/{DOWNSAMPLE} of "
                     f"the native 10 m. " + ATTRIB),
            "url": str(cog_path), "px": round(px_deg * 111320, 1),
            "nodata": NODATA,
            "ts": f"{year}-01-01", "te": f"{year}-12-31",
            "l": float(b.left), "b": float(b.bottom),
            "r": float(b.right), "t": float(b.top),
            "chk": md5_of(cog_path), "sid": source_id,
        })
        conn.execute(text("""
            UPDATE metadata.datasets SET etl_status='ingested', updated_at=now()
            WHERE code = 'satellite.ndvi'
        """))
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = 1
            WHERE run_id = :id
        """), {"id": run_id})

    print(f"\nDONE. Run {run_id} logged as success.")
    print("THE CHECK THAT MATTERS NEXT: compare NDVI against WorldCover "
          "cropland.\nIf areas WorldCover called shrubland show cropland-level "
          "NDVI, that is the\nsmallholder farming WorldCover missed, and it is "
          "the reason this layer exists.")

# BaseException, NOT Exception, and this is load-bearing.
# This script's own guards raise SystemExit, and Ctrl+C raises
# KeyboardInterrupt. Both inherit from BaseException, so an
# `except Exception` handler never fires for them and the
# metadata.etl_runs row is left at 'running' forever. That bug left 12
# orphan rows across a month of work, including runs PROGRESS.md
# documents as failures. The trailing `raise` is unchanged: this logs
# the failure and then gets out of the way.
except BaseException as exc:
    TMP.unlink(missing_ok=True)
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'failed', error_message = :e
            WHERE run_id = :id
        """), {"e": str(exc)[:2000], "id": run_id})
    raise
