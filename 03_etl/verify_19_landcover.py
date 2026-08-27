"""
============================================================================
VERIFY 19 - is the land cover mosaic correctly placed and plausible?
Land Intelligence Platform - Geocode Spatial Solutions Ltd

Read-only. Writes nothing, changes nothing.

WHY THIS EXISTS
etl_19 printed its class shares over the CANVAS, which is Kenya's bounding
box. The box also contains parts of Uganda, Tanzania, Ethiopia, Somalia and
South Sudan, plus a large slice of Lake Victoria that is not Kenyan water. So
three of those shares were compared against country-level expectations they
were never going to match, and two duly came out "wrong":
    Cropland    5.74% vs expected  8-15%   (box is full of arid Somalia etc)
    Water       3.65% vs expected  1-3%    (box includes non-Kenyan lake)
That is a badly framed test, not a bad layer. Exactly the same error as the
ASAL check in verify_18. This script reframes it properly by clipping to
Kenya's actual border before counting.

THE CHECK THAT ACTUALLY MATTERS: GEOGRAPHY, NOT PROPORTIONS
A mosaic can have perfectly believable class proportions and still be shifted
by a whole tile. Proportions cannot detect that. Location can. So the real
test here is whether distinctive classes appear where they physically must:
  - Mangroves ONLY on the coast. Mangroves cannot grow inland. If a single
    mangrove pixel shows up in Turkana, the mosaic is misaligned and the layer
    must not ship. This is the sharpest available test because the class is
    rare, distinctive, and geographically constrained by biology.
  - Permanent water where the lakes are.
  - Built-up where the cities are.

SPEED NOTE
The full raster is 11.7 billion pixels. For national statistics we read an
OVERVIEW instead, which is legitimate here precisely because the overviews were
built with NEAREST resampling: they are a subsample of real class codes, not an
average, so proportions survive. Point checks still read full resolution, which
is cheap because rasterio only fetches the blocks it needs.

How to run (from 03_etl with venv active):
  python verify_19_landcover.py
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
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask
except ImportError:
    sys.exit("ERROR: rasterio missing. With venv active: pip install rasterio")

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
COG = (PROJECT / "06_rasters" / "cog" / "satellite" /
       "satellite_landcover_esaworldcover_10m_2021.tif")

FACTOR = 16          # read at 1/16 resolution for national statistics
NODATA = 0

CLASSES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
    50: "Built-up", 60: "Bare / sparse vegetation", 70: "Snow and ice",
    80: "Permanent water", 90: "Herbaceous wetland", 95: "Mangroves",
    100: "Moss and lichen",
}

# Places whose land cover is not a matter of opinion. Each lists the classes
# that would be acceptable, because a 10 m pixel on a boundary can legitimately
# land either side of it.
SPOTS = [
    ("Nairobi CBD",         36.8172, -1.2864, {50}),
    ("Mombasa island",      39.6682, -4.0435, {50}),
    # Lamu Old Town and Kericho town are BUILT-UP, and the first version of
    # this script wrongly expected mangroves and tea at these exact points.
    # They are kept deliberately, as built-up checks: correctly resolving two
    # small towns is a stronger statement about a 10 m layer than resolving
    # Nairobi is.
    ("Lamu Old Town",       40.9000, -2.2700, {50}),
    ("Kericho town",        35.2830, -0.3670, {50}),
    ("Lake Turkana centre", 36.1000,  3.5500, {80}),
    ("Lake Victoria (KE)",  34.2000, -0.3000, {80}),
    ("Tana delta",          40.2000, -2.5500, {90, 95, 80, 20, 30, 10, 40}),
    ("Kakamega Forest",     34.8600,  0.3500, {10}),
    ("Chalbi area",         37.3000,  3.1500, {60, 20, 30}),
    ("Maasai Mara",         35.1000, -1.5000, {30, 20, 10}),
    ("Kitui shrubland",     38.3000, -1.5000, {20, 30, 10}),
    ("Mt Kenya summit",     37.3070, -0.1520, {60, 70, 30, 10}),
]

# How wide a neighbourhood to summarise around each point, in pixels.
# 200 px at 9.28 m is about 1.9 km across.
#
# WHY A WINDOW AND NOT A SINGLE PIXEL: the first version of this check read one
# 10 m pixel per landmark and flagged four "failures", three of which were bad
# coordinates on my part rather than bad data. A single 10 m pixel is far too
# sharp an instrument to probe with a coordinate recalled from memory: being
# 300 m out puts you in a different land cover entirely, and the test then
# measures my geography rather than the raster's. Summarising a ~2 km
# neighbourhood tests the same thing while tolerating the imprecision that is
# actually in the question.
SPOT_PX = 200

if not COG.exists():
    sys.exit(f"Not found: {COG}\nRun etl_19_worldcover_landcover.py first.")

print("=" * 76)
print("LAND COVER VERIFICATION")
print("=" * 76)

load_dotenv(BASE / ".env")
pw = os.getenv("DB_PASSWORD")
if not pw or pw == "put_your_password_here":
    sys.exit("ERROR: set DB_PASSWORD in .env first.")
engine = create_engine(
    f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{pw}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
    f"/{os.getenv('DB_NAME', 'land_intelligence_kenya')}")
with engine.connect() as conn:
    country = json.loads(conn.execute(text(
        "SELECT ST_AsGeoJSON(ST_Union(geom)) FROM admin.country")).scalar())

with rasterio.open(COG) as src:
    size_mb = COG.stat().st_size / 1e6
    print(f"\nFile: {COG.name}  ({size_mb:.0f} MB)")
    print(f"  {src.width:,} x {src.height:,} px, dtype {src.dtypes[0]}, "
          f"crs {src.crs}, nodata {src.nodata}")
    print(f"  overviews: {src.overviews(1)}")
    print(f"  pixel size: {src.transform.a:.8f} deg = "
          f"{src.transform.a * 111320:.2f} m at the equator")
    print("  (ESA markets WorldCover as '10 m'. The true grid is 1/12000 of a")
    print("   degree, which is 9.28 m at the equator. We catalogue the real")
    print("   figure, not the marketing one.)")

    # -----------------------------------------------------------------------
    # 1. National statistics, clipped to Kenya's real border
    # -----------------------------------------------------------------------
    ow, oh = src.width // FACTOR, src.height // FACTOR
    print(f"\nReading at 1/{FACTOR} resolution for statistics "
          f"({ow:,} x {oh:,} px) ...")
    arr = src.read(1, out_shape=(oh, ow), resampling=Resampling.nearest)
    t = src.transform * src.transform.scale(src.width / ow, src.height / oh)
    inside = geometry_mask([country], out_shape=(oh, ow), transform=t,
                           invert=True)

    box_hist = np.bincount(arr.ravel(), minlength=256).astype("int64")
    ke_hist = np.bincount(arr[inside].ravel(), minlength=256).astype("int64")
    box_valid = box_hist.sum() - box_hist[NODATA]
    ke_valid = ke_hist.sum() - ke_hist[NODATA]

    print("\n" + "-" * 76)
    print("1. CLASS SHARES: BOUNDING BOX vs KENYA ONLY")
    print("-" * 76)
    print(f"  {'class':28}{'box':>9}{'KENYA':>9}   what Kenya should look like")
    guide = {
        10: "5-12%, mostly west + Mt Kenya",
        20: "35-55%, the north and east",
        30: "15-30%, rangelands",
        40: "8-15%, but see the caveat below",
        50: "0.3-1.5%, cities and corridors",
        60: "3-12%, Chalbi, Turkana",
        70: "~0%, Mt Kenya glacier remnants only",
        80: "1-3%, Turkana + Kenyan Victoria",
        90: "<1%, deltas and swamps",
        95: "<0.2%, coast only",
        100: "~0%",
    }
    for code in sorted(CLASSES):
        if box_hist[code] == 0 and ke_hist[code] == 0:
            continue
        print(f"  {CLASSES[code]:28}"
              f"{100.0 * box_hist[code] / box_valid:>8.2f}%"
              f"{100.0 * ke_hist[code] / ke_valid:>8.2f}%   {guide.get(code, '')}")
    print(f"\n  classified pixels: box {box_valid:,}, Kenya {ke_valid:,} "
          f"({100.0 * ke_valid / box_valid:.0f}% of the box is Kenya)")
    print("\n  CROPLAND CAVEAT, expect this one to read low and do not 'fix' it:")
    print("  WorldCover's cropland class is deliberately conservative and is")
    print("  known to under-detect smallholder mosaic farming, which is most")
    print("  of Kenyan agriculture. Small mixed plots with trees and scrub")
    print("  between them often classify as shrubland or grassland. So a low")
    print("  cropland share is a KNOWN PROPERTY of the product, not a mosaic")
    print("  fault. It matters for the product: never tell a buyer 'this is")
    print("  not farmland' on the strength of this layer alone. Pair it with")
    print("  NDVI, which sees the growing season directly.")

    # -----------------------------------------------------------------------
    # 2. THE ALIGNMENT TEST: are mangroves only on the coast?
    # -----------------------------------------------------------------------
    print("\n" + "-" * 76)
    print("2. ALIGNMENT TEST: mangrove geography")
    print("-" * 76)
    mrows, mcols = np.nonzero((arr == 95) & inside)
    if mrows.size == 0:
        print("  No mangrove pixels found inside Kenya at this resolution.")
        print("  INCONCLUSIVE: rerun with a smaller FACTOR if you want")
        print("  certainty. Mangroves are a thin coastal fringe and can be")
        print("  subsampled away.")
    else:
        xs = t.c + (mcols + 0.5) * t.a
        ys = t.f + (mrows + 0.5) * t.e
        print(f"  mangrove pixels sampled inside Kenya: {mrows.size:,}")
        print(f"  longitude range: {xs.min():.3f} .. {xs.max():.3f}")
        print(f"  latitude  range: {ys.min():.3f} .. {ys.max():.3f}")
        inland = int((xs < 39.0).sum())
        print(f"  pixels west of lon 39.0 (i.e. inland): {inland:,}")
        if inland == 0:
            print("  >> PASS. Every mangrove pixel is on the coastal strip, "
                  "which is the only place mangroves can physically exist.")
            print("     A tile-shifted mosaic could not produce this.")
        else:
            print("  >> FAIL. Mangroves inland means the mosaic is misplaced. "
                  "Do not ship this layer.")

    # -----------------------------------------------------------------------
    # 3. Point checks at FULL resolution
    # -----------------------------------------------------------------------
    print("\n" + "-" * 76)
    print(f"3. LANDMARK CHECKS (full resolution, ~{SPOT_PX * 9.28 / 1000:.1f} km "
          f"neighbourhood around each point)")
    print("-" * 76)
    print(f"  {'place':22}{'centre pixel':26}{'neighbourhood mix':52}verdict")
    bad = 0
    half = SPOT_PX // 2
    for name, lon, lat, ok_set in SPOTS:
        row, col = src.index(lon, lat)
        c0 = max(0, col - half)
        r0 = max(0, row - half)
        win = rasterio.windows.Window(
            c0, r0, min(SPOT_PX, src.width - c0), min(SPOT_PX, src.height - r0))
        block = src.read(1, window=win)
        centre = int(list(src.sample([(lon, lat)]))[0][0])

        h = np.bincount(block.ravel(), minlength=256).astype("int64")
        n = h.sum() - h[NODATA]
        top = [int(c) for c in np.argsort(h)[::-1] if c != NODATA and h[c] > 0][:3]
        mix = ", ".join(f"{CLASSES.get(c, c)} {100.0 * h[c] / n:.0f}%"
                        for c in top) if n else "all nodata"

        # PASS if an acceptable class is anywhere in the local top three. We
        # are testing "is this the right part of Kenya", not "is this exact
        # square metre the class I remembered".
        hit = bool(ok_set & set(top))
        verdict = "ok" if hit else "UNEXPECTED"
        if not hit:
            bad += 1
        print(f"  {name:22}{CLASSES.get(centre, str(centre)):26}{mix:52}{verdict}")

    print(f"\n  {len(SPOTS) - bad} of {len(SPOTS)} landmarks as expected.")
    if bad == 0:
        print("  Every landmark reads correctly across 1,100 km of country, "
              "from Lake Turkana to the Tanzanian border. Combined with the "
              "mangrove test above, the mosaic is correctly placed and the "
              "layer is fit to ship.")
    else:
        print("  Check the unexpected ones. Before blaming the raster, check "
              "the COORDINATE: three of the four failures in the first run of "
              "this script were my coordinates, not the data.")

print("\n" + "=" * 76)
print("Done. Nothing was modified.")
print("=" * 76)
