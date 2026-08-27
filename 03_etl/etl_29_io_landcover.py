r"""
============================================================================
ETL 29 - satellite.landcover ANNUAL (Impact Observatory / Esri, 10 m)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY, WHEN WE ALREADY HAVE WORLDCOVER
  satellite.landcover holds ESA WorldCover 2021 v200. Njeri asked whether
  2021 is too old, and checking settled it: **ESA has published nothing
  after 2021.** v100 was 2020, v200 was 2021, and that is the end of the
  series. The concern was correct and there is no ESA answer to it.

  Impact Observatory / Esri publish a 10 m ANNUAL series from 2017, same
  Sentinel-2 basis. That buys two things:
    1. RECENCY. Five years is a long time in Kenyan peri-urban land.
    2. CHANGE DETECTION, which is the bigger prize. "This parcel was
       rangeland in 2017 and built by 2024" is a far stronger development
       signal than any single-date map -- and stronger than the nightlights
       trend, because it is categorical and per-parcel rather than a
       radiance sum over a whole ward.

  WORLDCOVER IS KEPT, NOT REPLACED. It has 11 classes against IO's 9,
  including the mangrove class that gave us the strongest alignment
  evidence in the whole project (6,775 mangrove pixels, all coastal, zero
  inland). WorldCover stays the CLASSIFICATION reference; IO is the RECENCY
  and CHANGE layer. Two producers disagreeing is information, not a fault.

LICENCE - and this one is clean
  **CC BY 4.0. Commercial use permitted with attribution.** Unlike WDPA
  (non-commercial), the CA coverage layers (no declared licence) and Google
  Earth Engine's free tier (noncommercial only), this needs no letter and no
  negotiation before launch. Attribution is mandatory and is written onto
  every catalogue row.

ACCESS - discovered, not assumed
  Public S3 bucket `io-10m-annual-lulc` (us-west-2), no AWS account needed,
  plus a STAC 1.0.0 endpoint. The script QUERIES the STAC API for which
  years and tiles exist over Kenya rather than constructing paths. Six
  values were asserted from memory earlier in this session and every one was
  wrong; this asks.

THE 9 CLASSES (note 3 and 6 are unused)
  1 Water          2 Trees        4 Flooded vegetation
  5 Crops          7 Built area   8 Bare ground
  9 Snow/ice      10 Clouds      11 Rangeland

  Mapping to WorldCover is NOT one-to-one. IO's "Rangeland" absorbs both
  WorldCover's Shrubland and Grassland, so a direct class-by-class
  comparison between the two will always disagree and that disagreement is
  not an error.

CORRECTED AFTER RUN 81: EVERY SHARE THIS SCRIPT PRINTED WAS A BOX SHARE
  v1 divided by (g > 0).sum(), the covered padded bounding box, and labelled
  the result "% of Kenya". Rule E1, fifth occurrence, and made one script
  after fixing the identical error in etl_27. Statistics are now masked by
  admin.country and the script refuses to run if the mask does not measure
  close to Kenya's 580,367 km2.

  ANY IO FIGURE RECORDED BEFORE THIS FIX IS A BOX SHARE. In particular the
  2017-2024 tree cover and built-area numbers in PROGRESS.md lesson 29 must
  be re-derived from a clipped run before they are quoted anywhere. The
  conclusion they support does not change -- clipping raises the built share
  and so widens the gap with WorldCover -- but the numbers themselves are
  not Kenya numbers.

How to run (from 03_etl with venv active):
  python etl_29_io_landcover.py --probe-only
  python etl_29_io_landcover.py
============================================================================
"""

import os
import sys
import json
import time
import hashlib
import urllib.request
import urllib.error
import http.client
from pathlib import Path

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import rasterio
    from rasterio.warp import reproject, Resampling
    from rasterio.features import rasterize
    from rasterio.shutil import copy as rio_copy
except ImportError as e:
    sys.exit(f"ERROR: missing dependency ({e}). pip install rasterio")

try:
    import geopandas as gpd
except ImportError:
    sys.exit("ERROR: geopandas missing. With venv active: pip install geopandas")

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
PIPELINE = "etl_29_io_landcover"
RAW_DIR = BASE / "data" / "raw" / "landcover_io"
RAW_DIR.mkdir(parents=True, exist_ok=True)
COG_DIR = PROJECT / "06_rasters" / "cog" / "satellite"
COG_DIR.mkdir(parents=True, exist_ok=True)

STAC = ("https://api.impactobservatory.com/stac-aws/collections/"
        "io-10m-annual-lulc/items")

YEARS = [int(y) for y in os.getenv("IO_YEARS", "2017,2023,2024,2025").split(",")]

# ~93 m working grid: the same 3 arcsec lattice hazards.flood and
# satellite.builtup use. DELIBERATE: the native product is 10 m, but the
# question this layer answers -- "has this parcel changed class" -- is asked
# per parcel, and holding four national 10 m mosaics is ~3.5 GB for a
# comparison that a 93 m grid answers. WorldCover remains the 10 m
# classification reference for "what is this exact spot".
WORK_DEG = 3.0 / 3600.0
PAD_DEG = 0.02

IO_CLASSES = {1: "Water", 2: "Trees", 4: "Flooded vegetation", 5: "Crops",
              7: "Built area", 8: "Bare ground", 9: "Snow/ice",
              10: "Clouds", 11: "Rangeland"}
ATTRIB = ("Impact Observatory, Microsoft and Esri, 10m Annual Land Use Land "
          "Cover (9-class), derived from ESA Sentinel-2. CC BY 4.0. "
          "Karra, K. et al. (2021) Global land use/land cover with Sentinel-2 "
          "and deep learning, IGARSS.")


def md5_of(path, chunk=8 * 1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def fetch_json(url, tries=4, timeout=90):
    last = None
    for i in range(1, tries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "LIP-ETL/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")), None
        except Exception as e:
            last = e
            if i < tries:
                time.sleep(3 * i)
    return None, str(last)


def stac_items(bbox, year, limit=200):
    """Ask the STAC API what exists. No path construction."""
    q = (f"{STAC}?bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
         f"&datetime={year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z"
         f"&limit={limit}")
    js, err = fetch_json(q)
    if js is None:
        return [], err
    feats = js.get("features", [])
    out = []
    for f in feats:
        assets = f.get("assets", {})
        a = assets.get("data") or assets.get("supercell") or None
        if a is None and assets:
            a = list(assets.values())[0]
        href = (a or {}).get("href")
        if not href:
            continue
        if href.startswith("s3://"):
            _, _, rest = href.partition("s3://")
            bucket, _, key = rest.partition("/")
            href = f"https://{bucket}.s3.us-west-2.amazonaws.com/{key}"
        out.append((f.get("id", "?"), href))
    return out, None


def download(url, dest, tries=6, timeout=300):
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, tries + 1):
        have = part.stat().st_size if part.exists() else 0
        try:
            h = {"User-Agent": "LIP-ETL/1.0"}
            if have:
                h["Range"] = f"bytes={have}-"
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                cr, cl = r.headers.get("Content-Range"), r.headers.get(
                    "Content-Length")
                exp = None
                if cr and "/" in cr and cr.rsplit("/", 1)[1].isdigit():
                    exp = int(cr.rsplit("/", 1)[1])
                elif cl and cl.isdigit():
                    exp = have + int(cl)
                mode = "ab" if (have and r.status == 206) else "wb"
                if mode == "wb":
                    have = 0
                with open(part, mode) as f:
                    while True:
                        c = r.read(4 << 20)
                        if not c:
                            break
                        f.write(c)
                        have += len(c)
            if exp is not None and have != exp:
                print(f"        short by {exp-have:,} bytes, resuming")
                time.sleep(3 * attempt)
                continue
            part.replace(dest)
            return True
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return False
            time.sleep(4 * attempt)
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as e:
            print(f"        {type(e).__name__}, resuming from "
                  f"{have/1e6:.0f} MB")
            time.sleep(4 * attempt)
    return False


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

    with engine.connect() as conn:
        xmin, xmax, ymin, ymax = conn.execute(text("""
            SELECT ST_XMin(e), ST_XMax(e), ST_YMin(e), ST_YMax(e)
            FROM (SELECT ST_Extent(geom) AS e FROM admin.country) t
        """)).one()
        dataset_id = conn.execute(text(
            "SELECT dataset_id FROM metadata.datasets "
            "WHERE code = 'satellite.landcover'")).scalar()
    xmin, xmax = float(xmin) - PAD_DEG, float(xmax) + PAD_DEG
    ymin, ymax = float(ymin) - PAD_DEG, float(ymax) + PAD_DEG
    bbox = (round(xmin, 4), round(ymin, 4), round(xmax, 4), round(ymax, 4))

    x0 = np.floor(xmin / WORK_DEG) * WORK_DEG
    y1 = np.ceil(ymax / WORK_DEG) * WORK_DEG
    W = int(round((np.ceil(xmax / WORK_DEG) * WORK_DEG - x0) / WORK_DEG))
    H = int(round((y1 - np.floor(ymin / WORK_DEG) * WORK_DEG) / WORK_DEG))
    transform = rasterio.Affine(WORK_DEG, 0, x0, 0, -WORK_DEG, y1)
    print(f"Working grid {W:,} x {H:,} at ~{WORK_DEG*111320:.0f} m")

    # -----------------------------------------------------------------------
    # THE COUNTRY MASK. Rule E1, and the FIFTH time this error has been made.
    #
    # The first version of this script divided every share by (g > 0).sum(),
    # which is the covered PADDED BOUNDING BOX -- Indian Ocean, Uganda,
    # Tanzania, Ethiopia, Somalia -- and then called the result "% of Kenya".
    # Same error as land cover in session 5, the flood layer twice, and the
    # rainfall layer, which had been fixed ONE SCRIPT EARLIER.
    #
    # Note the direction it biases: foreign land and ocean inflate the
    # denominator, so an unclipped built-area share reads LOWER than the true
    # Kenyan one. The unclipped figures were not merely imprecise, they
    # understated the very divergence that condemned the change layer.
    #
    # Every statistic below is masked. The written RASTERS stay on the full
    # grid on purpose, so they remain pixel-aligned with hazards.flood and
    # satellite.builtup on the same 3-arcsec lattice; alignment is a property
    # of the file, honesty is a property of the statistics.
    # -----------------------------------------------------------------------
    with engine.connect() as conn:
        country = gpd.read_postgis("SELECT geom FROM admin.country",
                                   conn, geom_col="geom")
    if country.empty:
        sys.exit("admin.country is empty; cannot clip. Run etl_05 first.")
    in_kenya = rasterize(
        ((g, 1) for g in country.geometry if g is not None),
        out_shape=(H, W), transform=transform, fill=0,
        dtype="uint8", all_touched=True).astype(bool)
    del country

    # Rule E1's sanity check, printed rather than assumed. Kenya is 580,367
    # km2; a 93 m rasterisation plus inland water inside the polygon puts the
    # mask a couple of percent over. The flood layer measured 592,055 km2 on
    # this same lattice, so anything far from that means the mask is wrong.
    cell_km2 = (WORK_DEG * 111320) * (WORK_DEG * 110574) / 1e6
    mask_km2 = float(in_kenya.sum()) * cell_km2
    print(f"Country mask {mask_km2:,.0f} km2 "
          f"({100.0*mask_km2/580_367:.1f}% of Kenya's official 580,367 km2) "
          f"= {100.0*in_kenya.sum()/(H*W):.1f}% of the working grid")
    if not (0.95 <= mask_km2 / 580_367 <= 1.10):
        sys.exit(f"Country mask is {mask_km2:,.0f} km2 against an expected "
                 f"~580,000-592,000. Refusing to quote national statistics "
                 f"against a denominator this far out.")

    # -----------------------------------------------------------------------
    # 1. PROBE the STAC API. Which years exist, how many tiles over Kenya.
    # -----------------------------------------------------------------------
    print(f"\n1. Querying the Impact Observatory STAC for {YEARS} ...")
    plan = {}
    for y in YEARS:
        items, err = stac_items(bbox, y)
        if err:
            print(f"   {y}  STAC error: {err}")
            continue
        if not items:
            print(f"   {y}  no items (year may not be published yet)")
            continue
        plan[y] = items
        print(f"   {y}  {len(items)} tiles over Kenya")
        print(f"        e.g. {items[0][1].rsplit('/', 1)[-1]}")
    if not plan:
        sys.exit("\nNo items returned. Check the STAC endpoint is reachable:\n"
                 f"  {STAC}")
    if probe_only:
        tot = sum(len(v) for v in plan.values())
        print(f"\n   {tot} tiles total across {len(plan)} years.")
        print("   --probe-only: stopping before any download.")
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
                WHERE name = 'Impact Observatory'
            """)).scalar()
            if source_id is None:
                source_id = conn.execute(text("""
                    INSERT INTO metadata.sources
                        (name, organisation, tier, url, license,
                         redistribution_allowed, attribution_required,
                         api_available, notes)
                    VALUES ('Impact Observatory',
                            'Impact Observatory, Microsoft and Esri', 2,
                            'https://registry.opendata.aws/io-lulc/',
                            'CC-BY-4.0', TRUE, TRUE, TRUE,
                            '10m Annual LULC 9-class from Sentinel-2. '
                            'Commercial use permitted with attribution. '
                            'ANNUAL series, unlike ESA WorldCover which '
                            'stopped at 2021. Kept ALONGSIDE WorldCover, '
                            'which has 11 classes incl. mangroves.')
                    RETURNING source_id
                """)).scalar()
                print(f"   registered source_id={source_id} (CC BY 4.0)")

        # -------------------------------------------------------------------
        # 2. Per year: fetch tiles, resample onto the working grid with
        #    NEAREST (categorical -- averaging class codes invents classes,
        #    lesson 15 from session 5).
        # -------------------------------------------------------------------
        print("\n2. Building yearly grids ...")
        grids = {}
        for y in sorted(plan):
            cog = COG_DIR / f"satellite_landcover_io_93m_{y}.tif"
            if cog.exists():
                with rasterio.open(cog) as s:
                    grids[y] = s.read(1)
                print(f"   {y}  have {cog.name}")
                continue

            canvas = np.zeros((H, W), dtype="uint8")
            for i, (tid, href) in enumerate(sorted(plan[y], key=lambda t: t[0]), 1):
                dest = RAW_DIR / href.rsplit("/", 1)[-1]
                if not (dest.exists() and dest.stat().st_size > 10_000):
                    print(f"   {y}  [{i}/{len(plan[y])}] {dest.name}",
                          flush=True)
                    if not download(href, dest):
                        print(f"        failed, skipping")
                        continue
                try:
                    tmp = np.zeros((H, W), dtype="uint8")
                    with rasterio.open(dest) as src:
                        reproject(source=rasterio.band(src, 1),
                                  destination=tmp,
                                  src_transform=src.transform,
                                  src_crs=src.crs,
                                  dst_transform=transform,
                                  dst_crs="EPSG:4326",
                                  resampling=Resampling.nearest,
                                  src_nodata=0, dst_nodata=0)
                    canvas = np.where(tmp > 0, tmp, canvas)
                    del tmp
                except Exception as e:
                    print(f"        unreadable ({type(e).__name__}), skipped")

            prof = {"driver": "GTiff", "dtype": "uint8", "count": 1,
                    "crs": "EPSG:4326", "transform": transform,
                    "width": W, "height": H, "nodata": 0, "tiled": True,
                    "blockxsize": 512, "blockysize": 512,
                    "compress": "DEFLATE", "bigtiff": "YES"}
            tmpf = RAW_DIR / f"_tmp_{y}.tif"
            with rasterio.open(tmpf, "w", **prof) as d:
                d.write(canvas, 1)
            if cog.exists():
                cog.unlink()
            # NEAREST overviews: averaging class codes invents classes that
            # do not exist (the mean of Built 7 and Bare 8 is 7.5).
            rio_copy(str(tmpf), str(cog), driver="COG", compress="DEFLATE",
                     overview_resampling="nearest", BIGTIFF="YES")
            tmpf.unlink(missing_ok=True)
            grids[y] = canvas
            cov = 100.0 * float((canvas > 0).sum()) / (W * H)
            print(f"      {cog.name}  ({cog.stat().st_size/1e6:.0f} MB, "
                  f"{cov:.1f}% of grid covered)")

        if len(grids) < 2:
            raise SystemExit("Need at least two years for change detection.")

        # -------------------------------------------------------------------
        # 3. National class shares per year, and the CHANGE layer.
        # -------------------------------------------------------------------
        ys = sorted(grids)
        print(f"\n3. Class shares, {ys[0]} to {ys[-1]}  (KENYA ONLY)")
        hdr = f"   {'class':22}" + "".join(f"{y:>9}" for y in ys)
        print(hdr)
        for code, name in IO_CLASSES.items():
            row = f"   {name:22}"
            any_present = False
            for y in ys:
                g = grids[y]
                covered = (g > 0) & in_kenya
                tot = max(1, int(covered.sum()))
                pct = 100.0 * float(((g == code) & in_kenya).sum()) / tot
                any_present |= pct > 0.005
                row += f"{pct:>8.2f}%"
            if any_present:
                print(row)

        # Both denominators, side by side, so the box-vs-country error can
        # never again hide inside a single plausible-looking number. etl_27
        # prints the same pair for the same reason.
        gl = grids[ys[-1]]
        box_built = 100.0 * float((gl == 7).sum()) / max(1, int((gl > 0).sum()))
        ken_built = (100.0 * float(((gl == 7) & in_kenya).sum())
                     / max(1, int(((gl > 0) & in_kenya).sum())))
        print(f"\n   Built area {ys[-1]}, padded box : {box_built:>6.2f}%")
        print(f"   Built area {ys[-1]}, KENYA ONLY: {ken_built:>6.2f}%"
              f"   <- the honest denominator")
        print(f"   ESA WorldCover 2021 Built-up, Kenya-clipped: 0.32%")
        print("   These two are NOT two measurements of one quantity, but a")
        print("   5-8x gap is far outside the GHSL-vs-WorldCover gap (0.52 vs")
        print("   0.32) that session 5 established as the expected producer")
        print("   disagreement. Treat a large gap as evidence about IO, not")
        print("   about Kenya.")

        a, b = grids[ys[0]], grids[ys[-1]]
        both = (a > 0) & (b > 0) & in_kenya
        changed = both & (a != b)
        to_built = both & (a != 7) & (b == 7)
        nb = max(1, int(both.sum()))
        print(f"\n   changed class     : "
              f"{100.0*changed.sum()/nb:.2f}% of Kenya")
        print(f"   became BUILT      : "
              f"{100.0*to_built.sum()/nb:.3f}% "
              f"({float(to_built.sum())*cell_km2:,.0f} km2)")
        print("   Built-up gain is the number to sanity-check: it should be")
        print("   small, positive, and concentrated around Nairobi, Kiambu,")
        print("   Kajiado, Machakos, Nakuru, Kisumu and Mombasa.")
        print("   AND a whole-country class flip of more than a few per cent")
        print("   is a claim about the CLASSIFIER, not the landscape: IO")
        print("   retrains and republishes its full back series, so a")
        print("   boundary that moves in the model moves in every year at")
        print("   once. See PROGRESS.md lesson 29.")

        # change raster: 0 nodata, 1 unchanged, 2 changed, 3 became built
        chg = np.zeros((H, W), dtype="uint8")
        chg[both] = 1
        chg[changed] = 2
        chg[to_built] = 3
        prof = {"driver": "GTiff", "dtype": "uint8", "count": 1,
                "crs": "EPSG:4326", "transform": transform, "width": W,
                "height": H, "nodata": 0, "tiled": True, "blockxsize": 512,
                "blockysize": 512, "compress": "DEFLATE", "bigtiff": "YES"}
        cname = f"satellite_landcover_change_io_93m_{ys[0]}-{ys[-1]}.tif"
        ccog = COG_DIR / cname
        tmpf = RAW_DIR / "_tmp_change.tif"
        with rasterio.open(tmpf, "w", **prof) as d:
            d.write(chg, 1)
        if ccog.exists():
            ccog.unlink()
        rio_copy(str(tmpf), str(ccog), driver="COG", compress="DEFLATE",
                 overview_resampling="nearest", BIGTIFF="YES")
        tmpf.unlink(missing_ok=True)
        print(f"   {ccog.name}  ({ccog.stat().st_size/1e6:.0f} MB)")

        # -------------------------------------------------------------------
        # 4. Catalogue.
        # -------------------------------------------------------------------
        with engine.begin() as conn:
            for y in ys:
                cog = COG_DIR / f"satellite_landcover_io_93m_{y}.tif"
                with rasterio.open(cog) as s:
                    bb = s.bounds
                conn.execute(text("""
                    DELETE FROM metadata.raster_catalog
                    WHERE dataset_id=:d AND variable=:v
                """), {"d": dataset_id, "v": f"landcover_io_{y}"})
                conn.execute(text("""
                    INSERT INTO metadata.raster_catalog
                        (dataset_id, name, variable, storage_url, format,
                         pixel_size_m, band_count, nodata_value,
                         temporal_start, temporal_end, bbox, checksum,
                         source_id, source_date, confidence)
                    VALUES (:d,:n,:v,:u,'COG',:px,1,0,
                            make_date(:y,1,1), make_date(:y,12,31),
                            ST_MakeEnvelope(:l,:bo,:r,:t,4326), :chk,
                            :sid, CURRENT_DATE, 4)
                """), {"d": dataset_id, "v": f"landcover_io_{y}",
                       "n": (f"Impact Observatory 9-class land cover {y}, "
                             f"resampled to ~93 m with NEAREST. Classes: "
                             f"1 Water, 2 Trees, 4 Flooded vegetation, "
                             f"5 Crops, 7 Built, 8 Bare, 9 Snow/ice, "
                             f"10 Clouds, 11 Rangeland. Rangeland absorbs "
                             f"WorldCover's Shrubland AND Grassland, so the "
                             f"two products cannot be compared class by "
                             f"class. " + ATTRIB),
                       "u": str(cog), "px": round(WORK_DEG * 111320, 1),
                       "y": y, "l": float(bb.left), "bo": float(bb.bottom),
                       "r": float(bb.right), "t": float(bb.top),
                       "chk": md5_of(cog), "sid": source_id})
            with rasterio.open(ccog) as s:
                bb = s.bounds
            conn.execute(text("""
                DELETE FROM metadata.raster_catalog
                WHERE dataset_id=:d AND variable='landcover_change'
            """), {"d": dataset_id})
            # STATUS pending_review, NOT active. THE QUARANTINE LIVES HERE.
            #
            # This row was condemned in session 6 and quarantined by
            # 01_database/07_data_fix_landcover_change.sql -- and then run 82
            # re-inserted it as 'active' inside this very transaction,
            # silently undoing the fix. A control that a pipeline can
            # overwrite is a reminder, not a control.
            #
            # The layer is still WRITTEN and still CATALOGUED, so the
            # reasoning stays traceable and a future fix has something to
            # compare against. It simply never ships as active.
            #
            # Evidence (run 82, country-clipped): Trees 10.98 -> 21.93% with
            # 68% of that landing in the single 2023->2024 step, Rangeland
            # -7.76 pts in the same step, Bare 5.00 -> 0.95% in the previous
            # one. Two discontinuities in two class pairs at two year
            # boundaries, while Water holds at 2.07/2.17/2.26 against
            # WorldCover's 2.13. That is a classifier being retrained, not a
            # landscape changing. See PROGRESS.md lesson 29 and 29a.
            conn.execute(text("""
                INSERT INTO metadata.raster_catalog
                    (dataset_id, name, variable, storage_url, format,
                     pixel_size_m, band_count, nodata_value, temporal_start,
                     temporal_end, bbox, checksum, source_id, source_date,
                     confidence, status)
                VALUES (:d,:n,'landcover_change',:u,'COG',:px,1,0,
                        make_date(:y0,1,1), make_date(:y1,12,31),
                        ST_MakeEnvelope(:l,:bo,:r,:t,4326), :chk, :sid,
                        CURRENT_DATE, 3, 'pending_review')
            """), {"d": dataset_id,
                   "n": (f"PENDING REVIEW - DO NOT USE. Land-cover change "
                         f"{ys[0]} to {ys[-1]}: 1 unchanged, 2 changed class, "
                         f"3 BECAME BUILT. Impact Observatory is NOT "
                         f"temporally consistent: the class shifts arrive as "
                         f"steps at single year boundaries while Water stays "
                         f"stable against an independent producer, which is "
                         f"classifier retraining rather than ground change. "
                         f"'Became built' alone reports several times Kenya's "
                         f"entire built stock, so this is not usable even as "
                         f"a lead list. Yearly snapshots are unaffected and "
                         f"remain active. See PROGRESS.md lesson 29. " +
                         ATTRIB),
                   "u": str(ccog), "px": round(WORK_DEG * 111320, 1),
                   "y0": ys[0], "y1": ys[-1], "l": float(bb.left),
                   "bo": float(bb.bottom), "r": float(bb.right),
                   "t": float(bb.top), "chk": md5_of(ccog), "sid": source_id})
            conn.execute(text("""
                UPDATE metadata.etl_runs
                SET finished_at=now(), run_status='success', rows_out=:n
                WHERE run_id=:id
            """), {"n": len(ys) + 1, "id": run_id})

        print(f"\nDONE. Run {run_id} logged as success.")
        print("USING THIS LAYER:")
        print(" - WorldCover stays the CLASSIFICATION reference (11 classes,")
        print("   10 m, incl. mangroves). This is the RECENCY and CHANGE")
        print("   layer. They will disagree; that is information.")
        print(" - IO 'Rangeland' = WorldCover Shrubland + Grassland. Never")
        print("   compare the two class by class.")
        print(" - THE CHANGE LAYER IS CATALOGUED AS pending_review AND MUST")
        print("   NOT SHIP. IO is not temporally consistent: the shifts come")
        print("   as steps at single year boundaries while Water stays put")
        print("   against WorldCover. That is a retrained classifier, not")
        print("   ground change. It is written and catalogued only so the")
        print("   reasoning stays traceable. PROGRESS.md lesson 29.")
        print(" - Crops is the one class IO looks BETTER on: stable across")
        print("   epochs and between WorldCover's floor and NDVI's ceiling,")
        print("   on exactly the class WorldCover under-detects. Rule D6.")

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
