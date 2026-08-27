"""
============================================================================
ETL 09 - PROTECTED AREAS (environment.protected_areas) from WDPA
Land Intelligence Platform - Geocode Spatial Solutions Ltd

Source: World Database on Protected Areas (WDPA / Protected Planet),
Kenya extract. Catalogue backup for protected areas (primary KWS is
by-request). WDPA ships official names, designations, IUCN categories
and managing authorities, everything OSM's free layer lacked.

LICENSING FLAG: WDPA is non-commercial. Fine for building and testing;
before commercial launch, secure KWS data or clear WDPA's terms. Tracked
as a known licensing issue in PROGRESS.md.

What this script does:
  1. Finds the WDPA part-zips under data/raw/protected_areas
  2. Opens each zip, extracts it to a temp folder, reads the *-polygons.shp
  3. De-duplicates by WDPAID (parts can repeat a boundary)
  4. Classifies area_type from designation/name, authority from manager
  5. Assigns county by spatial join, loads with confidence 4

How to run (from 03_etl with venv active):
  python etl_09_wdpa_protected_areas.py
============================================================================
"""

import os
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
RAW = BASE / "data" / "raw" / "protected_areas"
SOURCE_NAME = "WDPA"                 # matches sources.csv catalogue name
SOURCE_URL = "https://www.protectedplanet.net/country/KEN"
SOURCE_DATE = date(2026, 7, 1)      # WDPA July 2026 release
PIPELINE = "etl_09_wdpa_protected_areas"


def classify(name, desig, marine):
    t = f"{desig} {name}".lower()
    if str(marine).strip() == "2" or "marine" in t:
        return "marine_protected"
    if "corridor" in t:
        return "wildlife_corridor"
    if "national park" in t:
        return "national_park"
    if "sanctuary" in t:
        return "sanctuary"
    if "conservancy" in t or "conservation area" in t:
        return "conservancy"
    if "reserve" in t:               # national/forest/game/nature reserve
        return "national_reserve"
    return "conservancy"             # neutral default


def authority(mang, gov):
    m = f"{mang} {gov}".lower()
    if "wildlife service" in m or "kws" in m:
        return "KWS"
    if "forest service" in m or "kfs" in m:
        return "KFS"
    if "county" in m:
        return "county"
    if "community" in m or "conservancy" in m:
        return "community"
    return None


def read_wdpa_polygons():
    """Find WDPA part-zips, extract, read every *-polygons.shp, concat."""
    zips = sorted(RAW.glob("WDPA_*_shp_*.zip"))
    if not zips:
        zips = sorted(RAW.glob("WDPA_*_shp.zip"))
    if not zips:
        raise RuntimeError("No WDPA zip files under data/raw/protected_areas/")
    frames = []
    for zpath in zips:
        with zipfile.ZipFile(zpath) as z:
            poly = [n for n in z.namelist() if n.lower().endswith("polygons.shp")]
            if not poly:
                continue
            with tempfile.TemporaryDirectory() as tmp:
                z.extractall(tmp)
                for shp in poly:
                    g = gpd.read_file(Path(tmp) / shp)
                    frames.append(g)
                    print(f"   {zpath.name}: {len(g):,} polygons")
    if not frames:
        raise RuntimeError("No *-polygons.shp found inside the WDPA zips.")
    return pd.concat(frames, ignore_index=True)


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
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))
    source_id = conn.execute(text("""
        INSERT INTO metadata.sources
            (name, organisation, tier, url, license,
             redistribution_allowed, api_available, notes)
        VALUES (:n, 'UNEP-WCMC Protected Planet', 2, :u,
                'WDPA terms (non-commercial)', false, true,
                'Kenya extract. Non-commercial; use KWS for paid product.')
        ON CONFLICT (name) DO UPDATE SET updated_at = now()
        RETURNING source_id
    """), {"n": SOURCE_NAME, "u": SOURCE_URL}).scalar()
print(f"Source: {SOURCE_NAME} (source_id={source_id})")

with engine.begin() as conn:
    run_id = conn.execute(text("""
        INSERT INTO metadata.etl_runs (pipeline, started_at, run_status)
        VALUES (:p, now(), 'running') RETURNING run_id
    """), {"p": PIPELINE}).scalar()
print(f"ETL run opened (run_id={run_id})")

try:
    print("\nReading WDPA polygons from zips...")
    gdf = read_wdpa_polygons()
    print(f"   {len(gdf):,} polygons total before de-duplication")

    lower = {c.lower(): c for c in gdf.columns}
    def col(*names):
        for nm in names:
            if nm in lower:
                return lower[nm]
        return None

    c_id = col("wdpaid", "wdpa_pid")
    c_name = col("name", "orig_name")
    c_desig = col("desig_eng", "desig", "desig_type")
    c_marine = col("marine")
    c_mang = col("mang_auth")
    c_gov = col("gov_type")
    if c_name is None:
        raise RuntimeError(f"No NAME column in WDPA file: {list(gdf.columns)}")

    if c_id:
        gdf = gdf.drop_duplicates(subset=c_id)
    print(f"   {len(gdf):,} unique protected areas")

    gdf["p_name"] = gdf[c_name].astype(str)
    gdf["p_type"] = gdf.apply(lambda r: classify(
        r.get(c_name, ""), r.get(c_desig, "") if c_desig else "",
        r.get(c_marine, "") if c_marine else ""), axis=1)
    gdf["p_auth"] = gdf.apply(lambda r: authority(
        r.get(c_mang, "") if c_mang else "",
        r.get(c_gov, "") if c_gov else ""), axis=1)

    print("   Classified by type:")
    for t, cnt in gdf["p_type"].value_counts().items():
        print(f"      {t}: {cnt}")

    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    gdf["gid"] = range(len(gdf))

    print(f"   Staging {len(gdf):,} polygons...")
    gdf[["gid", "p_name", "p_type", "p_auth", "geometry"]].rename(
        columns={"geometry": "geometry"}).to_postgis(
        "wdpa_raw", engine, schema="staging",
        if_exists="replace", chunksize=2000)

    print("   Assigning counties and loading environment.protected_areas...")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS staging.county_tiles"))
        conn.execute(text("""
            CREATE TABLE staging.county_tiles AS
            SELECT county_code, ST_Subdivide(geom, 128) AS geom
            FROM admin.counties
        """))
        conn.execute(text(
            "CREATE INDEX ON staging.county_tiles USING gist (geom)"))
        conn.execute(text(
            "CREATE INDEX ON staging.wdpa_raw USING gist (geometry)"))
        conn.execute(text("ANALYZE staging.county_tiles"))
        conn.execute(text("ANALYZE staging.wdpa_raw"))
        # Clear any prior protected-area load (OSM attempt loaded nothing,
        # but be safe and clear both this source and the OSM source rows).
        conn.execute(text("DELETE FROM environment.protected_areas"))
        n = conn.execute(text("""
            INSERT INTO environment.protected_areas
                (name, area_type, authority, county_code, geom,
                 source_id, source_date, confidence)
            SELECT DISTINCT ON (p.gid)
                   p.p_name, p.p_type, p.p_auth, t.county_code,
                   ST_Multi(ST_CollectionExtract(ST_MakeValid(p.geometry), 3)),
                   :sid, :sd, 4
            FROM staging.wdpa_raw p
            JOIN staging.county_tiles t ON ST_Intersects(p.geometry, t.geom)
            ORDER BY p.gid, t.county_code
        """), {"sid": source_id, "sd": SOURCE_DATE}).rowcount

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = :r
            WHERE run_id = :id
        """), {"r": n, "id": run_id})
        conn.execute(text("""
            UPDATE metadata.datasets SET etl_status = 'ingested', updated_at = now()
            WHERE code = 'environment.protected_areas'
        """))
    print(f"\nDONE. {n:,} protected areas loaded. Run {run_id} success.")
    print("Verify: SELECT area_type, count(*) FROM environment.protected_areas "
          "GROUP BY 1 ORDER BY 2 DESC;")

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
