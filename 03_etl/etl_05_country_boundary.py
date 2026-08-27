"""
============================================================================
ETL 05 - NATIONAL BOUNDARY (admin.country)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does:
  Builds Kenya's national outline by dissolving (merging) the 47 county
  polygons already in admin.counties, rather than loading a separate
  national shapefile.

Why dissolve instead of load a file:
  If we loaded the country from one source and the counties from another,
  their edges would not line up perfectly, leaving thin slivers and gaps
  on the map. Dissolving the counties guarantees the national outline IS
  exactly the sum of its counties. One source of truth, zero seams.

How to run (from 03_etl with venv active):
  python etl_05_country_boundary.py
============================================================================
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
PIPELINE = "etl_05_country_boundary"

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
    # Reuse the same source the county geometry came from, so provenance
    # is honest: the national outline is derived from those county rows.
    with engine.connect() as conn:
        source_id = conn.execute(text("""
            SELECT source_id FROM admin.counties
            WHERE source_id IS NOT NULL
            GROUP BY source_id ORDER BY count(*) DESC LIMIT 1
        """)).scalar()

    with engine.begin() as conn:
        # ST_Union merges all 47 polygons into one; ST_MakeValid then
        # ST_Multi guarantees a clean MultiPolygon (Kenya plus its islands).
        # Idempotent: replace any previous derived boundary.
        conn.execute(text("DELETE FROM admin.country"))
        n = conn.execute(text("""
            INSERT INTO admin.country
                (iso3, name, geom, source_id, source_date, confidence)
            SELECT 'KEN', 'Kenya',
                   ST_Multi(ST_MakeValid(ST_Union(geom))),
                   :sid, CURRENT_DATE, 4
            FROM admin.counties
        """), {"sid": source_id}).rowcount

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = :r
            WHERE run_id = :id
        """), {"r": n, "id": run_id})
        conn.execute(text("""
            UPDATE metadata.datasets SET etl_status = 'ingested',
                   updated_at = now()
            WHERE code = 'admin.country'
        """))
    print(f"\nDONE. National boundary built from 47 counties. "
          f"Run {run_id} logged as success.")
    print("Verify in pgAdmin / QGIS: admin.country should be one row, "
          "one clean Kenya outline.")

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
