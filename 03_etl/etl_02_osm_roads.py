"""
============================================================================
ETL 02 - OSM ROAD NETWORK (national, all 47 counties; see PILOT_ONLY)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does, in order:
  1. Connects to land_intelligence_kenya using your .env file
  2. Registers Geofabrik/OpenStreetMap as a source in metadata.sources
  3. Opens a run record in metadata.etl_runs
  4. Reads the roads layer straight out of kenya-latest-free.shp.zip
     (no need to extract the zip; geopandas can look inside it)
  5. Maps OSM road classes (about 20 of them) onto our 9 schema classes
  6. Stages all of Kenya's roads in staging.roads_raw (the loading dock)
  7. In SQL, keeps only roads that touch the 20 pilot counties, tags each
     with its county code, repairs geometry, and inserts into transport.roads
  8. Closes the run record with row counts

How to run (from the 03_etl folder with the venv active):
  python etl_02_osm_roads.py

Expected input (place under 03_etl/data/raw/osm/):
  kenya-latest-free.shp.zip  from https://download.geofabrik.de/africa/kenya.html
  (or the already-extracted gis_osm_roads_free_1.shp)

Licensing note: OSM data is ODbL (share-alike). Fine for internal analysis
and derived scores; raw redistribution needs attribution. Tracked as known
issue 4 in PROGRESS.md, to be resolved before commercial launch.
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

SOURCE_NAME = "OpenStreetMap via Geofabrik (Kenya extract)"
SOURCE_URL = "https://download.geofabrik.de/africa/kenya.html"
SOURCE_DATE = date.today()          # edit to the extract date shown on Geofabrik
PIPELINE = "etl_02_osm_roads"
ROADS_LAYER = "gis_osm_roads_free_1.shp"

# False = load roads for all 47 counties (national database).
# True  = restrict to the 20 pilot counties (faster, for testing).
PILOT_ONLY = False

# OSM fclass -> our schema's road_class. OSM splits roads into many
# categories; our schema keeps 9 that matter for land analysis.
# '_link' variants are the ramps/sliproads of their parent class.
CLASS_MAP = {
    "motorway": "motorway", "motorway_link": "motorway",
    "trunk": "trunk", "trunk_link": "trunk",
    "primary": "primary", "primary_link": "primary",
    "secondary": "secondary", "secondary_link": "secondary",
    "tertiary": "tertiary", "tertiary_link": "tertiary",
    "unclassified": "unclassified",
    "residential": "residential",
    "living_street": "residential",   # narrow shared street = residential
    "service": "unclassified",        # driveways, access lanes
    "path": "path", "footway": "path", "cycleway": "path",
    "bridleway": "path", "steps": "path", "pedestrian": "path",
}
# Any fclass starting with 'track' (track, track_grade1..5) becomes 'track'.
# Anything unmapped (e.g. 'unknown') is dropped, logged, and counted.

# Major classes get confidence 4 (OSM Kenya tarmac coverage is excellent);
# minor roads get 3 (rural completeness varies).
HIGH_CONFIDENCE_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary"}


def find_roads_input():
    """Look for the extracted roads shapefile first, then the zip.
    Returns a path string geopandas can open either way."""
    for shp in RAW.rglob(ROADS_LAYER):
        return str(shp)
    for z in RAW.rglob("kenya-latest-free.shp.zip"):
        # zip:// tells geopandas to read a file inside the archive
        return f"zip://{z}!{ROADS_LAYER}"
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

# ---------------------------------------------------------------------------
# 2. REGISTER THE SOURCE
# ---------------------------------------------------------------------------
with engine.begin() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))
    source_id = conn.execute(
        text("""
            INSERT INTO metadata.sources
                (name, organisation, tier, url, license,
                 redistribution_allowed, api_available, notes)
            VALUES
                (:n, 'OpenStreetMap contributors / Geofabrik', 3, :u,
                 'ODbL 1.0 (share-alike, attribution required)',
                 true, true,
                 'Kenya extract, roads layer. Share-alike terms to be reviewed before commercial redistribution of raw geometry.')
            ON CONFLICT (name) DO UPDATE SET updated_at = now()
            RETURNING source_id
        """),
        {"n": SOURCE_NAME, "u": SOURCE_URL},
    ).scalar()
print(f"Source registered: {SOURCE_NAME} (source_id={source_id})")

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

try:
    # -----------------------------------------------------------------------
    # 4. READ THE ROADS LAYER
    # -----------------------------------------------------------------------
    src = find_roads_input()
    if src is None:
        raise RuntimeError(
            "Roads input not found. Put kenya-latest-free.shp.zip (or the "
            f"extracted {ROADS_LAYER}) under 03_etl/data/raw/osm/ and rerun.")
    print(f"\nReading roads from: {src}")
    print("This is all of Kenya's roads, so it takes a few minutes...")

    # Only load the columns we need; saves a lot of memory on a laptop.
    gdf = gpd.read_file(src, columns=["osm_id", "fclass", "name"])
    print(f"   {len(gdf):,} road segments read")

    # -----------------------------------------------------------------------
    # 5. MAP OSM CLASSES TO OUR SCHEMA CLASSES
    # -----------------------------------------------------------------------
    fclass = gdf["fclass"].astype(str)
    gdf["road_class"] = fclass.map(CLASS_MAP)
    # track, track_grade1..grade5 all collapse into 'track'
    gdf.loc[fclass.str.startswith("track"), "road_class"] = "track"

    dropped = gdf["road_class"].isna()
    if dropped.any():
        top = fclass[dropped].value_counts().head(5).to_dict()
        print(f"   Dropping {dropped.sum():,} segments with unmapped classes: {top}")
    gdf = gdf[~dropped].copy()

    # CRS check: Geofabrik ships EPSG:4326 already, but never assume.
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        print(f"   Reprojecting from {gdf.crs} to EPSG:4326")
        gdf = gdf.to_crs(4326)

    # A stable row id so the SQL step can deduplicate boundary-crossing roads.
    gdf["gid"] = range(len(gdf))

    # -----------------------------------------------------------------------
    # 6. STAGE (the loading dock)
    # -----------------------------------------------------------------------
    print(f"   Staging {len(gdf):,} segments into staging.roads_raw "
          "(chunked, takes a few minutes)...")
    gdf[["gid", "osm_id", "name", "road_class", "geometry"]].to_postgis(
        "roads_raw", engine, schema="staging",
        if_exists="replace", chunksize=20000,
    )

    # -----------------------------------------------------------------------
    # 7. SQL: FILTER TO PILOT COUNTIES AND LOAD transport.roads
    # -----------------------------------------------------------------------
    # ST_Subdivide chops each county polygon into small simple tiles.
    # Testing a road against a small tile is far cheaper than against a
    # county outline with thousands of vertices, so the join runs in
    # minutes instead of hours. Standard production PostGIS technique.
    scope = "pilot-county" if PILOT_ONLY else "all-county (national)"
    print(f"\nBuilding subdivided {scope} tiles for a fast spatial join...")
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
        conn.execute(text(
            "CREATE INDEX ON staging.roads_raw USING gist (geometry)"))
        conn.execute(text("ANALYZE staging.county_tiles"))
        conn.execute(text("ANALYZE staging.roads_raw"))

    print(f"Loading {scope} roads into transport.roads "
          "(the big step, expect several minutes)...")
    with engine.begin() as conn:
        # Idempotent rerun: clear this source's previous load first.
        conn.execute(text(
            "DELETE FROM transport.roads WHERE source_id = :sid"),
            {"sid": source_id})
        # DISTINCT ON (gid): a road touching two counties matches twice;
        # we keep one row, assigned to the first county alphabetically.
        # Geometry stays unclipped so proximity queries near borders work.
        n = conn.execute(text("""
            INSERT INTO transport.roads
                (osm_id, name, road_class, surface, county_code, geom,
                 source_id, source_date, confidence)
            SELECT DISTINCT ON (r.gid)
                   NULLIF(r.osm_id, '')::bigint,
                   r.name,
                   r.road_class,
                   'unknown',
                   t.county_code,
                   ST_Multi(ST_CollectionExtract(ST_MakeValid(r.geometry), 2)),
                   :sid, :sd,
                   CASE WHEN r.road_class IN
                        ('motorway','trunk','primary','secondary','tertiary')
                        THEN 4 ELSE 3 END
            FROM staging.roads_raw r
            JOIN staging.county_tiles t ON ST_Intersects(r.geometry, t.geom)
            ORDER BY r.gid, t.county_code
        """), {"sid": source_id, "sd": SOURCE_DATE}).rowcount
    print(f"   {n:,} road segments loaded into transport.roads")

    # -----------------------------------------------------------------------
    # 8. CLOSE THE RUN RECORD AS SUCCESS
    # -----------------------------------------------------------------------
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = :r
            WHERE run_id = :id
        """), {"r": n, "id": run_id})
    print(f"\nDONE. {n:,} rows loaded. Run {run_id} logged as success.")
    print("Verify in pgAdmin:")
    print("  SELECT county_code, road_class, count(*) FROM transport.roads")
    print("  GROUP BY 1, 2 ORDER BY 1, 2;")

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
