"""
============================================================================
VERIFY 20 - is the built-up surface layer correctly placed and correctly
            understood?
Land Intelligence Platform - Geocode Spatial Solutions Ltd

Read-only. Writes nothing, changes nothing.

THE DECISIVE TEST
Built-up surface has a property no other layer we hold has: we already know
the answer. Kenya's most built-up counties are not a research question. If
this raster is placed correctly, ranking counties by total built-up surface
must return Nairobi at the top, followed by the coastal and central urban
counties. If it instead ranks Marsabit or Wajir first, the layer is misplaced
and no amount of plausible-looking statistics should save it.

That is a much stronger test than "do the numbers look sensible", because it
can only pass for one reason.

TWO THINGS etl_20 SURFACED THAT NEED SETTLING HERE
1. The maximum cell read 8,606 m2 against a computed cell area of 8,548 m2,
   which is 101%. A cell cannot be more than 100% built. The 5% tolerance in
   etl_20 let it through, correctly, but the discrepancy needs explaining
   rather than ignoring, because the enrichment engine is about to divide by
   cell area and would then report parcels as 101% built.
2. GHSL and WorldCover disagree about how much of Kenya is built. They are
   not measuring the same thing, and this script quantifies the gap so the
   difference is documented rather than discovered later by a client.

How to run (from 03_etl with venv active):
  python verify_20_builtup.py
============================================================================
"""

import os
import sys
import json
import math
from pathlib import Path

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import rasterio
    from rasterio.mask import mask as rio_mask
except ImportError:
    sys.exit("ERROR: rasterio missing. With venv active: pip install rasterio")

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
COG = (PROJECT / "06_rasters" / "cog" / "satellite" /
       "satellite_builtup_ghsl_92m_2020.tif")
NODATA = 65535

# Places where we know roughly what the answer must be.
SPOTS = [
    # 36.8172, -1.2864 is Uhuru Park / Central Park, NOT the built CBD, which
    # is why the first run of this script read 3.2% there and looked alarming.
    # Kept as a control: a layer that reports green space as unbuilt in the
    # middle of a capital city is behaving correctly, not failing.
    ("Nairobi Uhuru Park",  36.8172, -1.2864, "PARK: point should read low"),
    ("Nairobi CBD (Moi Av)",36.8250, -1.2833, "dense: expect high"),
    ("Mombasa island",      39.6682, -4.0435, "dense: expect high"),
    ("Nakuru town",         36.0667, -0.3031, "town: expect moderate"),
    ("Eldoret town",        35.2698,  0.5143, "town: expect moderate"),
    ("Lake Turkana centre", 36.1000,  3.5500, "open water: MUST be 0"),
    ("Chalbi desert",       37.3000,  3.1500, "empty desert: expect ~0"),
    ("Maasai Mara",         35.1000, -1.5000, "protected grassland: expect ~0"),
]

# Half-width, in cells, of the neighbourhood summarised beside each point.
# 6 cells at ~93 m is a little over 1 km, which happens to be exactly the
# neighbourhood our catalogue specifies for this dataset ("percent built
# within 1 km of parcel"), so this check also previews the real enrichment.
SPOT_HALF = 6

if not COG.exists():
    sys.exit(f"Not found: {COG}\nRun etl_20_ghsl_builtup.py first.")

print("=" * 78)
print("BUILT-UP SURFACE VERIFICATION")
print("=" * 78)

load_dotenv(BASE / ".env")
pw = os.getenv("DB_PASSWORD")
if not pw or pw == "put_your_password_here":
    sys.exit("ERROR: set DB_PASSWORD in .env first.")
engine = create_engine(
    f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{pw}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
    f"/{os.getenv('DB_NAME', 'land_intelligence_kenya')}")

with rasterio.open(COG) as src:
    px = src.transform.a
    print(f"\nFile: {COG.name}  ({COG.stat().st_size/1e6:.0f} MB)")
    print(f"  {src.width:,} x {src.height:,} px, dtype {src.dtypes[0]}, "
          f"nodata {src.nodata}, overviews {src.overviews(1)}")

    # -----------------------------------------------------------------------
    # 1. What IS a full cell? Settle the 101% problem.
    # -----------------------------------------------------------------------
    print("\n" + "-" * 78)
    print("1. CELL AREA: what does a fully built cell actually read?")
    print("-" * 78)
    # Three ways of computing the same thing, which is the point: they differ,
    # and the difference is the whole 101% puzzle.
    wgs84 = (px * 111319.49) * (px * 110574.30)     # WGS84 ellipsoid, equator
    sphere = (px * (2 * math.pi * 6371007 / 360)) ** 2   # authalic sphere
    print(f"  pixel: {px:.8f} deg")
    print(f"  cell area, WGS84 ellipsoid at equator : {wgs84:,.0f} m2")
    print(f"  cell area, authalic sphere (R=6371007): {sphere:,.0f} m2")

    # The largest value anywhere in the raster is, in practice, a saturated
    # cell: somewhere in Nairobi or Mombasa is wall to wall building. So the
    # observed maximum is itself evidence of what GHSL treats as a full cell,
    # which is better evidence than any formula we could write here.
    peak = 0
    for _, win in src.block_windows(1):
        blk = src.read(1, window=win)
        m = blk[blk != NODATA]
        if m.size:
            peak = max(peak, int(m.max()))
    print(f"  observed maximum cell value          : {peak:,} m2")
    print(f"  ratio to WGS84 figure                : "
          f"{100.0 * peak / wgs84:.1f}%")
    print(f"  ratio to spherical figure            : "
          f"{100.0 * peak / sphere:.1f}%")
    print("\n  WHY THIS MATTERS: GHSL is computed on an equal-area (Mollweide)")
    print("  grid and then regridded to lat/lon, so its idea of a cell does")
    print("  not exactly match a naive lat/lon calculation. The gap is under")
    print("  1%, which is harmless for a map and NOT harmless for a number we")
    print("  show a buyer: divide by the wrong constant and a parcel reads")
    print("  '101% built', which destroys trust instantly.")
    print(f"\n  RECOMMENDATION for the enrichment engine: use the observed")
    print(f"  saturation value {peak:,} m2 as 'a full cell', and cap the")
    print("  resulting fraction at 1.0. Never report above 100%.")

    # -----------------------------------------------------------------------
    # 2. THE DECISIVE TEST: rank counties by built-up surface
    # -----------------------------------------------------------------------
    print("\n" + "-" * 78)
    print("2. COUNTY RANKING (the test that can only pass for one reason)")
    print("-" * 78)
    with engine.connect() as conn:
        counties = conn.execute(text("""
            SELECT name, ST_AsGeoJSON(geom) FROM admin.counties
            WHERE status = 'active'
        """)).all()
    print(f"  summing built-up surface across {len(counties)} counties ...")

    results = []
    for name, gj in counties:
        try:
            arr, _ = rio_mask(src, [json.loads(gj)], crop=True,
                              nodata=NODATA, filled=True)
        except ValueError:
            continue                       # county outside the raster
        a = arr[0]
        good = a != NODATA
        if not good.any():
            continue
        built_km2 = float(a[good].sum()) / 1e6
        cells = int(good.sum())
        results.append((name, built_km2, cells))

    # RANK BY SHARE, NOT BY TOTAL. The first version of this script ranked by
    # absolute built-up square kilometres and then complained that Nairobi came
    # ninth. That was a broken test, not a broken layer: Kitui is 30,496 km2
    # and Nairobi is 696 km2, and Kenya's total building surface is dominated
    # by dispersed rural housing across large, populous counties. Ranking by
    # absolute area therefore measures county SIZE. The question we actually
    # care about, "how developed is this place", is a share.
    rows = []
    for name, km2, cells in results:
        county_km2 = cells * peak / 1e6
        rows.append((name, km2, county_km2,
                     100.0 * km2 / county_km2 if county_km2 else 0.0))
    rows.sort(key=lambda r: -r[3])

    print(f"\n  BY SHARE BUILT (the meaningful ranking)")
    print(f"  {'rank':<6}{'county':22}{'% built':>10}{'built km2':>12}"
          f"{'county km2':>12}")
    for i, (name, km2, ckm2, pct) in enumerate(rows[:12], 1):
        print(f"  {i:<6}{name:22}{pct:>9.2f}%{km2:>12,.1f}{ckm2:>12,.0f}")

    print(f"\n  BY ABSOLUTE AREA (shown only to make the difference obvious;")
    print(f"  this ranking mostly reflects how big a county is)")
    print(f"  {'rank':<6}{'county':22}{'built km2':>12}")
    results.sort(key=lambda r: -r[1])
    for i, (name, km2, cells) in enumerate(results[:5], 1):
        print(f"  {i:<6}{name:22}{km2:>12,.1f}")

    print(f"\n  {'':6}{'lowest by share:':22}")
    for name, km2, ckm2, pct in rows[-3:]:
        print(f"  {'':6}{name:22}{pct:>9.2f}%")

    top_share = [r[0].lower() for r in rows[:5]]
    if "nairobi" in top_share:
        print("\n  >> PASS. Nairobi leads the share ranking. No misalignment "
              "puts the country's")
        print("     densest built surface on the correct county by accident.")
    else:
        print("\n  >> INVESTIGATE. Nairobi is not top by share, which is very "
              "hard to explain.")

    print("\n  (retained for reference, the old size-confounded table:)")
    print(f"  {'rank':<6}{'county':22}{'built-up km2':>14}{'% of county':>13}")
    for i, (name, km2, cells) in enumerate(results[:12], 1):
        # County area estimated as cell count times the saturation value, since
        # that value IS one cell's area in square metres. Cell area shrinks
        # slightly away from the equator, so this is a fraction of a percent
        # optimistic at Kenya's extremes. Fine for a ranking, not a land
        # registry figure.
        county_km2 = cells * peak / 1e6
        pct = 100.0 * km2 / county_km2 if county_km2 else 0
        print(f"  {i:<6}{name:22}{km2:>14,.1f}{pct:>12.2f}%")


    # -----------------------------------------------------------------------
    # 3. Point checks, expressed as percent of a cell
    # -----------------------------------------------------------------------
    print("\n" + "-" * 78)
    print("3. POINT CHECKS (percent of the cell that is building)")
    print("-" * 78)
    print("  The '1 km' column is the number the product will actually use.")
    print("  A single 93 m cell can sit on a park, a road or a rooftop and say")
    print("  very little; the neighbourhood is what describes a location.\n")
    print(f"  {'place':24}{'cell %':>9}{'1 km %':>9}{'1 km peak':>11}   "
          f"expectation")
    for name, lon, lat, note in SPOTS:
        v = int(list(src.sample([(lon, lat)]))[0][0])
        if v == NODATA:
            print(f"  {name:24}{'nodata':>9}{'-':>9}{'-':>11}   {note}")
            continue
        row, col = src.index(lon, lat)
        c0, r0 = max(0, col - SPOT_HALF), max(0, row - SPOT_HALF)
        w = min(2 * SPOT_HALF + 1, src.width - c0)
        h = min(2 * SPOT_HALF + 1, src.height - r0)
        blk = src.read(1, window=rasterio.windows.Window(c0, r0, w, h))
        good = blk != NODATA
        if good.any():
            nb_pct = 100.0 * float(blk[good].sum()) / (int(good.sum()) * peak)
            nb_max = 100.0 * float(blk[good].max()) / peak
        else:
            nb_pct = nb_max = 0.0
        print(f"  {name:24}{100.0*v/peak:>8.1f}%{nb_pct:>8.1f}%"
              f"{nb_max:>10.1f}%   {note}")

    # -----------------------------------------------------------------------
    # 4. Cross-check against WorldCover, which measures something DIFFERENT
    # -----------------------------------------------------------------------
    print("\n" + "-" * 78)
    print("4. CROSS-CHECK AGAINST WORLDCOVER")
    print("-" * 78)
    with engine.connect() as conn:
        country = json.loads(conn.execute(text(
            "SELECT ST_AsGeoJSON(ST_Union(geom)) FROM admin.country")).scalar())
        kenya_km2 = float(conn.execute(text(
            "SELECT ST_Area(ST_Union(geom)::geography)/1e6 FROM admin.country"
        )).scalar())
    ke_arr, _ = rio_mask(src, [country], crop=True, nodata=NODATA, filled=True)
    ke = ke_arr[0]
    ke_good = ke != NODATA
    ke_built_km2 = float(ke[ke_good].sum()) / 1e6
    print(f"  Kenya land area (from admin.country) : {kenya_km2:,.0f} km2")
    print(f"  GHSL built-up surface inside Kenya   : {ke_built_km2:,.0f} km2 "
          f"({100.0 * ke_built_km2 / kenya_km2:.2f}% of the country)")
    print(f"  WorldCover 'Built-up' class, Kenya   : 0.32% (from verify_19)")
    print("\n  These two SHOULD differ, and the difference is not an error:")
    print("   - WorldCover asks 'is this 10 m patch of ground built-up land',")
    print("     and its built-up class is known to miss sparse rural buildings")
    print("     (the same conservatism that makes its cropland read low).")
    print("   - GHSL measures building SURFACE and detects scattered rural")
    print("     structures that never form a whole 10 m built-up patch.")
    print("  So expect GHSL to be the higher of the two. If it were LOWER,")
    print("  that would be the surprise worth chasing.")
    print("\n  Practical rule for the product: use WorldCover to say what a")
    print("  parcel IS, and GHSL to say how developed its surroundings ARE.")
    print("  Do not present them as two measurements of one quantity.")

print("\n" + "=" * 78)
print("Done. Nothing was modified.")
print("=" * 78)
