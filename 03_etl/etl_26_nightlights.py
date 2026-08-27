r"""
============================================================================
ETL 26 - demographics.nightlights (NASA Black Marble VNP46A4) - THE LAST P1
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHAT IT ANSWERS
  "Is the area developing?" Nightlights are the standard satellite proxy for
  economic activity, and the catalogue is explicit that THE TREND IS THE
  SIGNAL, not the level. A bright ward is already developed; a ward whose
  radiance has doubled in five years is where value is moving. So this loads
  SEVERAL YEARS and fits a trend rather than one epoch.

  Pairs with satellite.builtup: GHSL measures roof area, VIIRS measures
  activity. A new estate appears in GHSL before anyone lives there; the
  lights come on when they do.

WHY BLACK MARBLE AND NOT EOG's VNL
  The first version of this script targeted EOG VNL v2.2. EOG has moved
  programmatic OpenID access behind a paid subscription: eogauth.mines.edu
  now returns nginx 403 on every token endpoint while eogdata returns 401.
  A free EOG account no longer opens the API.

  NASA Black Marble is the same instrument (VIIRS DNB) and cadence, and is
  better for us on four counts:
    1. LICENCE. NASA Earth Science data is free public use with no
       commercial restriction. Google Earth Engine's free tier is
       NONCOMMERCIAL ONLY and this is a commercial product, so GEE would
       have been the WDPA trap a fourth time.
    2. SIZE. VNL ships one ~1.5 GB global file per year, untiled. VNP46A4 is
       tiled 10x10 degrees, so Kenya needs four tiles per year at tens of MB.
       On a link that failed four different ways building etl_25, that is the
       difference between feasible and not.
    3. FIT. Download -> local COG -> catalogue -> zonal stats in PostGIS is
       the pattern every other raster here follows. GEE would move
       computation off-machine and put provenance on someone else's servers.
    4. CORRECTION. VNP46A4 is BRDF-adjusted for lunar illumination,
       atmosphere, terrain and vegetation. Since the TREND is the signal,
       removing lunar and seasonal artefacts matters more than absolute
       radiance: we compare a ward against itself across years, which is
       exactly where those artefacts bite.

  Cost of the switch, stated plainly: HDF5 rather than GeoTIFF, so tiles must
  be mosaicked and the subdataset located; and VNL has the longer track
  record in the economics literature, so published nightlights elasticities
  will not be directly transferable.

NOTHING IS HARDCODED THAT CAN BE ASKED
  This session lost several runs to values written from memory (a wrong OAuth
  secret, wrong column names, a misread field). So: the tile list is computed
  from Kenya's own bbox, the file names come from the LAADS listing, and the
  HDF5 subdataset and its scale factor are DISCOVERED from the file and
  printed before use. --probe-only exercises all of that without downloading.

ACCESS
  Free NASA Earthdata account, then a LAADS App Key:
    1. register at https://urs.earthdata.nasa.gov/users/new
    2. generate a token at
       https://ladsweb.modaps.eosdis.nasa.gov/profile/#generate-token
    3. put LAADS_TOKEN=<token> in 03_etl/.env

How to run (from 03_etl with venv active):
  python etl_26_nightlights.py --probe-only
  python etl_26_nightlights.py
============================================================================
"""

import os
import sys
import re
import json
import time
import socket
import hashlib
import urllib.parse
import urllib.request
import urllib.error
import http.client
from pathlib import Path

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import warnings

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.transform import from_origin
    from rasterio.shutil import copy as rio_copy
    from rasterio.features import geometry_mask
except ImportError as e:
    sys.exit(f"ERROR: missing dependency ({e}). With venv active: "
             f"pip install rasterio")

try:
    import geopandas as gpd
except ImportError:
    sys.exit("ERROR: geopandas missing. With venv active: pip install geopandas")

# EXPECTED, NOT A PROBLEM: the Black Marble HDF5 files carry no geotransform.
# We build the grid from the tile indices instead, which is exact by
# definition (10 degrees / 2400 px). Silenced so that a warning printed on
# every one of 20 tiles does not bury a message that matters.
warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
PIPELINE = "etl_26_nightlights"
RAW_DIR = BASE / "data" / "raw" / "nightlights"
RAW_DIR.mkdir(parents=True, exist_ok=True)
COG_DIR = PROJECT / "06_rasters" / "cog" / "demographics"
COG_DIR.mkdir(parents=True, exist_ok=True)

LAADS = "https://ladsweb.modaps.eosdis.nasa.gov"
# ARCHIVESET 5200, read from the LAADS product page for VNP46A4, not from
# memory. The first version of this script said 5000, which is a real
# ArchiveSet but holds VNP01 / TLE_VGD / USNOPW_VGD and no Black Marble at
# all. Overridable, because an archive number is exactly the sort of value
# that moves.
#   https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/
#   products/VNP46A4/  ->  "ArchiveSet(s): 5200"
COLLECTION = os.getenv("LAADS_COLLECTION", "5200")
PRODUCT = "VNP46A4"          # yearly, BRDF-adjusted, 15 arcsec, ~92 MB/tile

# VNP46A4 grid: 10 degree tiles, 2400x2400 px, so 15 arcsec exactly.
TILE_DEG = 10.0
TILE_PX = 2400
PIX = TILE_DEG / TILE_PX     # 1/240 degree

# Preference order for the composite. AllAngle uses every viewing angle and
# is the fuller product; NearNadir is cleaner but sparser. Whichever exists
# is used and printed.
SDS_PREFER = ["AllAngle_Composite_Snow_Free", "NearNadir_Composite_Snow_Free"]

YEARS = [int(y) for y in os.getenv(
    "NIGHTLIGHT_YEARS", "2015,2019,2022,2023,2024").split(",")]

PAD_DEG = 0.05
LIT_THRESHOLD = 0.5          # nW/cm2/sr above which a cell counts as lit
CHUNK = 2 * 1024 * 1024
ATTRIB = ("NASA Black Marble VNP46A4 (VIIRS/NPP Lunar BRDF-Adjusted "
          "Nighttime Lights Yearly L3 Global 15 arc second). Roman, M.O. et "
          "al. (2018) NASA's Black Marble nighttime lights product suite, "
          "Remote Sensing of Environment 210, 113-143. Courtesy NASA "
          "Earthdata / LAADS DAAC.")


def token():
    t = os.getenv("LAADS_TOKEN") or os.getenv("EARTHDATA_TOKEN")
    return t.strip() if t else None


def http_get(url, tok, timeout=120, extra=None):
    h = {"User-Agent": "LIP-ETL/1.0"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    if extra:
        h.update(extra)
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=h), timeout=timeout)


def fetch_text(url, tok, tries=4):
    last = None
    for i in range(1, tries + 1):
        try:
            with http_get(url, tok) as r:
                return r.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return None, f"HTTP {e.code}: token rejected or missing"
            last = e
        except Exception as e:
            last = e
        if i < tries:
            time.sleep(3 * i)
    return None, f"{last}"


def tiles_for(xmin, ymin, xmax, ymax):
    """Black Marble tile indices covering a bbox.

    h counts east from 180W, v counts south from 90N, both in 10 degree
    steps. Computed from Kenya's own extent rather than written down, so a
    change to admin.country cannot silently leave a tile out.
    """
    h0, h1 = int((xmin + 180) // 10), int((xmax + 180) // 10)
    v0, v1 = int((90 - ymax) // 10), int((90 - ymin) // 10)
    return [(h, v) for v in range(v0, v1 + 1) for h in range(h0, h1 + 1)]


def tile_transform(h, v):
    return from_origin(-180.0 + h * TILE_DEG, 90.0 - v * TILE_DEG, PIX, PIX)


def list_year(year, tok):
    """Ask LAADS what files exist for this year. JSON API first, HTML second."""
    api = (f"{LAADS}/api/v2/content/details/allData/{COLLECTION}/{PRODUCT}/"
           f"{year}/001?fields=all&formats=json")
    txt, err = fetch_text(api, tok)
    out = {}
    if txt:
        try:
            js = json.loads(txt)
            items = js.get("content", js if isinstance(js, list) else [])
            for it in items:
                name = it.get("name") or it.get("fileName") or ""
                if not name.endswith(".h5"):
                    continue
                m = re.search(r"\.h(\d{2})v(\d{2})\.", name)
                if m:
                    link = it.get("downloadsLink") or (
                        f"{LAADS}/archive/allData/{COLLECTION}/{PRODUCT}/"
                        f"{year}/001/{name}")
                    out[(int(m.group(1)), int(m.group(2)))] = (name, link)
        except json.JSONDecodeError:
            pass
    if not out:
        arch = (f"{LAADS}/archive/allData/{COLLECTION}/{PRODUCT}/{year}/001/")
        txt, err = fetch_text(arch, tok)
        if txt:
            for name in set(re.findall(r'(VNP46A4\.[A-Za-z0-9.]+\.h5)', txt)):
                m = re.search(r"\.h(\d{2})v(\d{2})\.", name)
                if m:
                    out[(int(m.group(1)), int(m.group(2)))] = (
                        name, arch + name)
    return out, err


def h5_ok(path):
    """Does the file actually open as HDF5 with subdatasets?

    A SIZE CHECK IS NOT AN INTEGRITY CHECK. Run 71 accepted a 69,549,369 byte
    file that should have been 71,886,238: the socket closed cleanly mid
    transfer, so no exception fired, and 'bigger than 100 KB' passed happily.
    HDF5 caught it three steps later with 'truncated file'. This is session
    5's stale-resume lesson again -- a marker may only be trusted if the code
    writing it could honour the promise.
    """
    try:
        with rasterio.open(str(path)) as ds:
            return bool(ds.subdatasets)
    except Exception:
        return False


def download(url, dest, tok, tries=8):
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, tries + 1):
        have = part.stat().st_size if part.exists() else 0
        try:
            extra = {"Range": f"bytes={have}-"} if have else None
            with http_get(url, tok, timeout=300, extra=extra) as r:
                # What SHOULD arrive. Content-Range wins when resuming
                # because Content-Length then describes only the remainder.
                expected = None
                cr = r.headers.get("Content-Range")
                cl = r.headers.get("Content-Length")
                if cr and "/" in cr and cr.rsplit("/", 1)[1].isdigit():
                    expected = int(cr.rsplit("/", 1)[1])
                elif cl and cl.isdigit():
                    expected = have + int(cl)
                mode = "ab" if (have and r.status == 206) else "wb"
                if mode == "wb":
                    have = 0
                    if expected is None and cl and cl.isdigit():
                        expected = int(cl)
                with open(part, mode) as f:
                    while True:
                        c = r.read(CHUNK)
                        if not c:
                            break
                        f.write(c)
                        have += len(c)
            if expected is not None and have != expected:
                # Short read with no exception: the classic silent
                # truncation. Keep the .part and resume rather than
                # promoting an incomplete file.
                print(f"      short by {expected-have:,} bytes "
                      f"({have:,}/{expected:,}), resuming", flush=True)
                time.sleep(min(30, 3 * attempt))
                continue
            part.replace(dest)
            if not h5_ok(dest):
                # Right length, wrong content: a login page, a proxy error,
                # or a corrupted transfer. Start this one over.
                print(f"      downloaded but will not open as HDF5; "
                      f"discarding and retrying")
                dest.unlink(missing_ok=True)
                continue
            return True
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                print(f"      HTTP {e.code}: LAADS_TOKEN rejected")
                return False
            time.sleep(min(60, 4 * attempt))
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as e:
            print(f"      {type(e).__name__}, resuming from "
                  f"{have/1e6:.0f} MB", flush=True)
            time.sleep(min(60, 4 * attempt))
    return False


def open_sds(h5path):
    """Find the radiance subdataset and its scaling. Discovered, not assumed.

    GDAL exposes HDF5 groups as subdatasets. Names, scale factors and fill
    values differ between Black Marble products and have changed between
    collections, so we list what is in the file and pick by preference.
    """
    with rasterio.open(str(h5path)) as ds:
        subs = list(ds.subdatasets)
    if not subs:
        return None, None, subs
    pick = None
    for want in SDS_PREFER:
        for s in subs:
            if s.rsplit("/", 1)[-1] == want or s.endswith(want):
                pick = s
                break
        if pick:
            break
    if pick is None:
        cand = [s for s in subs if "Composite" in s and "Quality" not in s
                and "Num" not in s and "Std" not in s]
        pick = cand[0] if cand else subs[0]
    return pick, None, subs


def md5_of(path, chunk=8 * 1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def main():
    probe_only = "--probe-only" in sys.argv
    load_dotenv(BASE / ".env")

    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit("ERROR: set DB_PASSWORD in .env first.")
    url = (f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
           f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
           f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Connected to database:",
          os.getenv("DB_NAME", "land_intelligence_kenya"))

    try:
        socket.getaddrinfo("ladsweb.modaps.eosdis.nasa.gov", 443)
    except socket.gaierror as e:
        sys.exit(f"ERROR: cannot resolve LAADS ({e}). This is this machine's "
                 f"network, not the data. Nothing downloaded, no run opened.")

    tok = token()
    if not tok:
        print("\nNo LAADS_TOKEN in .env. Listing may work; downloads will "
              "not.\n  1. register  https://urs.earthdata.nasa.gov/users/new"
              "\n  2. token     https://ladsweb.modaps.eosdis.nasa.gov/"
              "profile/#generate-token\n  3. LAADS_TOKEN=<token> in .env")

    with engine.connect() as conn:
        xmin, xmax, ymin, ymax = conn.execute(text("""
            SELECT ST_XMin(e), ST_XMax(e), ST_YMin(e), ST_YMax(e)
            FROM (SELECT ST_Extent(geom) AS e FROM admin.country) t
        """)).one()
    xmin, xmax = float(xmin) - PAD_DEG, float(xmax) + PAD_DEG
    ymin, ymax = float(ymin) - PAD_DEG, float(ymax) + PAD_DEG
    need = tiles_for(xmin, ymin, xmax, ymax)
    print(f"\nKenya bbox {xmin:.2f},{ymin:.2f} to {xmax:.2f},{ymax:.2f}")
    print(f"Black Marble tiles needed: "
          f"{', '.join(f'h{h:02d}v{v:02d}' for h, v in need)}")

    # -----------------------------------------------------------------------
    # 1. PROBE
    # -----------------------------------------------------------------------
    print(f"\n1. Listing LAADS {PRODUCT} collection {COLLECTION} ...")
    plan = {}
    for y in YEARS:
        avail, err = list_year(y, tok)
        if not avail:
            print(f"   {y}  nothing listed ({err})")
            continue
        got = [t for t in need if t in avail]
        miss = [t for t in need if t not in avail]
        print(f"   {y}  {len(avail):,} tiles globally; "
              f"{len(got)}/{len(need)} of Kenya's"
              + (f"  MISSING {['h%02dv%02d' % t for t in miss]}" if miss
                 else ""))
        if got:
            plan[y] = {t: avail[t] for t in got}
            print(f"        e.g. {plan[y][got[0]][0]}")
    if not plan:
        sys.exit("\nNo tiles found. Check LAADS_TOKEN, and that collection "
                 f"{COLLECTION} is right for {PRODUCT} (override with "
                 f"LAADS_COLLECTION).")
    if probe_only:
        print("\n   --probe-only: stopping before any download.")
        return

    with engine.begin() as conn:
        run_id = conn.execute(text("""
            INSERT INTO metadata.etl_runs (pipeline, started_at, run_status)
            VALUES (:p, now(), 'running') RETURNING run_id
        """), {"p": PIPELINE}).scalar()
    print(f"ETL run opened (run_id={run_id})")

    try:
        with engine.begin() as conn:
            source_id = conn.execute(text("""
                SELECT source_id FROM metadata.sources
                WHERE name = 'NASA Black Marble'
            """)).scalar()
            if source_id is None:
                source_id = conn.execute(text("""
                    INSERT INTO metadata.sources
                        (name, organisation, tier, url, license,
                         redistribution_allowed, attribution_required,
                         api_available, notes)
                    VALUES ('NASA Black Marble',
                            'NASA Goddard / LAADS DAAC', 2,
                            'https://www.earthdata.nasa.gov/data/projects/'
                            'black-marble',
                            'NASA Earth Science Data (open, no commercial '
                            'restriction)', TRUE, TRUE, TRUE,
                            'VNP46A4 yearly BRDF-adjusted nighttime lights, '
                            '15 arcsec. Replaces EOG VNL v2.2, whose '
                            'programmatic access moved to paid subscribers. '
                            'THE TREND IS THE SIGNAL, not the level.')
                    RETURNING source_id
                """)).scalar()
                print(f"   registered source_id={source_id} "
                      f"(NASA open, commercial OK)")

        # -------------------------------------------------------------------
        # 2. Download tiles, mosaic, crop to Kenya.
        # -------------------------------------------------------------------
        print("\n2. Fetching tiles and building yearly COGs ...")
        year_cogs = {}
        for y in sorted(plan):
            cog = COG_DIR / f"demographics_nightlights_blackmarble_500m_{y}.tif"
            if cog.exists():
                print(f"   {y}  have {cog.name}")
                year_cogs[y] = cog
                continue

            local = {}
            for (h, v), (name, link) in sorted(plan[y].items()):
                dest = RAW_DIR / name
                if dest.exists():
                    if h5_ok(dest):
                        local[(h, v)] = dest
                        continue
                    # A file already on disk from run 71 may be truncated.
                    # Verifying costs a header read; trusting it costs the
                    # whole run at the mosaic step.
                    print(f"   {y}  h{h:02d}v{v:02d} on disk but truncated "
                          f"or unreadable, refetching")
                    dest.unlink(missing_ok=True)
                print(f"   {y}  h{h:02d}v{v:02d} downloading ...", flush=True)
                if download(link, dest, tok):
                    local[(h, v)] = dest
                else:
                    print(f"        failed")
            if not local:
                print(f"   {y}  no tiles, skipping")
                continue

            # Mosaic on a lat/lon canvas built from the tile indices. The HDF5
            # carries no usable geotransform, but the grid is exact by
            # definition, so the canvas is derived rather than guessed.
            hs = [h for h, v in local]
            vs = [v for h, v in local]
            west = -180.0 + min(hs) * TILE_DEG
            north = 90.0 - min(vs) * TILE_DEG
            W = (max(hs) - min(hs) + 1) * TILE_PX
            H = (max(vs) - min(vs) + 1) * TILE_PX
            canvas = np.zeros((H, W), dtype="float32")
            transform = from_origin(west, north, PIX, PIX)

            sds_used, scale_used = None, None
            for (h, v), path in sorted(local.items()):
                sds, _, subs = open_sds(path)
                if sds is None:
                    print(f"      h{h:02d}v{v:02d}: no subdatasets, skipped")
                    continue
                if sds_used is None:
                    sds_used = sds.rsplit("/", 1)[-1]
                    print(f"      subdataset: {sds_used}")
                    print(f"      ({len(subs)} available in the file)")
                with rasterio.open(sds) as s:
                    a = s.read(1).astype("float32")
                    sc = s.scales[0] if s.scales else 1.0
                    nod = s.nodata
                if nod is not None:
                    a[a == nod] = 0.0
                # BLACK MARBLE v2.0 STORES RADIANCE AS FLOAT, not uint16.
                # NASA changed it precisely so gas flares above 6553.5
                # nW/cm2/sr stop saturating at the 16-bit ceiling. So 65535
                # is a fill marker inherited from v1.0, not a valid maximum,
                # and anything at or beyond it is absence of data. Negative
                # radiance is likewise not physical.
                a[~np.isfinite(a)] = 0.0
                a[a >= 65535] = 0.0
                a[a < 0] = 0.0
                if sc and sc != 1.0:
                    a *= sc
                    scale_used = sc
                r0 = (v - min(vs)) * TILE_PX
                c0 = (h - min(hs)) * TILE_PX
                canvas[r0:r0 + a.shape[0], c0:c0 + a.shape[1]] = a
                del a
            if scale_used:
                print(f"      scale factor applied: {scale_used}")

            win = from_bounds(xmin, ymin, xmax, ymax,
                              transform).round_offsets().round_lengths()
            r0, c0 = max(0, int(win.row_off)), max(0, int(win.col_off))
            sub = canvas[r0:r0 + int(win.height), c0:c0 + int(win.width)]
            prof = {"driver": "GTiff", "dtype": "float32", "count": 1,
                    "crs": "EPSG:4326", "width": sub.shape[1],
                    "height": sub.shape[0],
                    "transform": rasterio.windows.transform(win, transform),
                    "compress": "DEFLATE", "predictor": 3, "tiled": True,
                    "blockxsize": 512, "blockysize": 512}
            tmp = RAW_DIR / f"_tmp_{y}.tif"
            with rasterio.open(tmp, "w", **prof) as d:
                d.write(sub, 1)
            rio_copy(str(tmp), str(cog), driver="COG", compress="DEFLATE",
                     predictor=3, overview_resampling="average")
            tmp.unlink(missing_ok=True)
            print(f"      {cog.name}  {sub.shape[1]}x{sub.shape[0]}  "
                  f"max {float(np.nanmax(sub)):.1f} nW/cm2/sr  "
                  f"lit {100.0*float(np.mean(sub > LIT_THRESHOLD)):.2f}%")
            del canvas, sub
            year_cogs[y] = cog

        if len(year_cogs) < 2:
            raise SystemExit("Fewer than two years built; a trend needs at "
                             "least two.")

        # -------------------------------------------------------------------
        # 3. Zonal statistics per county and ward.
        # -------------------------------------------------------------------
        print("\n3. Zonal statistics ...")
        levels = [
            ("county", "SELECT county_code AS code, geom FROM admin.counties "
                       "WHERE status='active'"),
            ("ward", "SELECT COALESCE(ward_code, 'LIP-W' || id::text) AS code,"
                     " geom FROM admin.wards WHERE status='active'"),
        ]
        rows = []
        for level, sql in levels:
            gdf = gpd.read_postgis(sql, engine, geom_col="geom")
            print(f"   {level}: {len(gdf):,} units")
            for y, cog in sorted(year_cogs.items()):
                with rasterio.open(cog) as src:
                    band = src.read(1)
                    for code, geom in zip(gdf["code"], gdf.geometry):
                        if geom is None or geom.is_empty:
                            continue
                        try:
                            w = from_bounds(*geom.bounds, src.transform)
                            w = w.round_offsets().round_lengths()
                            rr = max(0, int(w.row_off))
                            cc = max(0, int(w.col_off))
                            sub = band[rr:rr + int(w.height),
                                       cc:cc + int(w.width)]
                            if sub.size == 0:
                                continue
                            m = geometry_mask(
                                [geom], out_shape=sub.shape,
                                transform=rasterio.windows.transform(
                                    w, src.transform), invert=True)
                            vals = sub[m]
                            if vals.size == 0:
                                continue
                            rows.append({
                                "admin_level": level,
                                "admin_code": str(code), "period": str(y),
                                "radiance_mean": float(np.nanmean(vals)),
                                "radiance_sum": float(np.nansum(vals)),
                                "lit_area_pct": float(
                                    100.0 * np.mean(vals > LIT_THRESHOLD)),
                            })
                        except Exception:
                            continue
                    del band
                print(f"      {y} done ({len(rows):,} rows)", flush=True)

        # -------------------------------------------------------------------
        # 4. THE DEVELOPMENT TREND, absolute not percentage.
        #
        # The first version fitted compound annual growth in radiance_sum and
        # it was unusable: median 33%/yr, top wards at 250%/yr, and the
        # ranking led with rural Homa Bay rather than the peri-urban market.
        # A percentage rate from a near-zero base is unbounded, and 335 of
        # 1,422 wards had a 2015 baseline of exactly zero.
        #
        # calibrate_nightlight_trend.py compared three metrics on whether
        # their top-ranked wards are places Kenyan land value actually moves.
        # Absolute change won outright: Ruai, Kitengela, Mihang'o, Gatongora,
        # Murera, Kalimoni, Gitothua, Muthwani, Kinanie, Karen, and Hindi on
        # the LAPSSET corridor.
        #
        # A lit-area-points metric was the intuitive candidate and FAILED,
        # because it saturates: Ruai, Karen, Gitothua and Mihang'o were
        # already 100% lit in 2015, so it scores the core market at zero.
        #
        # Least-squares slope, not last-minus-first, so one odd year cannot
        # dominate. No baseline floor is needed: absolute change is defined
        # at zero and cannot explode.
        # -------------------------------------------------------------------
        print("\n4. Fitting the development trend (absolute radiance/yr) ...")
        by_unit = {}
        for r in rows:
            by_unit.setdefault((r["admin_level"], r["admin_code"]), []).append(
                (int(r["period"]), r["radiance_sum"]))
        trends = {}
        for key, series in by_unit.items():
            series.sort()
            if len(series) < 2:
                continue
            yrs = np.array([s[0] for s in series], dtype="float64")
            val = np.array([s[1] for s in series], dtype="float64")
            trends[key] = float(np.polyfit(yrs, val, 1)[0])
        for r in rows:
            r["trend_radiance_yr"] = trends.get(
                (r["admin_level"], r["admin_code"]))
            # NULL ON PURPOSE. See 06_schema_update_v1.5.sql. Shipping a
            # percentage that ranks electrification as development would be
            # a confident wrong number, which is worse than an absent one.
            r["trend_pct_yr"] = None
        tv = [t for t in trends.values() if t is not None]
        if tv:
            print(f"   median {np.median(tv):.2f}, 95th pct "
                  f"{np.percentile(tv, 95):.1f}, max {max(tv):.1f} "
                  f"radiance/yr")

        # -------------------------------------------------------------------
        # 5. Write and catalogue.
        # -------------------------------------------------------------------
        print("\n5. Writing demographics.nightlights_stats ...")
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM demographics.nightlights_stats
                WHERE source_id = :sid
            """), {"sid": source_id})
            for i in range(0, len(rows), 1000):
                conn.execute(text("""
                    INSERT INTO demographics.nightlights_stats
                        (admin_level, admin_code, period, radiance_mean,
                         radiance_sum, lit_area_pct, trend_pct_yr,
                         trend_radiance_yr, source_id, source_date,
                         confidence)
                    VALUES (:admin_level, :admin_code, :period, :radiance_mean,
                            :radiance_sum, :lit_area_pct, :trend_pct_yr,
                            :trend_radiance_yr, :sid, CURRENT_DATE, 4)
                """), [dict(r, sid=source_id) for r in rows[i:i + 1000]])
        print(f"   {len(rows):,} rows written")

        with engine.connect() as conn:
            dataset_id = conn.execute(text(
                "SELECT dataset_id FROM metadata.datasets "
                "WHERE code = 'demographics.nightlights'")).scalar()
        if dataset_id:
            with engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM metadata.raster_catalog
                    WHERE dataset_id = :d AND variable = 'nightlights'
                """), {"d": dataset_id})
                for y, cog in sorted(year_cogs.items()):
                    with rasterio.open(cog) as s:
                        b = s.bounds
                        px = round(s.transform.a * 111320, 1)
                    conn.execute(text("""
                        INSERT INTO metadata.raster_catalog
                            (dataset_id, name, variable, storage_url, format,
                             pixel_size_m, band_count, nodata_value,
                             temporal_start, temporal_end, bbox, checksum,
                             source_id, source_date, confidence)
                        VALUES (:d, :n, 'nightlights', :u, 'COG', :px, 1, NULL,
                                make_date(:y,1,1), make_date(:y,12,31),
                                ST_MakeEnvelope(:l,:bo,:r,:t,4326),
                                :chk, :sid, CURRENT_DATE, 4)
                    """), {"d": dataset_id,
                           "n": (f"NASA Black Marble VNP46A4 annual "
                                 f"nighttime radiance {y}, nW/cm2/sr, "
                                 f"~500 m. " + ATTRIB),
                           "u": str(cog), "px": px, "y": y,
                           "l": float(b.left), "bo": float(b.bottom),
                           "r": float(b.right), "t": float(b.top),
                           "chk": md5_of(cog), "sid": source_id})
                conn.execute(text("""
                    UPDATE metadata.datasets
                    SET etl_status='ingested', updated_at=now()
                    WHERE code = 'demographics.nightlights'
                """))

        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE metadata.etl_runs
                SET finished_at=now(), run_status='success', rows_out=:n
                WHERE run_id=:id
            """), {"n": len(rows), "id": run_id})

        print(f"\nDONE. Run {run_id} logged as success.")
        print(f"Years: {', '.join(str(y) for y in sorted(year_cogs))}")
        print("\nUSING THIS LAYER:")
        print(" - trend_radiance_yr is the DEVELOPMENT SIGNAL. Absolute")
        print("   change per year, so it ranks intensification within")
        print("   already-lit land, which is what peri-urban development is.")
        print(" - trend_pct_yr is NULL on purpose. A percentage rate from a")
        print("   near-zero base ranked rural electrification above the")
        print("   Nairobi peri-urban market. See 06_schema_update_v1.5.sql.")
        print(" - trend_radiance_yr is a SUM, so it scales with unit area.")
        print("   Never compare a large ward to a small one on it directly.")
        print(" - Radiance is not a linear measure of economic activity, and")
        print("   the layer is indicative: SNPP's sensor degraded over the")
        print("   series and v2.0 corrects but does not erase that.")

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
                SET finished_at=now(), run_status='failed', error_message=:e
                WHERE run_id=:id
            """), {"e": str(exc)[:2000], "id": run_id})
        raise


if __name__ == "__main__":
    main()
