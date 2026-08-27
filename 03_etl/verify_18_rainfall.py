"""
============================================================================
VERIFY 18 - does the rainfall layer agree with reality?
Land Intelligence Platform - Geocode Spatial Solutions Ltd

Read-only. Touches no data, writes nothing, changes nothing in the database.

etl_18 reported a national mean of 712 mm, a minimum of 167 mm and a MAXIMUM
of 3,492 mm. The mean and minimum are unremarkable for Kenya. The maximum is
not: Kenya's wettest places (Kakamega forest, the Kericho tea belt, the
windward slopes of Mt Kenya and Mt Elgon) sit around 1,800 to 2,400 mm a year.
3,492 mm would be a wetter place than anywhere in the country.

There is an innocent explanation and a guilty one, and they are easy to tell
apart:
  INNOCENT - the pixel is outside Kenya. We averaged a padded BOUNDING BOX,
             which also contains eastern Uganda, the Lake Victoria basin,
             northern Tanzania, southern Ethiopia and part of Somalia. Some of
             those are genuinely wetter than anywhere in Kenya.
  GUILTY   - the pixel is inside Kenya, in which case something is wrong with
             the averaging and the layer should not ship.

This script settles it by printing WHERE the maximum actually is, and by
recomputing the statistics clipped to Kenya's real border instead of the box.

It also checks the layer against fourteen towns whose long-term rainfall is
well documented, which is the honest test: not "do the numbers look sensible"
but "does this raster say the right thing about places we can independently
verify". Expect agreement within roughly 25 percent. CHIRPS is a satellite and
gauge blend at 5 km, so a single town pixel is an area average, not the reading
from that town's rain gauge, and mountain stations differ most.

How to run (from 03_etl with venv active):
  python verify_18_rainfall.py
============================================================================
"""

import os
import sys
import json
from pathlib import Path

# Same PROJ/GDAL fix as every other raster script here. Must precede rasterio.
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
COG = (PROJECT / "06_rasters" / "cog" / "climate" /
       "climate_rainfall_chirps_5km_1991-2020.tif")

# Long-term annual rainfall for places with decades of record. These are
# published climatological means, deliberately spread from the wettest west to
# the driest north east so a systematic bias would show up as a pattern rather
# than as one odd town.
TOWNS = [
    # name,        lon,      lat,     published mean mm/yr (approx)
    ("Kakamega",   34.752,   0.283,   1900),
    ("Kericho",    35.283,  -0.367,   1900),
    ("Kisumu",     34.768,  -0.092,   1300),
    ("Eldoret",    35.269,   0.514,   1100),
    ("Kitale",     35.006,   1.019,   1100),
    ("Nyeri",      36.951,  -0.420,   1000),
    # Meru and Embu sit on the eastern flank of Mt Kenya, close to the pixel
    # that produced the suspicious maximum. If the layer is running hot in
    # that massif specifically, these two will show it.
    ("Meru",       37.650,   0.047,   1250),
    ("Embu",       37.450,  -0.531,   1200),
    ("Mombasa",    39.668,  -4.043,   1050),
    ("Nairobi",    36.817,  -1.286,    900),
    ("Nakuru",     36.067,  -0.303,    900),
    ("Machakos",   37.263,  -1.518,    700),
    ("Voi",        38.566,  -3.396,    550),
    ("Garissa",    39.658,  -0.457,    350),
    ("Wajir",      40.057,   1.747,    300),
    ("Lodwar",     35.597,   3.119,    200),
]

if not COG.exists():
    sys.exit(f"Not found: {COG}\nRun etl_18_chirps_rainfall.py first.")

print("=" * 74)
print("RAINFALL LAYER VERIFICATION")
print("=" * 74)

size_b = COG.stat().st_size
print(f"\nFile: {COG.name}")
print(f"  size on disk: {size_b:,} bytes ({size_b / 1e6:.3f} MB)")
print("  (etl_18 printed '0.0 MB' because it rounded to one decimal. A 5 km")
print("   grid over Kenya is only about 34,000 pixels, so a small file is")
print("   CORRECT here, unlike the 30 m layers. This line proves it is not 0.)")

with rasterio.open(COG) as src:
    print(f"  grid: {src.width} x {src.height} px, dtype {src.dtypes[0]}, "
          f"crs {src.crs}, nodata {src.nodata}")
    print(f"  bounds: lon {src.bounds.left:.3f}..{src.bounds.right:.3f}, "
          f"lat {src.bounds.bottom:.3f}..{src.bounds.top:.3f}")
    print(f"  overviews: {src.overviews(1)}")

    band = src.read(1)
    nd = src.nodata
    good = band != nd

    # ---------------------------------------------------------------------
    # 1. WHERE is the maximum? This is the question that matters.
    # ---------------------------------------------------------------------
    flat_idx = np.argmax(np.where(good, band, -32768))
    ry, rx = np.unravel_index(flat_idx, band.shape)
    # float() is NOT decoration. src.xy returns np.float64, and psycopg2 sends
    # a NumPy scalar to Postgres as its repr, "np.float64(37.925)", which the
    # server reads as schema "np". Cast NumPy scalars to plain Python types
    # before they go anywhere near SQL.
    mx_lon, mx_lat = (float(v) for v in src.xy(ry, rx))
    print("\n" + "-" * 74)
    print("1. LOCATION OF THE MAXIMUM")
    print("-" * 74)
    print(f"  max value : {int(band[ry, rx]):,} mm/year")
    print(f"  located at: lon {mx_lon:.3f}, lat {mx_lat:.3f}")

    # Is the peak a coherent wet REGION or a single spiking pixel? A real
    # mountain rainfall maximum has wet neighbours, because rain falls over
    # slopes, not over one 5 km square. A lone spike surrounded by much drier
    # pixels is an artefact. This is the difference between "unusually wet
    # place" and "broken pixel", and it is not visible from the max alone.
    y0, y1 = max(0, ry - 1), min(band.shape[0], ry + 2)
    x0, x1 = max(0, rx - 1), min(band.shape[1], rx + 2)
    nb = band[y0:y1, x0:x1]
    nbg = nb[nb != nd]
    print(f"  3x3 neighbourhood: min {nbg.min():,} max {nbg.max():,} "
          f"mean {nbg.mean():,.0f} mm")
    print("    neighbours near the peak => a real wet massif;")
    print("    neighbours far below it  => a single-pixel artefact.")

    # The ten wettest pixels, so we can see whether the top of the
    # distribution clusters in one plausible massif or scatters at random.
    print("\n  ten wettest pixels:")
    order = np.argsort(np.where(good, band, -32768), axis=None)[::-1][:10]
    for k, fi in enumerate(order, 1):
        yy, xx = np.unravel_index(fi, band.shape)
        lo, la = (float(v) for v in src.xy(yy, xx))
        print(f"    {k:>2}. {int(band[yy, xx]):>5,} mm  at lon {lo:.3f}, "
              f"lat {la:.3f}")

    # ---------------------------------------------------------------------
    # 2. Statistics for the BOX versus statistics for KENYA ONLY.
    # ---------------------------------------------------------------------
    load_dotenv(BASE / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit("ERROR: set DB_PASSWORD in .env first.")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{pw}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
        f"/{os.getenv('DB_NAME', 'land_intelligence_kenya')}")

    with engine.connect() as conn:
        geo = conn.execute(text(
            "SELECT ST_AsGeoJSON(ST_Union(geom)) FROM admin.country"
        )).scalar()
        # Is the maximum pixel inside Kenya, yes or no? The database already
        # holds the authoritative border, so we ask it rather than eyeballing.
        inside = conn.execute(text("""
            SELECT ST_Contains(ST_Union(geom),
                               ST_SetSRID(ST_MakePoint(:x, :y), 4326))
            FROM admin.country
        """), {"x": mx_lon, "y": mx_lat}).scalar()
    print(f"  inside Kenya's border? {'YES' if inside else 'NO'}")
    if inside:
        print("  >> INSIDE Kenya. Judge it on the neighbourhood and the town "
              "check below: a coherent wet massif with good town agreement is "
              "believable, an isolated spike is not.")
    else:
        print("  >> OUTSIDE. The maximum sits in the padded bounding box, not "
              "in Kenya. Expected, and harmless: parcels are sampled by "
              "location, so a pixel abroad is never read for a Kenyan parcel.")

    country = json.loads(geo)
    clipped, _ = rio_mask(src, [country], crop=True, nodata=nd, filled=True)
    kb = clipped[0]
    kgood = kb != nd

    print("\n" + "-" * 74)
    print("2. STATISTICS: PADDED BOX vs KENYA ONLY")
    print("-" * 74)
    print(f"  {'':16}{'min':>8}{'max':>8}{'mean':>8}{'pixels':>10}")
    print(f"  {'padded box':16}{band[good].min():>8}{band[good].max():>8}"
          f"{band[good].mean():>8.0f}{good.sum():>10,}")
    print(f"  {'Kenya only':16}{kb[kgood].min():>8}{kb[kgood].max():>8}"
          f"{kb[kgood].mean():>8.0f}{kgood.sum():>10,}")
    print("\n  The Kenya-only row is the one to judge. Expect roughly:")
    print("    min  150-250 mm   (Turkana, Marsabit, north east)")
    print("    max  1800-2600 mm (Kakamega, Kericho, Mt Kenya, Mt Elgon)")
    print("    mean 550-750 mm   (most of the country is arid or semi-arid)")

    # How much of Kenya is genuinely dry? A useful independent cross-check:
    # roughly 80 percent of Kenya is classified arid or semi-arid, which
    # corresponds to under about 700 mm a year.
    kv = kb[kgood].astype("float64")
    for thresh in (400, 700, 1200):
        pct = 100.0 * (kv < thresh).sum() / kv.size
        print(f"    {pct:5.1f}% of Kenya under {thresh} mm/year")
    print("  (Kenya is about 80% arid or semi-arid, so the 'under 700 mm' "
          "figure should land near 75-85%. That is an independent check on "
          "the whole distribution, not just its edges.)")

    # ---------------------------------------------------------------------
    # 3. Town by town against published climatology.
    # ---------------------------------------------------------------------
    print("\n" + "-" * 74)
    print("3. TOWN CHECK  (raster value vs published long-term mean)")
    print("-" * 74)
    print(f"  {'town':12}{'raster':>9}{'published':>11}{'diff':>9}{'':>4}")
    rows, big_misses = [], 0
    for name, lon, lat, published in TOWNS:
        val = list(src.sample([(lon, lat)]))[0][0]
        if val == nd:
            print(f"  {name:12}{'nodata':>9}{published:>11}{'-':>9}   ??")
            continue
        diff = (val - published) / published * 100.0
        flag = "ok" if abs(diff) <= 25 else ("HIGH" if diff > 0 else "LOW")
        if flag != "ok":
            big_misses += 1
        rows.append((val, published))
        print(f"  {name:12}{int(val):>9}{published:>11}{diff:>8.0f}%   {flag}")

    if rows:
        r = np.array([x[0] for x in rows], dtype="float64")
        p = np.array([x[1] for x in rows], dtype="float64")
        bias = (r - p).mean()
        corr = np.corrcoef(r, p)[0, 1]
        print(f"\n  average bias : {bias:+.0f} mm  (raster minus published)")
        print(f"  correlation  : {corr:.3f}")
        print(f"  towns off by more than 25%: {big_misses} of {len(rows)}")
        print("\n  What to look for: correlation above ~0.9 means the layer "
              "ranks wet and dry places correctly, which is what a suitability "
              "score actually depends on. A small bias is fine. A LARGE bias "
              "in ONE direction across every town would mean a units problem.")

print("\n" + "=" * 74)
print("Done. Nothing was modified.")
print("=" * 74)
