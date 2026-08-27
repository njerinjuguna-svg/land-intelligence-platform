"""
============================================================================
ETL 21 - WORLDPOP POPULATION (demographics.population) at 100 m
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does:
  Downloads WorldPop's gridded population for Kenya, saves it as a COG, and
  then does the thing the catalogue actually asks for: ZONAL STATISTICS.
  Population and density are written per county and per ward into
  demographics.population_stats.

  Note this dataset is different in kind from everything since etl_13. The
  catalogue routes it to postgis / demographics.population_stats / zonal, not
  to metadata.raster_catalog. The deliverable is a TABLE. We keep the raster
  as well, because parcel-level enrichment will want "how many people live
  within 2 km of this plot", and that question needs the grid, not the ward
  total. So this ETL produces both, and catalogues both.

Why gridded population and not just the census:
  The census tells you a ward has 18,000 people. It does not tell you they are
  all clustered along one road with the rest of the ward empty. WorldPop
  redistributes census counts using satellite-detected settlement, so a parcel
  can be scored on the people actually near IT rather than on the average of
  an administrative unit it happens to sit in.

CONSTRAINED vs UNCONSTRAINED (this choice matters):
  WorldPop publishes two families. UNCONSTRAINED spreads population across all
  land, including places with no buildings. CONSTRAINED only puts people where
  built structures were detected. For land intelligence, constrained is
  obviously right: we care whether people live near a specific plot, and
  unconstrained would place phantom residents in empty bush.

UN-ADJUSTED vs NOT (the assumption in v1 of this script was WRONG):
  v1 defaulted to the NON-UN-adjusted product on the reasoning that the
  UN-adjusted one is rescaled to UN World Population Prospects estimates,
  which for Kenya run above the 2019 KNBS census, and that our Kenyan clients
  are better served by the census-consistent figure.

  Measured on run 51, that reasoning does not survive contact with the data:
      non-UN-adjusted : 55,201,278   (+16.1% vs the 2019 census)
      UN-adjusted     : 53,771,300   (+13.0%)
      2019 KNBS census: 47,564,296
  The non-adjusted file is NOT census-calibrated. It is WorldPop's own model
  output, and it is FURTHER from the census than the UN-adjusted one. The
  difference between the two is only 2.7% and both sit well above the census,
  so neither choice rescues us; the real answer is the note below.

  KEEP BOTH DOWNLOADED AND PRINT BOTH TOTALS. The point of this block is that
  the discrepancy stays visible in the log instead of being decided silently.

THE REAL FIX, AND IT IS ARCHITECTURAL:
  KNBS is tier 1 in our own source catalogue and WorldPop is tier 3. Admin
  level population should ultimately come from the official census table, with
  WorldPop supplying only the DISTRIBUTION of those people inside each unit.
  That is what dasymetric mapping is actually for. Until the KNBS census is
  loaded, treat every absolute population figure here as indicative, and
  prefer relative comparisons ("more people near plot A than plot B") over
  absolute claims ("18,400 people live within 2 km").

  Do NOT rescale the grid to the census to close the gap. That buries a real
  disagreement inside a number that then looks authoritative.

URL probing:
  WorldPop's folder layout has changed between releases, so rather than
  hardcode a guess this script tries a list of known patterns, prints which
  ones answer, and uses the best available. Same approach as etl_18.

How to run (from 03_etl with venv active):
  python etl_21_worldpop_population.py
============================================================================
"""

import os
import sys
import time
import json
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
    from rasterio.mask import mask as rio_mask
    from rasterio.shutil import copy as rio_copy
except ImportError:
    sys.exit("ERROR: rasterio missing. With venv active: pip install rasterio")

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
PIPELINE = "etl_21_worldpop_population"

RAW_DIR = BASE / "data" / "raw" / "demographics" / "worldpop"
RAW_DIR.mkdir(parents=True, exist_ok=True)
COG_DIR = PROJECT / "06_rasters" / "cog" / "demographics"
COG_DIR.mkdir(parents=True, exist_ok=True)

WP = "https://data.worldpop.org/GIS/Population"

# Candidates in preference order: newest first, constrained before
# unconstrained. Each entry is (label, url, un_adjusted?).
CANDIDATES = [
    ("2022 constrained R2024B",
     f"{WP}/Global_2021_2022_Constrained/2022/BSGM/KEN/ken_pop_2022_CN_100m_R2024B_v1.tif", False),
    ("2021 constrained R2024B",
     f"{WP}/Global_2021_2022_Constrained/2021/BSGM/KEN/ken_pop_2021_CN_100m_R2024B_v1.tif", False),
    ("2020 constrained maxar",
     f"{WP}/Global_2000_2020_Constrained/2020/maxar_v1/KEN/ken_ppp_2020_constrained.tif", False),
    ("2020 constrained BSGM",
     f"{WP}/Global_2000_2020_Constrained/2020/BSGM/KEN/ken_ppp_2020_constrained.tif", False),
    ("2020 constrained maxar UNadj",
     f"{WP}/Global_2000_2020_Constrained/2020/maxar_v1/KEN/ken_ppp_2020_UNadj_constrained.tif", True),
    ("2020 constrained BSGM UNadj",
     f"{WP}/Global_2000_2020_Constrained/2020/BSGM/KEN/ken_ppp_2020_UNadj_constrained.tif", True),
    ("2020 unconstrained",
     f"{WP}/Global_2000_2020/2020/KEN/ken_ppp_2020.tif", False),
]

COG_NAME = "demographics_population_worldpop_100m.tif"
COG_PATH = COG_DIR / COG_NAME

ATTRIB = ("WorldPop (University of Southampton), CC-BY-4.0. "
          "www.worldpop.org, doi:10.5258/SOTON/WP00645.")

# 2019 KNBS census, national total. This is the anchor we judge against.
CENSUS_TOTAL_2019 = 47_564_296

# Approximate 2019 KNBS census county populations, FOR ORIENTATION ONLY.
# These are here to catch an order-of-magnitude or ranking failure, not to
# grade WorldPop to the person. Loading the official KNBS county and ward
# tables is its own P1 task and should replace this list.
CENSUS_COUNTY = {
    "Nairobi": 4_397_073, "Kiambu": 2_417_735, "Nakuru": 2_162_202,
    "Kakamega": 1_867_579, "Bungoma": 1_670_570, "Meru": 1_545_714,
    "Kilifi": 1_453_787, "Machakos": 1_421_932, "Kisii": 1_266_860,
    "Mombasa": 1_208_333, "Uasin Gishu": 1_163_186, "Turkana": 926_976,
    "Mandera": 867_457, "Garissa": 841_353, "Marsabit": 459_785,
    "Taita Taveta": 340_671, "Tana River": 315_943, "Samburu": 310_327,
    "Isiolo": 268_002, "Lamu": 143_920,
}


def md5_of(path, chunk=8 * 1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def head_ok(url, timeout=45):
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "LIP-ETL/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def download(url, dest, retries=5, timeout=300):
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LIP-ETL/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r, \
                    open(part, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            part.replace(dest)
            return True
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                part.unlink(missing_ok=True)
                return False
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        part.unlink(missing_ok=True)
        time.sleep(3 * attempt)
    return False


def national_total(path):
    """Sum every population pixel, in bands so memory stays small."""
    total = 0.0
    with rasterio.open(path) as s:
        nd = s.nodata
        for _, win in s.block_windows(1):
            a = s.read(1, window=win).astype("float64")
            if nd is not None:
                a[a == nd] = 0.0
            # WorldPop uses large negative fills in places; population cannot
            # be negative, so anything below zero is a fill value, not a count.
            a[a < 0] = 0.0
            total += float(np.nansum(a))
    return total


load_dotenv(BASE / ".env")
pw = os.getenv("DB_PASSWORD")
if not pw or pw == "put_your_password_here":
    sys.exit("ERROR: edit the .env file and set DB_PASSWORD first.")

engine = create_engine(
    f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{pw}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
    f"/{os.getenv('DB_NAME', 'land_intelligence_kenya')}")
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
    with engine.connect() as conn:
        source_id = conn.execute(text(
            "SELECT source_id FROM metadata.sources WHERE name = 'WorldPop'"
        )).scalar()
        dataset_id = conn.execute(text(
            "SELECT dataset_id FROM metadata.datasets "
            "WHERE code = 'demographics.population'")).scalar()
    if source_id is None or dataset_id is None:
        raise SystemExit("WorldPop source or demographics.population dataset "
                         "missing. Run etl_04 first.")

    # -----------------------------------------------------------------------
    # 1. Probe. Print everything so we learn the real layout.
    # -----------------------------------------------------------------------
    print("\nProbing WorldPop URL patterns ...")
    available = []
    for label, url, unadj in CANDIDATES:
        ok = head_ok(url)
        print(f"  {'OK  ' if ok else 'no  '} {label}")
        if ok:
            available.append((label, url, unadj))
    if not available:
        raise SystemExit(
            "No WorldPop URL responded. The layout has probably changed.\n"
            "Open https://hub.worldpop.org/geodata/listing?id=79 in a browser, "
            "find the Kenya 100 m constrained GeoTIFF, and tell me the URL.")

    primary = next((a for a in available if not a[2]), available[0])
    counterpart = next((a for a in available if a[2] != primary[2]), None)
    print(f"\nPrimary: {primary[0]}")
    if counterpart:
        print(f"Comparison download: {counterpart[0]} "
              f"(only to show the UN adjustment gap)")

    # -----------------------------------------------------------------------
    # 2. Download and compare national totals against the census
    # -----------------------------------------------------------------------
    totals = {}
    paths = {}
    for label, url, unadj in ([primary] + ([counterpart] if counterpart else [])):
        dest = RAW_DIR / Path(url).name
        if dest.exists() and dest.stat().st_size > 1_000_000:
            print(f"  already have {dest.name} "
                  f"({dest.stat().st_size/1e6:.0f} MB)")
        else:
            print(f"  downloading {dest.name} ...", flush=True)
            if not download(url, dest):
                print(f"    failed, skipping")
                continue
            print(f"    done ({dest.stat().st_size/1e6:.0f} MB)")
        paths[label] = dest
        totals[label] = national_total(dest)

    if primary[0] not in paths:
        raise SystemExit("The primary raster failed to download. Nothing done.")

    print(f"\n  {'variant':34}{'national total':>16}{'vs 2019 census':>16}")
    for label, tot in totals.items():
        d = 100.0 * (tot - CENSUS_TOTAL_2019) / CENSUS_TOTAL_2019
        print(f"  {label:34}{tot:>16,.0f}{d:>15.1f}%")
    print(f"  {'2019 KNBS census':34}{CENSUS_TOTAL_2019:>16,}")
    print("\n  Kenya's population is genuinely growing at roughly 2% a year, so")
    print("  a figure ABOVE the 2019 census is expected for a later epoch. A")
    print("  figure BELOW it would be the warning sign.")

    src_path = paths[primary[0]]
    if totals.get(primary[0], 0) < CENSUS_TOTAL_2019 * 0.7:
        raise SystemExit(
            f"The chosen raster totals {totals[primary[0]]:,.0f}, far below the "
            f"2019 census of {CENSUS_TOTAL_2019:,}. Something is wrong with the "
            f"file or the nodata handling. Refusing to write zonal stats.")

    # -----------------------------------------------------------------------
    # 3. Save as COG and catalogue the grid
    # -----------------------------------------------------------------------
    print("\nConverting to COG ...")
    if COG_PATH.exists():
        COG_PATH.unlink()
    with rasterio.open(src_path) as s:
        # predictor 3 is the FLOATING POINT predictor and 2 is the integer one.
        # Using the wrong one does not corrupt anything, it just compresses
        # badly, but there is no reason to guess when the file will tell us.
        pred = 3 if s.dtypes[0].startswith("float") else 2
    # 'average' overviews are correct for a CONTINUOUS field. Note this is a
    # count per pixel, so a zoomed-out pixel showing the average of its
    # children is the right visual, but any ANALYSIS must use full resolution
    # and sum, never read an overview and multiply.
    rio_copy(str(src_path), str(COG_PATH), driver="COG",
             compress="DEFLATE", predictor=pred, overview_resampling="average")
    print(f"COG written: {COG_PATH.name} "
          f"({COG_PATH.stat().st_size/1e6:.0f} MB)")

    with rasterio.open(COG_PATH) as s:
        b = s.bounds
        px_deg = s.transform.a
        cog_nodata = s.nodata
        print(f"  {s.width:,} x {s.height:,} px, {s.dtypes[0]}, "
              f"nodata {cog_nodata}, ~{px_deg*111320:.0f} m")

    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM metadata.raster_catalog
            WHERE dataset_id = :did AND variable = 'population'
        """), {"did": dataset_id})
        conn.execute(text("""
            INSERT INTO metadata.raster_catalog
                (dataset_id, name, variable, storage_url, format, pixel_size_m,
                 band_count, nodata_value, temporal_start, temporal_end, bbox,
                 checksum, source_id, source_date, confidence)
            VALUES
                (:did, :name, 'population', :url, 'COG', :px, 1, :nodata,
                 :ts, :te, ST_MakeEnvelope(:l, :b, :r, :t, 4326),
                 :chk, :sid, CURRENT_DATE, 3)
        """), {
            "did": dataset_id,
            "name": (f"WorldPop gridded population, PEOPLE PER PIXEL (a count, "
                     f"not a density): to get a population for any area, SUM "
                     f"the pixels. Constrained to detected settlement. "
                     f"Variant: {primary[0]}. " + ATTRIB),
            "url": str(COG_PATH), "px": round(px_deg * 111320, 1),
            "nodata": float(cog_nodata) if cog_nodata is not None else -99999.0,
            "ts": "2020-01-01", "te": "2022-12-31",
            "l": float(b.left), "b": float(b.bottom),
            "r": float(b.right), "t": float(b.top),
            "chk": md5_of(COG_PATH), "sid": source_id,
        })

    # -----------------------------------------------------------------------
    # 4. ZONAL STATS: the actual deliverable
    # -----------------------------------------------------------------------
    print("\nComputing zonal statistics ...")

    with engine.connect() as conn:
        n_wards = conn.execute(text(
            "SELECT count(*) FROM admin.wards WHERE status='active'")).scalar()
        n_coded = conn.execute(text(
            "SELECT count(*) FROM admin.wards "
            "WHERE status='active' AND ward_code IS NOT NULL")).scalar()
    print(f"  wards: {n_wards} active, {n_coded} with an official ward_code")
    if n_coded < n_wards:
        print(f"  NOTE: {n_wards - n_coded} wards have no official code yet, a")
        print(f"  known gap from session 3. Those rows get a provisional code")
        print(f"  'LIP-W<id>' so the data is usable now. When the IEBC codes")
        print(f"  are loaded, these MUST be migrated: search for 'LIP-W'.")

    levels = [
        ("county", """SELECT county_code AS code, name, ST_AsGeoJSON(geom) AS gj,
                             ST_Area(geom::geography)/1e6 AS km2
                      FROM admin.counties WHERE status='active'"""),
        ("ward", """SELECT COALESCE(ward_code, 'LIP-W'||id) AS code, name,
                           ST_AsGeoJSON(geom) AS gj,
                           ST_Area(geom::geography)/1e6 AS km2
                    FROM admin.wards WHERE status='active'"""),
    ]

    year = 2020 if "2020" in primary[0] else int(primary[0][:4])
    written = {}
    county_pop = {}

    with rasterio.open(COG_PATH) as src:
        nd = src.nodata
        for level, sql in levels:
            with engine.connect() as conn:
                rows = conn.execute(text(sql)).all()
            out = []
            t0 = time.time()
            for i, (code, name, gj, km2) in enumerate(rows, 1):
                if gj is None:
                    continue
                try:
                    arr, _ = rio_mask(src, [json.loads(gj)], crop=True,
                                      nodata=nd if nd is not None else -99999,
                                      filled=True)
                except ValueError:
                    continue          # geometry does not overlap the raster
                a = arr[0].astype("float64")
                if nd is not None:
                    a[a == nd] = 0.0
                a[~np.isfinite(a)] = 0.0
                a[a < 0] = 0.0
                pop = float(a.sum())
                km2 = float(km2) if km2 else 0.0
                out.append({
                    "lvl": level, "code": str(code), "yr": year,
                    "pop": int(round(pop)),
                    "dens": round(pop / km2, 2) if km2 > 0 else None,
                    "sid": source_id,
                })
                if level == "county":
                    county_pop[name] = pop
                if i % 200 == 0:
                    print(f"    {level}: {i}/{len(rows)} "
                          f"({time.time()-t0:.0f}s)", flush=True)

            with engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM demographics.population_stats
                    WHERE admin_level = :lvl AND year = :yr AND version = 1
                """), {"lvl": level, "yr": year})
                conn.execute(text("""
                    INSERT INTO demographics.population_stats
                        (admin_level, admin_code, year, population,
                         density_per_km2, source_id, source_date, confidence)
                    VALUES (:lvl, :code, :yr, :pop, :dens, :sid,
                            CURRENT_DATE, 3)
                """), out)
            written[level] = len(out)
            print(f"  {level}: {len(out)} rows written")

    # -----------------------------------------------------------------------
    # 5. Does it agree with the census? The test that matters.
    # -----------------------------------------------------------------------
    print("\n  County check against the 2019 KNBS census "
          "(approximate reference figures):")
    print(f"  {'county':16}{'WorldPop':>12}{'census 2019':>14}{'diff':>9}")
    pairs = []
    for name, census in sorted(CENSUS_COUNTY.items(), key=lambda kv: -kv[1]):
        got = county_pop.get(name)
        if got is None:
            print(f"  {name:16}{'not found':>12}{census:>14,}{'':>9}")
            continue
        pairs.append((got, census))
        print(f"  {name:16}{got:>12,.0f}{census:>14,}"
              f"{100.0*(got-census)/census:>8.0f}%")
    if len(pairs) > 3:
        g = np.array([p[0] for p in pairs], dtype="float64")
        c = np.array([p[1] for p in pairs], dtype="float64")
        print(f"\n  correlation with census: {np.corrcoef(g, c)[0,1]:.4f}")
        print("  Above ~0.98 means WorldPop is distributing people across "
              "counties correctly.")
        print("  A uniform positive offset is expected: the census is 2019 and "
              "this grid is later.")

    ward_total = None
    with engine.connect() as conn:
        ward_total = conn.execute(text("""
            SELECT sum(population) FROM demographics.population_stats
            WHERE admin_level='ward' AND year=:y AND version=1
        """), {"y": year}).scalar()
    print(f"\n  sum of ward populations : {int(ward_total or 0):,}")
    print(f"  national raster total   : {totals[primary[0]]:,.0f}")
    if ward_total:
        cov = 100.0 * float(ward_total) / totals[primary[0]]
        print(f"  wards capture {cov:.1f}% of the national total")
        print("  (under 100% is normal: pixels whose centre falls outside every")
        print("   ward polygon are not counted by any ward, and our ward layer")
        print("   is still 1,425 of 1,450. A LOW figure here would point at the")
        print("   missing wards, which is a known open item.)")

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.datasets SET etl_status='ingested', updated_at=now()
            WHERE code = 'demographics.population'
        """))
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = :r
            WHERE run_id = :id
        """), {"r": sum(written.values()), "id": run_id})

    print(f"\nDONE. Run {run_id} logged as success.")
    print("pgAdmin: SELECT admin_level, count(*), sum(population) "
          "FROM demographics.population_stats GROUP BY 1;")

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
