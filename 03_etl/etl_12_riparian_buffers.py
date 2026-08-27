"""
============================================================================
ETL 12 - RIPARIAN BUFFERS (environment.riparian_buffers)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does:
  Draws the legally protected strip of land along every river and stream we
  already hold in environment.rivers, and stores each strip as a polygon in
  environment.riparian_buffers, keyed back to the river it came from.

Why this matters for the product:
  In Kenya the land immediately next to a watercourse is a "riparian reserve".
  It is public land. You cannot build a permanent structure, cultivate, or
  fence it. A parcel that sits partly inside this strip has a slice that is
  legally unbuildable, which directly affects its value and its suitability
  score. So "is any of this parcel inside a riparian reserve?" is one of the
  first questions a serious buyer asks. This layer lets us answer it.

Why we can build it with NO download:
  A riparian buffer is not a thing you fetch from anywhere. It is DERIVED:
  take the river line, and grow a band of the statutory width around it. The
  rivers are already in PostGIS (etl_03), so this is pure geometry work inside
  the database. That is exactly why it is our quick win while raster storage
  is being planned.

The statutory widths (the important part):
  Kenyan riparian width is set by several overlapping laws that agree on a
  range: a MINIMUM of 6 m and a MAXIMUM of 30 m from the highest water mark,
  scaled by the size of the watercourse.
    - EMCA (Wetlands, Riverbanks, Lakeshores and Seashores) Regulations, 2009
    - Water (Resources) Regulations, 2025 (WRA riparian reserve obligations)
    - Survey Regulations, Cap 299 (30 m for tidal rivers and lakes)
  We do not have each channel's measured width or flood mark, only OSM's
  physical channel type. So we map type -> statutory width honestly and
  conservatively, and record confidence 3 to say "this is a rules-based
  approximation, not a surveyed boundary".

  river  -> 30 m  (a major watercourse: the 30 m ceiling)
  stream ->  6 m  (a minor watercourse: the 6 m floor)
  canal  ->  6 m  (artificial channel; WRA obligations can still apply, so we
                   flag it at the minimum rather than ignore it)
  drain  -> SKIPPED (man-made drainage, not a natural watercourse)

  NOTE on geometry: OSM gives us the river as a centre line. The reserve is
  legally measured from each bank. Because we lack channel width, we grow the
  band by the statutory width from the centre line. For Kenya's mostly narrow
  rivers this is a sound, slightly conservative approximation. When a surveyed
  channel-width or flood-mark source arrives, rerun to sharpen it.

Why we buffer in METERS, not degrees:
  Our data is EPSG:4326 (longitude/latitude, i.e. degrees). ST_Buffer(geom, 30)
  in that system would mean 30 DEGREES, which is thousands of kilometres, total
  nonsense. We cast the line to GEOGRAPHY first, which makes ST_Buffer treat the
  number as real meters on the curved earth, accurate anywhere in the country,
  then cast the result back to a 4326 geometry to store it.

How to run (from 03_etl with venv active):
  python etl_12_riparian_buffers.py
============================================================================
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
PIPELINE = "etl_12_riparian_buffers"

# ---------------------------------------------------------------------------
# The one place to change the rules. type -> statutory buffer width in meters.
# Leave a type out of this dict to skip it (that is how 'drain' is excluded).
# ---------------------------------------------------------------------------
WIDTHS = {
    "river": 30,   # major watercourse: statutory maximum
    "stream": 6,   # minor watercourse: statutory minimum
    "canal": 6,    # artificial channel: minimum, conservative flag
    # "drain" intentionally absent -> not buffered
}

# What we write into the legal_basis column so every buffer row can defend
# itself in a report. Kept short; the full reasoning lives in this file.
LEGAL_BASIS = (
    "EMCA (Wetlands, Riverbanks, Lakeshores and Seashores) Regs 2009 "
    "(6 m min - 30 m max from high-water mark); Water (Resources) Regs 2025; "
    "Survey Regs Cap 299. Width by OSM channel type; buffered from centre line."
)

CONFIDENCE = 3  # rules-based approximation from centre line, not a survey

# ---------------------------------------------------------------------------
# Connect (same pattern as every other ETL in this project)
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
# Open the run record (audit trail: every ETL is logged win or lose)
# ---------------------------------------------------------------------------
with engine.begin() as conn:
    run_id = conn.execute(text("""
        INSERT INTO metadata.etl_runs (pipeline, started_at, run_status)
        VALUES (:p, now(), 'running') RETURNING run_id
    """), {"p": PIPELINE}).scalar()
print(f"ETL run opened (run_id={run_id})")

try:
    # -----------------------------------------------------------------------
    # Provenance, done honestly. These buffers are DERIVED from the river
    # rows, so we inherit the source_id that most of those rivers carry.
    # That way the catalogue can trace a buffer straight back to the rivers
    # (and through them to OSM), instead of inventing a fake new source.
    # -----------------------------------------------------------------------
    with engine.connect() as conn:
        source_id = conn.execute(text("""
            SELECT source_id FROM environment.rivers
            WHERE source_id IS NOT NULL
            GROUP BY source_id ORDER BY count(*) DESC LIMIT 1
        """)).scalar()

        # How many rivers of each type are we about to process? (sanity check)
        rows = conn.execute(text("""
            SELECT waterway_type, count(*) AS n
            FROM environment.rivers
            WHERE status = 'active'
            GROUP BY waterway_type ORDER BY n DESC
        """)).fetchall()
    print("\nRivers on hand by type (status=active):")
    for wt, n in rows:
        used = WIDTHS.get(wt)
        tag = f"-> buffer {used} m" if used else "-> SKIPPED (not a natural watercourse)"
        print(f"  {str(wt):8} {n:>8,}  {tag}")

    # -----------------------------------------------------------------------
    # Build the buffers.
    #
    # Idempotent by design: this ETL is the ONLY thing that writes to
    # environment.riparian_buffers, so we clear the table and rebuild. Rerun
    # it any time the rivers change and you get a clean, correct result.
    #
    # The VALUES(...) block turns our Python width rules into a tiny lookup
    # table inside SQL, joined to rivers on waterway_type. Any type not listed
    # (i.e. 'drain', or NULL) simply fails the join and is left out.
    #
    # Per row:
    #   ST_Buffer(geom::geography, width) -> grow the band by real meters
    #   ::geometry                        -> back to a plain 4326 geometry
    #   ST_MakeValid                      -> guarantee no self-touching edges
    #   ST_Multi                          -> match the column's MultiPolygon type
    # -----------------------------------------------------------------------
    values_sql = ", ".join(f"('{wt}', {w})" for wt, w in WIDTHS.items())

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM environment.riparian_buffers"))
        n = conn.execute(text(f"""
            INSERT INTO environment.riparian_buffers
                (river_id, buffer_width_m, legal_basis, geom,
                 source_id, source_date, confidence)
            SELECT r.id,
                   w.width_m,
                   :basis,
                   ST_Multi(ST_MakeValid(
                       ST_Buffer(r.geom::geography, w.width_m)::geometry
                   )),
                   :sid, CURRENT_DATE, :conf
            FROM environment.rivers r
            JOIN (VALUES {values_sql}) AS w(wt, width_m)
              ON r.waterway_type = w.wt
            WHERE r.status = 'active'
        """), {"basis": LEGAL_BASIS, "sid": source_id, "conf": CONFIDENCE}).rowcount

    # -----------------------------------------------------------------------
    # Report what landed, grouped by the width that was applied.
    # -----------------------------------------------------------------------
    with engine.connect() as conn:
        summary = conn.execute(text("""
            SELECT buffer_width_m, count(*) AS n
            FROM environment.riparian_buffers
            GROUP BY buffer_width_m ORDER BY buffer_width_m
        """)).fetchall()
    print("\nRiparian buffers created:")
    for width, cnt in summary:
        print(f"  {width} m band : {cnt:>8,} buffers")
    print(f"  {'TOTAL':>6}   : {n:>8,} buffers")

    # -----------------------------------------------------------------------
    # Close the run as success and mark the dataset ingested in the catalogue.
    # -----------------------------------------------------------------------
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = :r
            WHERE run_id = :id
        """), {"r": n, "id": run_id})
        conn.execute(text("""
            UPDATE metadata.datasets SET etl_status = 'ingested', updated_at = now()
            WHERE code = 'environment.riparian_buffers'
        """))

    print(f"\nDONE. Run {run_id} logged as success.")
    print("Verify in pgAdmin / QGIS:")
    print("  - one buffer polygon per river/stream/canal, none for drains")
    print("  - buffers hug the river network as thin corridors")
    print("  - spot-check a wide river: its band should look ~30 m each side")

# BaseException, NOT Exception, and this is load-bearing.
# This script's own guards raise SystemExit, and Ctrl+C raises
# KeyboardInterrupt. Both inherit from BaseException, so an
# `except Exception` handler never fires for them and the
# metadata.etl_runs row is left at 'running' forever. That bug left 12
# orphan rows across a month of work, including runs PROGRESS.md
# documents as failures. The trailing `raise` is unchanged: this logs
# the failure and then gets out of the way.
except BaseException as exc:
    # Any failure: record why, then re-raise so you see the traceback.
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'failed', error_message = :e
            WHERE run_id = :id
        """), {"e": str(exc)[:2000], "id": run_id})
    raise
