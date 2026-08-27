"""
============================================================================
ETL 03 - OSM RIVERS AND WATERBODIES (national, all 47 counties; see PILOT_ONLY)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does, in order:
  1. Connects to land_intelligence_kenya using your .env file
  2. Reuses the Geofabrik source already registered by ETL 02
  3. Opens a run record in metadata.etl_runs
  4. Reads TWO layers from the extract already on disk:
       gis_osm_waterways_free_1.shp  (lines: rivers, streams, canals, drains)
       gis_osm_water_a_free_1.shp    (polygons: lakes, reservoirs, ponds)
  5. Stages both, then in SQL keeps only features touching the 20 pilot
     counties and loads them into environment.rivers and
     environment.waterbodies with provenance
  6. Closes the run record with row counts

PREREQUISITE: run 01_database/03_schema_update_v1.2.sql in pgAdmin first
(it adds the waterway_type column this script fills).

How to run (from the 03_etl folder with the venv active):
  python etl_03_osm_water.py

Design notes:
  * Waterbody classification heuristic: OSM's generic 'water' polygons
    become 'lake' if >= 5 hectares, else 'pond'. 'reservoir' maps directly.
    Wetlands, docks, glaciers and riverbanks are skipped (wetlands will
    get their own ETL from a better source). Confidence 3 reflects the
    heuristic; named major lakes can be upgraded later.
  * river_class (perennial/seasonal) stays NULL: OSM shapefiles do not
    carry it. A hydrological source (WRA) fills it in a later version.
============================================================================
"""

import os
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# 0. SETTINGS
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent
RAW = BASE / "data" / "raw"

SOURCE_NAME = "OpenStreetMap via Geofabrik (Kenya extract)"  # same as ETL 02
SOURCE_DATE = date(2026, 7, 16)     # the extract date shown on Geofabrik
PIPELINE = "etl_03_osm_water"
WATERWAYS_LAYER = "gis_osm_waterways_free_1.shp"
WATER_AREAS_LAYER = "gis_osm_water_a_free_1.shp"

# False = load water features for all 47 counties (national database).
# True  = restrict to the 20 pilot counties (faster, for testing).
PILOT_ONLY = False

# Line features we keep, mapped onto the v1.2 waterway_type column.
WATERWAY_TYPES = {"river", "stream", "canal", "drain"}

# Lake vs pond size threshold for OSM's generic 'water' polygons.
# 5 hectares = 50,000 square metres.
LAKE_MIN_M2 = 50_000


def find_layer(filename):
    for shp in RAW.rglob(filename):
        return str(shp)
    for z in RAW.rglob("kenya-latest-free.shp.zip"):
        return f"zip://{z}!{filename}"
    return None


# ---------------------------------------------------------------------------
# 1. CONNECT
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

# Guard: v1.2 must be applied first.
with engine.connect() as conn:
    has_col = conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'environment' AND table_name = 'rivers'
          AND column_name = 'waterway_type'
    """)).scalar()
if not has_col:
    sys.exit("ERROR: run 01_database/03_schema_update_v1.2.sql in pgAdmin "
             "first (adds environment.rivers.waterway_type), then rerun.")

# ---------------------------------------------------------------------------
# 2. REUSE THE SOURCE REGISTERED BY ETL 02
# ---------------------------------------------------------------------------
with engine.begin() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))
    source_id = conn.execute(
        text("SELECT source_id FROM metadata.sources WHERE name = :n"),
        {"n": SOURCE_NAME},
    ).scalar()
if source_id is None:
    sys.exit("ERROR: Geofabrik source not found in metadata.sources. "
             "Run etl_02_osm_roads.py first.")
print(f"Source reused: {SOURCE_NAME} (source_id={source_id})")

# ---------------------------------------------------------------------------
# 3. OPEN AN ETL RUN RECORD
# ---------------------------------------------------------------------------
with engine.begin() as conn:
    run_id = conn.execute(
        text("""
            INSERT INTO metadata.etl_runs (pipeline, started_at, run_status)
            VALUES (:p, now(), 'running') RETURNING run_id
        """),
        {"p": PIPELINE},
    ).scalar()
print(f"ETL run opened (run_id={run_id})")

rows_total = 0
try:
    # -----------------------------------------------------------------------
    # 4. PILOT-COUNTY TILES (rebuild: cheap, and guarantees freshness)
    # -----------------------------------------------------------------------
    scope = "pilot-county" if PILOT_ONLY else "all-county (national)"
    print(f"\nBuilding subdivided {scope} tiles...")
    where = "WHERE is_pilot" if PILOT_ONLY else ""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS staging.county_tiles"))
        conn.execute(text(f"""
            CREATE TABLE staging.county_tiles AS
            SELECT county_code, ST_Subdivide(geom, 128) AS geom
            FROM admin.counties {where}
        """))
        conn.execute(text(
            "CREATE INDEX ON staging.county_tiles USING gist (geom)"))
        conn.execute(text("ANALYZE staging.county_tiles"))

    # -----------------------------------------------------------------------
    # 5. WATERWAYS (lines) -> environment.rivers
    # -----------------------------------------------------------------------
    src = find_layer(WATERWAYS_LAYER)
    if src is None:
        raise RuntimeError(f"{WATERWAYS_LAYER} not found under data/raw. "
                           "It ships inside kenya-latest-free.shp.zip.")
    print(f"\nReading waterways from: {src}")
    gdf = gpd.read_file(src, columns=["osm_id", "fclass", "name"])
    print(f"   {len(gdf):,} waterway segments read")

    keep = gdf["fclass"].isin(WATERWAY_TYPES)
    dropped = (~keep).sum()
    if dropped:
        top = gdf.loc[~keep, "fclass"].value_counts().head(5).to_dict()
        print(f"   Dropping {dropped:,} segments outside our types: {top}")
    gdf = gdf[keep].copy()

    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    gdf["gid"] = range(len(gdf))

    print(f"   Staging {len(gdf):,} segments into staging.waterways_raw...")
    gdf[["gid", "name", "fclass", "geometry"]].to_postgis(
        "waterways_raw", engine, schema="staging",
        if_exists="replace", chunksize=20000,
    )

    print(f"   Loading {scope} waterways into environment.rivers...")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX ON staging.waterways_raw USING gist (geometry)"))
        conn.execute(text("ANALYZE staging.waterways_raw"))
        conn.execute(text(
            "DELETE FROM environment.rivers WHERE source_id = :sid"),
            {"sid": source_id})
        n = conn.execute(text("""
            INSERT INTO environment.rivers
                (name, waterway_type, county_code, geom,
                 source_id, source_date, confidence)
            SELECT DISTINCT ON (w.gid)
                   w.name, w.fclass, t.county_code,
                   ST_Multi(ST_CollectionExtract(ST_MakeValid(w.geometry), 2)),
                   :sid, :sd, 3
            FROM staging.waterways_raw w
            JOIN staging.county_tiles t ON ST_Intersects(w.geometry, t.geom)
            ORDER BY w.gid, t.county_code
        """), {"sid": source_id, "sd": SOURCE_DATE}).rowcount
    rows_total += n
    print(f"   {n:,} waterway segments loaded into environment.rivers")

    # -----------------------------------------------------------------------
    # 6. WATER AREAS (polygons) -> environment.waterbodies
    # -----------------------------------------------------------------------
    src = find_layer(WATER_AREAS_LAYER)
    if src is None:
        raise RuntimeError(f"{WATER_AREAS_LAYER} not found under data/raw.")
    print(f"\nReading water areas from: {src}")
    gdf = gpd.read_file(src, columns=["osm_id", "fclass", "name"])
    print(f"   {len(gdf):,} water polygons read")

    keep = gdf["fclass"].isin({"water", "reservoir"})
    dropped = (~keep).sum()
    if dropped:
        top = gdf.loc[~keep, "fclass"].value_counts().head(5).to_dict()
        print(f"   Skipping {dropped:,} polygons (wetlands etc. get their "
              f"own ETL later): {top}")
    gdf = gdf[keep].copy()

    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    gdf["gid"] = range(len(gdf))

    print(f"   Staging {len(gdf):,} polygons into staging.water_areas_raw...")
    gdf[["gid", "name", "fclass", "geometry"]].to_postgis(
        "water_areas_raw", engine, schema="staging",
        if_exists="replace", chunksize=20000,
    )

    print(f"   Loading {scope} waterbodies into environment.waterbodies...")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX ON staging.water_areas_raw USING gist (geometry)"))
        conn.execute(text("ANALYZE staging.water_areas_raw"))
        conn.execute(text(
            "DELETE FROM environment.waterbodies WHERE source_id = :sid"),
            {"sid": source_id})
        # body_type: reservoirs map directly; generic 'water' is split
        # lake vs pond by real-world area (geography cast = square metres).
        n = conn.execute(text("""
            INSERT INTO environment.waterbodies
                (name, body_type, county_code, geom,
                 source_id, source_date, confidence)
            SELECT DISTINCT ON (w.gid)
                   w.name,
                   CASE
                       WHEN w.fclass = 'reservoir' THEN 'reservoir'
                       WHEN ST_Area(w.geometry::geography) >= :lake_min
                            THEN 'lake'
                       ELSE 'pond'
                   END,
                   t.county_code,
                   ST_Multi(ST_CollectionExtract(ST_MakeValid(w.geometry), 3)),
                   :sid, :sd, 3
            FROM staging.water_areas_raw w
            JOIN staging.county_tiles t ON ST_Intersects(w.geometry, t.geom)
            ORDER BY w.gid, t.county_code
        """), {"sid": source_id, "sd": SOURCE_DATE,
               "lake_min": LAKE_MIN_M2}).rowcount
    rows_total += n
    print(f"   {n:,} waterbodies loaded into environment.waterbodies")

    # -----------------------------------------------------------------------
    # 7. CLOSE THE RUN RECORD AS SUCCESS
    # -----------------------------------------------------------------------
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = :r
            WHERE run_id = :id
        """), {"r": rows_total, "id": run_id})
    print(f"\nDONE. {rows_total:,} rows loaded. Run {run_id} logged as success.")
    print("Verify in pgAdmin:")
    print("  SELECT waterway_type, count(*) FROM environment.rivers GROUP BY 1;")
    print("  SELECT body_type, count(*) FROM environment.waterbodies GROUP BY 1;")

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
