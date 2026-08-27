"""
============================================================================
ETL 11 - MOBILE TOWERS (connectivity.towers)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

Source: OpenCellID, Kenya cells (MCC 639), 639.csv.gz. Catalogue PRIMARY
for towers. Crowdsourced cell positions, so locations are approximate
(confidence 2). LICENSING: CC-BY-SA-4.0 (share-alike), review before
commercial use. Tracked as a known licensing issue.

The 639.csv.gz has NO header. OpenCellID's fixed column order is:
  radio, mcc, net, area, cell, unit, lon, lat, range, samples,
  changeable, created, updated, averageSignal

What this script does:
  1. Reads the gzip CSV with explicit column names
  2. Maps radio to our vocabulary and net (MNC) to the operator name
  3. Filters to valid Kenya coordinates
  4. Assigns county by spatial join, loads into connectivity.towers

How to run (from 03_etl with venv active):
  python etl_11_opencellid_towers.py
============================================================================
"""

import os
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv
from shapely.geometry import Point
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
CSV = BASE / "data" / "raw" / "towers" / "639.csv.gz"
SOURCE_NAME = "OpenCellID"          # matches sources.csv
SOURCE_URL = "https://opencellid.org"
SOURCE_DATE = date.today()
PIPELINE = "etl_11_opencellid_towers"

COLS = ["radio", "mcc", "net", "area", "cell", "unit", "lon", "lat",
        "range", "samples", "changeable", "created", "updated", "avg_signal"]

# Kenya mobile network codes (MNC) under MCC 639.
OPERATOR = {2: "Safaricom", 3: "Airtel", 7: "Telkom", 5: "Airtel"}

RADIO_MAP = {"GSM": "gsm", "UMTS": "umts", "LTE": "lte", "NR": "nr",
             "CDMA": "unknown"}


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
        VALUES (:n, 'Unwired Labs / OpenCellID', 4, :u, 'CC-BY-SA-4.0',
                false, true,
                'Crowdsourced cell positions (approximate). Share-alike; '
                'review before commercial use.')
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
    if not CSV.exists():
        raise RuntimeError(f"{CSV} not found.")
    print(f"\nReading {CSV.name} (no header, explicit columns)...")
    df = pd.read_csv(CSV, header=None, names=COLS, low_memory=False)
    print(f"   {len(df):,} cell records read")

    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df = df.dropna(subset=["lon", "lat"])
    df = df[(df["lat"].between(-5.5, 5.5)) & (df["lon"].between(33.5, 42.5))]
    print(f"   {len(df):,} records with valid Kenya coordinates")

    df["op"] = pd.to_numeric(df["net"], errors="coerce").map(
        lambda x: OPERATOR.get(int(x), "other") if pd.notna(x) else "other")
    df["rad"] = df["radio"].astype(str).str.upper().map(RADIO_MAP)\
        .fillna("unknown")
    df["cid"] = df["cell"].astype(str)
    df["gid"] = range(len(df))

    print("   Operators found:")
    for t, c in df["op"].value_counts().items():
        print(f"      {t}: {c:,}")

    gdf = gpd.GeoDataFrame(
        df[["gid", "op", "rad", "cid"]].copy(),
        geometry=[Point(xy) for xy in zip(df["lon"], df["lat"])], crs=4326)

    print(f"   Staging {len(gdf):,} towers...")
    gdf.to_postgis("towers_raw", engine, schema="staging",
                   if_exists="replace", chunksize=20000)

    print("   Assigning counties and loading connectivity.towers...")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX ON staging.towers_raw USING gist (geometry)"))
        conn.execute(text("ANALYZE staging.towers_raw"))
        conn.execute(text(
            "DELETE FROM connectivity.towers WHERE source_id = :sid"),
            {"sid": source_id})
        n = conn.execute(text("""
            INSERT INTO connectivity.towers
                (operator, radio, cell_id, county_code, geom,
                 source_id, source_date, confidence)
            SELECT t.op, t.rad, t.cid, c.county_code, t.geometry,
                   :sid, :sd, 2
            FROM staging.towers_raw t
            LEFT JOIN admin.counties c ON ST_Contains(c.geom, t.geometry)
        """), {"sid": source_id, "sd": SOURCE_DATE}).rowcount

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
            SET finished_at = now(), run_status = 'success', rows_out = :r
            WHERE run_id = :id
        """), {"r": n, "id": run_id})
        conn.execute(text("""
            UPDATE metadata.datasets SET etl_status = 'ingested', updated_at = now()
            WHERE code = 'connectivity.towers'
        """))
    print(f"\nDONE. {n:,} towers loaded. Run {run_id} success.")
    print("Verify: SELECT operator, radio, count(*) FROM connectivity.towers "
          "GROUP BY 1,2 ORDER BY 1,2;")

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
