"""
============================================================================
VERIFY 23 - does NDVI find the farmland WorldCover missed?
Land Intelligence Platform - Geocode Spatial Solutions Ltd

Read-only. Writes nothing, changes nothing.

WHY THIS SCRIPT EXISTS
etl_19 mapped only 4.46% of Kenya as cropland, because WorldCover's cropland
class under-detects smallholder mosaic farming: small mixed plots with scrub
and trees between them classify as shrubland or grassland. That is most of
Kenyan agriculture. If we shipped land cover alone, the platform could tell a
buyer "this is not farmland" about a shamba someone farms.

NDVI was added to close that hole. So the question is not "does the NDVI layer
look nice". It is: DOES IT SEE GREEN, CULTIVATED-LOOKING GROUND IN PLACES
WORLDCOVER CALLED SHRUBLAND? This script measures that, in square kilometres.

TWO TESTS, IN THE RIGHT ORDER
1. Does NDVI rank WorldCover's classes the way physics demands? Closed forest
   must be greener than cropland, cropland greener than shrubland, shrubland
   greener than bare ground, and open water lowest of all. Two products built
   by different organisations from different sensors. If they agree on that
   ordering, both are placed correctly and NDVI is measuring what we think.
   This must pass BEFORE test 2 means anything: a misplaced NDVI layer would
   also show "unexpected greenness in shrubland", for the wrong reason.
2. Only then: how much shrubland and grassland is as green as cropland?

THRESHOLDS ARE DERIVED FROM THE DATA, NOT ASSUMED
Four tests earlier in this session failed because I picked a threshold from a
class name or a remembered figure before looking at how the data was actually
distributed. So this script prints every distribution BEFORE judging anything,
and the "cultivated-like" threshold is taken from the observed NDVI of pixels
WorldCover is confident are cropland, not from a number I chose.

How to run (from 03_etl with venv active):
  python verify_23_ndvi.py
============================================================================
"""

import os
import sys
import json
from pathlib import Path

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask
except ImportError:
    sys.exit("ERROR: rasterio missing. With venv active: pip install rasterio")

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
SAT = PROJECT / "06_rasters" / "cog" / "satellite"
NDVI = next(SAT.glob("satellite_ndvi_s2geomedian_*.tif"), None)
LC = SAT / "satellite_landcover_esaworldcover_10m_2021.tif"

SCALE = 0.0001
NDVI_NODATA = -32768
LC_NODATA = 0
SUB = 4          # analyse every 4th NDVI pixel: ~152 m

CLASSES = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
           50: "Built-up", 60: "Bare / sparse", 70: "Snow and ice",
           80: "Permanent water", 90: "Herbaceous wetland", 95: "Mangroves",
           100: "Moss and lichen"}

# Physics demands this ordering. Not a preference, a constraint.
MUST_RANK = ["Permanent water", "Bare / sparse", "Grassland", "Shrubland",
             "Cropland", "Tree cover"]

SPOTS = [
    ("Kakamega Forest",   34.860,  0.350, "closed forest, expect very high"),
    ("Kericho tea",       35.350, -0.400, "tea, evergreen, expect high"),
    ("Mt Kenya forest",   37.200, -0.200, "montane forest, expect high"),
    ("Maasai Mara",       35.100, -1.500, "grassland, expect moderate"),
    ("Kitui shrubland",   38.300, -1.500, "dry shrub, expect low-moderate"),
    ("Chalbi desert",     37.300,  3.150, "desert, expect very low"),
    ("Lake Turkana",      36.200,  3.550, "open water, expect negative"),
    ("Nairobi CBD",       36.825, -1.283, "dense built, expect low"),
]

if NDVI is None or not NDVI.exists():
    sys.exit("NDVI COG not found. Run etl_23_ndvi_sentinel2.py first.")
if not LC.exists():
    sys.exit(f"Not found: {LC}")

print("=" * 78)
print("NDVI VERIFICATION")
print("=" * 78)
print(f"\nNDVI: {NDVI.name}")

load_dotenv(BASE / ".env")
pw = os.getenv("DB_PASSWORD")
if not pw or pw == "put_your_password_here":
    sys.exit("ERROR: set DB_PASSWORD in .env first.")
engine = create_engine(
    f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
    f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
    f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")
with engine.connect() as conn:
    country = json.loads(conn.execute(text(
        "SELECT ST_AsGeoJSON(ST_Union(geom)) FROM admin.country")).scalar())

with rasterio.open(NDVI) as ns:
    ow, oh = ns.width // SUB, ns.height // SUB
    print(f"  {ns.width:,} x {ns.height:,} px, analysed at {ow:,} x {oh:,}")
    nd = ns.read(1, out_shape=(oh, ow), resampling=Resampling.average)
    t = ns.transform * ns.transform.scale(ns.width / ow, ns.height / oh)
    cell_km2 = (abs(t.a) * 111320) * (abs(t.e) * 110574) / 1e6
    print(f"  analysis cell ~{abs(t.a)*111320:.0f} m "
          f"({cell_km2:.4f} km2 each)")
    inside = geometry_mask([country], out_shape=(oh, ow), transform=t,
                           invert=True)
    with rasterio.open(LC) as ls:
        with WarpedVRT(ls, crs="EPSG:4326", transform=t, width=ow, height=oh,
                       resampling=Resampling.nearest) as v:
            lc = v.read(1)

ok = inside & (nd != NDVI_NODATA) & (lc != LC_NODATA)
ndv = nd.astype("float32") * SCALE
n = int(ok.sum())
print(f"  {n:,} Kenyan cells with both layers")

# ---------------------------------------------------------------------------
# 0. What does normal look like? Background FIRST, before any threshold.
# ---------------------------------------------------------------------------
allv = ndv[ok]
qs = np.percentile(allv, [1, 5, 25, 50, 75, 95, 99])
print("\n" + "-" * 78)
print("0. NDVI DISTRIBUTION ACROSS KENYA (before any judgement)")
print("-" * 78)
print("  percentile    1%     5%    25%    50%    75%    95%    99%")
print("  NDVI      " + "".join(f"{q:>7.3f}" for q in qs))
print(f"  mean {allv.mean():.3f}   min {allv.min():.3f}   max {allv.max():.3f}")

# ---------------------------------------------------------------------------
# 1. Does NDVI rank WorldCover's classes as physics demands?
# ---------------------------------------------------------------------------
print("\n" + "-" * 78)
print("1. MEAN NDVI BY LAND COVER CLASS (the ordering test)")
print("-" * 78)
print(f"  {'class':20}{'mean':>8}{'median':>8}{'p25':>8}{'p75':>8}{'km2':>12}")
means = {}
for code in sorted(CLASSES):
    m = ok & (lc == code)
    c = int(m.sum())
    if c < 100:
        continue
    v = ndv[m]
    means[CLASSES[code]] = float(v.mean())
    print(f"  {CLASSES[code]:20}{v.mean():>8.3f}{np.median(v):>8.3f}"
          f"{np.percentile(v,25):>8.3f}{np.percentile(v,75):>8.3f}"
          f"{c*cell_km2:>12,.0f}")

seq = [c for c in MUST_RANK if c in means]
vals = [means[c] for c in seq]
ordered = all(vals[i] < vals[i+1] for i in range(len(vals)-1))
print("\n  required ordering (physics, not preference):")
print("    " + " < ".join(seq))
print("    " + " < ".join(f"{v:.3f}" for v in vals))
if ordered:
    print("  >> PASS. Two products, different organisations, different "
          "sensors, and they")
    print("     agree on the ordering of vegetation greenness. Both are "
          "correctly placed")
    print("     and NDVI is measuring what we think it measures.")
else:
    print("  >> FAIL. The ordering is broken, so one of the layers is "
          "misplaced or NDVI")
    print("     is not measuring vegetation. Test 2 below is meaningless "
          "until this passes.")

# ---------------------------------------------------------------------------
# 2. The question this layer was built to answer
# ---------------------------------------------------------------------------
print("\n" + "-" * 78)
print("2. HOW MUCH 'SHRUBLAND' IS AS GREEN AS CROPLAND?")
print("-" * 78)
crop = ok & (lc == 40)
if crop.sum() < 1000:
    print("  Too little cropland to derive a threshold.")
else:
    # Threshold taken FROM the data: the 25th percentile of land WorldCover is
    # confident is cropland. Three quarters of known cropland is greener than
    # this, so ground above it is plausibly cultivated.
    thr = float(np.percentile(ndv[crop], 25))
    print(f"  Threshold derived from the data, not chosen: the 25th percentile")
    print(f"  of WorldCover's own cropland is NDVI {thr:.3f}. Three quarters of")
    print(f"  known cropland is greener than this.\n")
    print(f"  {'WorldCover class':20}{'area km2':>12}{'above thr':>12}"
          f"{'share':>9}")
    total_hidden = 0.0
    for code in (20, 30):
        m = ok & (lc == code)
        if m.sum() == 0:
            continue
        above = int((ndv[m] >= thr).sum())
        area = int(m.sum()) * cell_km2
        ha = above * cell_km2
        total_hidden += ha
        print(f"  {CLASSES[code]:20}{area:>12,.0f}{ha:>12,.0f}"
              f"{100.0*above/int(m.sum()):>8.1f}%")
    crop_km2 = int(crop.sum()) * cell_km2
    print(f"\n  WorldCover cropland total            : {crop_km2:,.0f} km2")
    print(f"  Shrub/grass as green as cropland     : {total_hidden:,.0f} km2")
    if crop_km2 > 0:
        print(f"  That is {total_hidden/crop_km2:.1f}x the mapped cropland.")
    print("\n  READ THIS CAREFULLY. Green does not prove cultivated: wet")
    print("  rangeland and dense natural bush are also green, so this figure")
    print("  is an UPPER BOUND on missed farmland, not a measurement of it.")
    print("  What it does establish is that land cover alone cannot answer")
    print("  'is this farmable', and that a large area of Kenya WorldCover")
    print("  calls shrubland is as productive as land it calls cropland.")
    print("\n  PRODUCT RULE: never tell a buyer 'not farmland' from land cover")
    print("  alone. Use NDVI plus rainfall plus soil. Land cover describes the")
    print("  surface; it does not adjudicate potential.")

# ---------------------------------------------------------------------------
# 3. Spot checks, over a neighbourhood rather than one pixel
# ---------------------------------------------------------------------------
print("\n" + "-" * 78)
print("3. SPOT CHECKS (mean NDVI over ~1 km around each point)")
print("-" * 78)
print(f"  {'place':20}{'NDVI':>8}   expectation")
with rasterio.open(NDVI) as ns:
    half = max(1, int(round(500 / (abs(ns.transform.a) * 111320))))
    for name, lon, lat, note in SPOTS:
        row, col = ns.index(lon, lat)
        c0, r0 = max(0, col - half), max(0, row - half)
        w = min(2 * half + 1, ns.width - c0)
        h = min(2 * half + 1, ns.height - r0)
        blk = ns.read(1, window=rasterio.windows.Window(c0, r0, w, h))
        good = blk[blk != NDVI_NODATA]
        val = good.mean() * SCALE if good.size else float("nan")
        print(f"  {name:20}{val:>8.3f}   {note}")

print("\n" + "=" * 78)
print("Done. Nothing was modified.")
print("=" * 78)
