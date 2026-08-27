"""
Quick inspector: shows what's inside the schools zips and the towers .gz,
so we can write the ETLs against the real column names. Read-only.

Run (from 03_etl with venv active):
  python inspect_downloads.py
"""

import gzip
import io
import zipfile
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
SCHOOLS = BASE / "data" / "raw" / "schools"
TOWERS = BASE / "data" / "raw" / "towers"

print("=" * 70)
print("SCHOOLS")
print("=" * 70)
for z in sorted(SCHOOLS.glob("*.zip")):
    print(f"\n--- {z.name} ---")
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            print("   ", n)
        # If there's a CSV inside, show its header + 3 rows
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        for c in csvs[:1]:
            with zf.open(c) as f:
                df = pd.read_csv(f, nrows=3, low_memory=False)
                print(f"   COLUMNS of {c}:")
                print("   ", list(df.columns))
                print(df.head(3).to_string())
        shps = [n for n in zf.namelist() if n.lower().endswith(".shp")]
        if shps:
            print(f"   (shapefile inside: {shps[0]} - will read with geopandas)")

print("\n" + "=" * 70)
print("TOWERS (639.csv.gz)")
print("=" * 70)
gz = TOWERS / "639.csv.gz"
if gz.exists():
    with gzip.open(gz, "rt") as f:
        head = "".join([next(f) for _ in range(3)])
    print("First 3 raw lines:")
    print(head)
    # Try reading as headed CSV
    with gzip.open(gz, "rt") as f:
        df = pd.read_csv(f, nrows=3, low_memory=False)
    print("Parsed columns (if first row is a header):")
    print("   ", list(df.columns))
else:
    print("   639.csv.gz not found")
