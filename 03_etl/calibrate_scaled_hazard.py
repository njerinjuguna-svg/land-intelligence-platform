r"""
============================================================================
CALIBRATION - catchment-scaled flood hazard (the fix for "no threshold works")
Land Intelligence Platform - Geocode Spatial Solutions Ltd

THE PROBLEM THIS EXISTS TO SOLVE
  calibrate_channel_threshold.py established, on the worst-case-within-1-km
  reading that etl_24 actually uses, that:

    5 km2 channels : every landmark correct, but 21% of Kenya at HAND <= 2 m
    30 km2 channels: 10.6% of Kenya at HAND <= 2 m, but Garissa's worst case
                     within 1 km is 10.0 m, i.e. never flagged above Moderate

  There is no threshold in between that fixes both, and the reason is not the
  threshold. It is that HAND never asks HOW BIG the channel is.

  At 5 km2 the floodplains come out right because a real floodplain does sit
  at HAND 0 beside a real river. The surplus 21% is arid plain sitting 0-2 m
  above an EPHEMERAL GULLY that cannot generate a flood. HAND treats the Tana
  at Garissa and a 5 km2 sand gully in Turkana as the same object. They are
  not the same object.

THE PHYSICS, STATED SO A HYDROLOGIST CAN ARGUE WITH IT
  Flood depth grows with discharge, and discharge grows with contributing
  area. Empirically depth ~ A^b with b around 0.25-0.35 for a given return
  period. So define a REFERENCE FLOOD DEPTH for the channel a cell drains to:

      d(A) = D0 * (A / A0) ** B          A = outlet's catchment area, km2

  and judge the cell on HAND MEASURED IN UNITS OF THAT DEPTH:

      hr = HAND / d(A)          hazard falls out of hr, not out of HAND

  With D0 = 2 m at A0 = 1000 km2 and B = 0.3:
      A =      5 km2  ->  d = 0.40 m      (a gully; 1 m above it is safe)
      A =    500 km2  ->  d = 1.62 m
      A = 50,000 km2  ->  d = 6.48 m      (the Tana; 5 m above it is not)

  So the SAME 2 m of elevation is dangerous beside the Tana and unremarkable
  beside a gully, which is the distinction the layer has been missing since
  run 55. The channel threshold stays LOW (5 km2) so that real floodplains
  keep their channels; size is handled by scaling rather than by exclusion.

WHAT THIS SCRIPT DOES
  Computes hr once from the cached conditioning, then sweeps D0. Because the
  class boundaries are multiples of D0, sweeping it is just a comparison on
  hr, so the whole sweep costs one routing pass. It writes NOTHING except the
  country-mask cache described below.

THE COUNTRY CLIP, ADDED AFTER RUN 77 -- READ THIS BEFORE TRUSTING A SWEEP
  Every share this script printed used n_valid = "cells where the DEM has
  data" as the denominator. GLO-30 gives the ocean an elevation of 0 rather
  than nodata, so that denominator included the Indian Ocean, Ugandan and
  Tanzanian Lake Victoria, and neighbouring land: run 75 established it was
  42% larger than Kenya.

  AMIN_TOP_KM2 = 10 in etl_24 was chosen against that denominator. It still
  passes, but it was picked for the wrong reasons, and re-running this
  calibrator WITHOUT the clip would have reproduced the exact error it is
  meant to correct -- confirming a value against the same bad denominator
  that chose it. Checklist item C1.

  So every share below is now a share of Kenya. Expect the numbers to MOVE
  relative to any pre-clip sweep you have on file; that is the point, not a
  regression.

  The mask is built once from admin.country and cached to disk beside the
  conditioning cache, so only the first run needs the database. Same reason
  the conditioning is cached: a calibration you cannot afford to re-run is
  two guesses and a rationalisation.

How to run (from 03_etl with venv active, after etl_24 has built the cache):
  python calibrate_scaled_hazard.py
  python calibrate_scaled_hazard.py --channel 5 --exp 0.3 --d0 1 1.5 2 3
  python calibrate_scaled_hazard.py --amin 3 5 10 15 30
============================================================================
"""

import os
import sys
import gc
import time
from pathlib import Path

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np
import rasterio

BASE = Path(__file__).resolve().parent
RAW_DIR = BASE / "data" / "raw" / "hazards"
DEM_WORK = RAW_DIR / "_dem_work_93m.tif"
COND_CACHE = RAW_DIR / "_cond_93m.tif"
FDIR_CACHE = RAW_DIR / "_fdir_93m.tif"
ACC_CACHE = RAW_DIR / "_acc_93m.tif"
MASK_CACHE = RAW_DIR / "_kenya_mask_93m.tif"

KENYA_KM2 = 580_367.0          # official area, the E1 sanity check


def load_country_mask(shape, transform, crs):
    """Kenya as a boolean array on the working grid.

    Cached to disk: only the first run touches PostgreSQL, so the calibrator
    stays runnable on a laptop with the database down, which is when you most
    want to sweep a threshold.
    """
    H, W = shape
    if MASK_CACHE.exists():
        with rasterio.open(MASK_CACHE) as s:
            if (s.width, s.height) == (W, H):
                print(f"Country mask from cache ({MASK_CACHE.name})")
                return s.read(1).astype(bool)
        # A cache whose grid does not match is not a cache, it is a trap.
        # Session 5's stale-resume near miss: a leftover file with plausible
        # dimensions silently contaminated a whole raster.
        print(f"   cached mask has the wrong grid, rebuilding")

    try:
        from dotenv import load_dotenv
        from sqlalchemy import create_engine
        import geopandas as gpd
        from rasterio.features import rasterize
    except ImportError as e:
        sys.exit(f"ERROR: building the country mask needs geopandas, "
                 f"sqlalchemy and python-dotenv ({e}).")

    load_dotenv(BASE / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit("ERROR: set DB_PASSWORD in .env. The country mask is read "
                 "from admin.country once, then cached.")
    url = (f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
           f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
           f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")
    engine = create_engine(url)
    print("Building the country mask from admin.country ...", flush=True)
    with engine.connect() as conn:
        country = gpd.read_postgis("SELECT geom FROM admin.country", conn,
                                   geom_col="geom")
    if country.empty:
        sys.exit("admin.country is empty; cannot clip.")
    mask = rasterize(((g, 1) for g in country.geometry if g is not None),
                     out_shape=(H, W), transform=transform, fill=0,
                     dtype="uint8", all_touched=True)
    with rasterio.open(MASK_CACHE, "w", driver="GTiff", dtype="uint8",
                       count=1, width=W, height=H, crs=crs,
                       transform=transform, nodata=0, tiled=True,
                       blockxsize=512, blockysize=512,
                       compress="DEFLATE") as d:
        d.write(mask, 1)
    print(f"   cached to {MASK_CACHE.name}")
    return mask.astype(bool)

WORK_DEG = 3.0 / 3600.0
FILL_TOL_M = 3.0
MAX_JUMP_PASSES = 32
CHANNEL_KM2 = 5.0
A0_KM2 = 1000.0
EXP_B = 0.3
D0_SWEEP = [1.5]
# Minimum catchment, km2, that the outlet must drain for a cell to be given
# the TOP class. Lower classes scale down from it (see the sweep).
#
# RE-CENTRED FOR THE CLIPPED RE-CALIBRATION (checklist C1). The old sweep was
# [0, 30, 100, 300, 1000], which does not contain 10 -- the value etl_24
# actually ships -- so it could confirm a choice it never tested. The open
# question is whether 10 can come DOWN now that the denominator is 42%
# smaller, because this layer's stated rule prefers warning more, so the
# candidates below Kenya's shipped value are the ones that matter.
AMIN_SWEEP = [0.0, 3.0, 5.0, 10.0, 15.0, 30.0]
# Class boundaries as multiples of the reference depth d(A).
MULT = {5: 1.0, 4: 2.0, 3: 4.0, 2: 10.0}
CLASS_NAMES = {1: "Very low", 2: "Low", 3: "Moderate", 4: "High",
               5: "Very high"}

DIRMAP = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1),
          4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}

# Landmarks, and whether a wrong answer at each one actually costs anything.
#
# SCOPE DECISION (Njeri, session 7): this is a product for land people BUY
# AND SELL. A layer that is soft over the Chalbi is not a defect worth
# spending a calibration on; a layer that is soft over Garissa or the Nairobi
# peri-urban belt is a refund. Landmarks now carry that weighting explicitly,
# because for two sessions the Chalbi row read as a FAILURE and pulled
# calibration effort toward terrain with almost no transactions on it.
#
# `binding=False` means: report it, never let it choose a constant.
SPOTS = [
    ("Budalangi, Nzoia",    34.150,  0.150, "High/Very high", True),
    ("Kano plains",         34.950, -0.200, "High/Very high", True),
    ("Tana delta",          40.300, -2.500, "High/Very high", True),
    ("Garissa on the Tana", 39.650, -0.450, "High/Very high", True),
    ("Nairobi Karen",       36.700, -1.330, "Low/Very low",   True),
    ("Aberdares slopes",    36.700, -0.450, "Very low",       True),
    # NOT BINDING. The Chalbi is a closed basin: fill_depressions raises it to
    # spill level, so it carries no HAND at all and this script reads
    # 'undefined' at every floor. etl_24 falls back to JRC + TWI there, which
    # this script does not implement, so the row cannot test what the product
    # actually ships even in principle. It is kept as context and must never
    # decide a threshold.
    ("Chalbi desert",       37.300,  3.150, "untestable here", False),
]


def parse_args():
    a = sys.argv[1:]
    ch, ex, d0s, am = CHANNEL_KM2, EXP_B, list(D0_SWEEP), list(AMIN_SWEEP)
    if "--channel" in a:
        i = a.index("--channel"); ch = float(a[i + 1]); del a[i:i + 2]
    if "--exp" in a:
        i = a.index("--exp"); ex = float(a[i + 1]); del a[i:i + 2]
    if "--d0" in a:
        i = a.index("--d0"); d0s = [float(a[i + 1])]; del a[i:i + 2]
    if "--amin" in a:
        i = a.index("--amin")
        am = [float(v) for v in a[i + 1:]]
        del a[i:]
    return ch, ex, d0s, am


def main():
    channel_km2, exp_b, d0_sweep, amin_sweep = parse_args()
    missing = [p.name for p in (DEM_WORK, COND_CACHE, FDIR_CACHE, ACC_CACHE)
               if not p.exists()]
    if missing:
        sys.exit("Conditioning cache missing: " + ", ".join(missing) +
                 "\nRun etl_24_hazards_flood.py once to build it.")

    t0 = time.time()
    print("Loading the conditioning cache ...", flush=True)
    with rasterio.open(DEM_WORK) as s:
        orig = s.read(1).astype("float32")
        nd, H, W, transform = s.nodata, s.height, s.width, s.transform
        crs = s.crs
    with rasterio.open(COND_CACHE) as s:
        cond = s.read(1).astype("float32")
    with rasterio.open(FDIR_CACHE) as s:
        fdir = s.read(1).astype("int16")
    with rasterio.open(ACC_CACHE) as s:
        acc = s.read(1).astype("float32")

    valid = np.isfinite(orig) & (orig != (nd if nd is not None else -9999.0))
    np.subtract(cond, orig, out=orig)
    filled = (orig > FILL_TOL_M) & valid
    del orig
    gc.collect()

    # ---- THE DENOMINATOR -------------------------------------------------
    # `valid` means "the DEM has a number here", which over an ocean that
    # GLO-30 encodes as elevation 0 is true and useless. Kenya is the
    # denominator; everything else is context the routing needs to see.
    in_kenya = load_country_mask((H, W), transform, crs)
    valid_ken = valid & in_kenya
    n_valid = int(valid_ken.sum())
    n_box = int(valid.sum())

    cell_km2 = (WORK_DEG * 111320) * (WORK_DEG * 110574) / 1e6
    mask_km2 = float(in_kenya.sum()) * cell_km2
    print(f"Grid {W:,} x {H:,}")
    print(f"   valid cells in the padded box : {n_box/1e6:>6.0f}M")
    print(f"   valid cells in KENYA          : {n_valid/1e6:>6.0f}M "
          f"<- the honest denominator "
          f"({100.0*n_valid/max(1, n_box):.0f}% of the box)")
    print(f"   country mask {mask_km2:,.0f} km2 vs official "
          f"{KENYA_KM2:,.0f} ({100.0*mask_km2/KENYA_KM2:.1f}%)")
    if not (0.95 <= mask_km2 / KENYA_KM2 <= 1.10):
        sys.exit(f"Country mask is {mask_km2:,.0f} km2, too far from "
                 f"{KENYA_KM2:,.0f}. Refusing to calibrate against it.")
    print(f"Channel threshold {channel_km2:g} km2, "
          f"fill tolerance {FILL_TOL_M:g} m, exponent B = {exp_b:g}, "
          f"A0 = {A0_KM2:g} km2")

    # ---- route once ------------------------------------------------------
    print("Routing ...", flush=True)
    N = H * W
    down = np.arange(N, dtype="int32").reshape(H, W)
    base = down.copy()
    f_in, b_in, d_in = fdir[1:-1, 1:-1], base[1:-1, 1:-1], down[1:-1, 1:-1]
    for code, (dr, dc) in DIRMAP.items():
        m = (f_in == code)
        if m.any():
            d_in[m] = b_in[m] + dr * W + dc
    del f_in, b_in, d_in, base, fdir
    gc.collect()
    down = down.ravel()
    nv = np.flatnonzero(~valid.ravel())
    down[nv] = nv
    del nv

    channels = (acc >= channel_km2 / cell_km2) & valid & ~filled
    nxt = down
    ch_flat = channels.ravel()
    idx = np.flatnonzero(ch_flat)
    nxt[idx] = idx
    del idx
    for _ in range(MAX_JUMP_PASSES):
        nxt2 = nxt[nxt]
        done = np.array_equal(nxt2, nxt)
        nxt = nxt2
        if done:
            break

    cflat = cond.ravel()
    resolved = ch_flat[nxt].reshape(H, W)
    hand = (cflat - cflat[nxt]).reshape(H, W)
    hand[channels] = 0.0
    ok = (resolved | channels) & valid & ~filled
    np.clip(hand, 0, 32000, out=hand)
    del resolved, cond, cflat
    gc.collect()

    # Catchment area, in km2, of the channel each cell drains to.
    oacc = acc.ravel()[nxt].reshape(H, W)
    channels_mask = channels
    del acc, nxt, down, ch_flat
    gc.collect()
    oacc *= np.float32(cell_km2)
    # Every statistic below reads Kenya only. in_kenya is freed straight
    # after: three full-grid boolean arrays is ~350 MB at 117M cells, and
    # this script already runs alongside the routing arrays.
    ok_ken = ok & in_kenya
    del in_kenya
    gc.collect()
    print(f"   outlet catchment area: median "
          f"{float(np.median(oacc[ok_ken])):,.0f} km2, "
          f"95th pct {float(np.percentile(oacc[ok_ken], 95)):,.0f} km2")

    # WHERE IS THE SPIKE AT HAND = 0 COMING FROM?
    # The first sweep found ~12% of Kenya at hr = 0, which no amount of
    # scaling can move, because HAND/d(A) is zero whenever HAND is zero. Two
    # candidate causes, and they need different answers:
    #   - channel cells, which are set to 0 deliberately and are supposed to
    #     be there,
    #   - FLAT GROUND THAT COLLAPSED NUMERICALLY. resolve_flats imposes a
    #     tiny gradient across flats, of order 1e-6 m. The cache stores the
    #     conditioned DEM as float32, where one ulp at 500 m elevation is
    #     about 6e-5 m. Those increments cannot survive the cast, so every
    #     cell on a large flat ends up at EXACTLY the channel's elevation and
    #     reads HAND = 0. That would be my bug, not the terrain's.
    zero = ok_ken & (hand <= 0.0)
    n_zero = int(zero.sum())
    n_zero_chan = int((zero & (hand == 0.0) & channels_mask).sum())
    print(f"\n   cells at HAND = 0: {100.0*n_zero/n_valid:.2f}% of Kenya")
    print(f"     of which channel cells (expected): "
          f"{100.0*n_zero_chan/max(1, n_zero):.1f}%")
    print(f"     of which flat ground off-channel  : "
          f"{100.0*(n_zero-n_zero_chan)/max(1, n_zero):.1f}%")
    tiny = ok_ken & (hand > 0.0) & (hand < 0.01)
    print(f"   cells at 0 < HAND < 1 cm (a collapsed flat would land here "
          f"if the cast were lossless): {100.0*float(tiny.sum())/n_valid:.2f}%")
    del zero, tiny
    gc.collect()

    # ---- hr = HAND / (A/A0)^B, so sweeping D0 is a pure comparison -------
    oacc_km2 = oacc.copy()                   # keep the raw catchment area
    np.divide(oacc, np.float32(A0_KM2), out=oacc)
    np.power(oacc, np.float32(exp_b), out=oacc)
    np.maximum(oacc, np.float32(1e-6), out=oacc)
    hr = hand / oacc
    del oacc, hand
    gc.collect()

    spot_rc = []
    inv = ~transform
    for name, lon, lat, expect, binding in SPOTS:
        c, r = inv * (lon, lat)
        spot_rc.append((name, int(r), int(c), expect, binding))

    hv = hr[ok_ken]
    ps = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    print("\n   hr = HAND / d(A), distribution over Kenyan cells where it is "
          "defined")
    print("   percentile  " + "".join(f"{p:>8}%" for p in ps))
    print("   hr          " + "".join(f"{q:>9.2f}"
                                      for q in np.percentile(hv, ps)))

    # A SIZE FLOOR, BECAUSE DIVISION CANNOT DISCRIMINATE AT ZERO.
    # hr = HAND/d(A) was supposed to separate "level with the Tana" from
    # "level with a gully", and it does everywhere except at HAND = 0, where
    # it is zero for both. That is where most of Kenya's mass sits, so the
    # scaling never got to do its job on the cells that mattered.
    #
    # So severity now also requires the channel to be big enough to produce
    # the flood being claimed. Being level with a 5 km2 sand gully is a
    # drainage fact, not a flood hazard: there is no upstream catchment to
    # deliver the water. The floors below are per class, and they are the
    # honest statement of "how big a river does this warning assume".
    # A FLOOR AT OR BELOW THE CHANNEL THRESHOLD CANNOT BIND.
    # Channels only exist where accumulation reaches CHANNEL_KM2, so every
    # cell's outlet catchment is >= CHANNEL_KM2 by construction. Sweeping 0,
    # 3 and 5 against a 5 km2 channel threshold returns three identical rows
    # and looks like a plateau in the data. It is an identity. Session 7 read
    # that plateau as evidence before spotting it; the script now says so.
    dead = [a for a in amin_sweep if a <= channel_km2]
    if dead:
        print(f"\n   NOTE: floors {', '.join(f'{a:g}' for a in dead)} km2 are "
              f"<= the channel threshold ({channel_km2:g} km2) and CANNOT "
              f"BIND.")
        print(f"   Every outlet catchment is at least {channel_km2:g} km2 by "
              f"construction, so these rows are identical to 0 by identity, "
              f"not by measurement. To lower the effective floor you must "
              f"lower CHANNEL_KM2 as well - which is the knob run 57 already "
              f"proved irreconcilable.")

    print("\n" + "=" * 78)
    print(f"Sweeping the catchment floor for the top class, at D0 = "
          f"{d0_sweep[0]:g} m")
    print(f"{'Very high needs A >=':>22}"
          + "".join(f"{CLASS_NAMES[c]:>11}" for c in (5, 4, 3, 2, 1)))
    d0 = d0_sweep[0]
    rows = []
    for amin in amin_sweep:
        # High needs a third of that catchment, Moderate a tenth; Low and
        # Very low carry no size requirement, because they make no claim.
        floors = {5: amin, 4: amin / 3.0, 3: amin / 10.0, 2: 0.0}
        shares, cls = {}, np.ones((H, W), dtype="uint8")
        # highest matching class wins, so assign from least to most severe
        for c in (2, 3, 4, 5):
            cls[ok & (hr <= MULT[c] * d0) & (oacc_km2 >= floors[c])] = c
        cls[~ok] = 0
        for c in (1, 2, 3, 4, 5):
            shares[c] = 100.0 * float(((cls == c) & valid_ken).sum()) / n_valid
        line = f"{amin:>19.0f}km2" + "".join(f"{shares[c]:>10.2f}%"
                                             for c in (5, 4, 3, 2, 1))
        print(line)
        spots = []
        for nm, r, c, ex, _bind in spot_rc:
            r0, c0 = max(0, r - 5), max(0, c - 5)
            blk = cls[r0:r + 6, c0:c + 6]
            g = blk[blk != 0]
            spots.append(int(g.max()) if g.size else 0)
        rows.append({"amin": amin, "shares": shares, "spots": spots})
        del cls
        gc.collect()

    print("\nWORST CLASS WITHIN ~1 km OF EACH LANDMARK")
    print(f"{'landmark':24}{'must be':16}"
          + "".join(f"{r['amin']:>10.0f}km2" for r in rows))
    for i, (nm, _, _, ex, binding) in enumerate(spot_rc):
        mark = "" if binding else "  (not binding)"
        line = f"{nm:24}{ex:18}"
        for r in rows:
            v = r["spots"][i]
            line += f"{(CLASS_NAMES[v] if v else 'undefined'):>12}"
        print(line + mark)
    print("\n  'not binding' = reported for context, must NOT decide a")
    print("  threshold. Land nobody buys or sells does not get to set the")
    print("  constants for land they do.")

    print("\nHOW TO READ THIS")
    print("  Every share above is a share of KENYA, not of the padded box.")
    print("  They will not match any sweep run before the clip was added;")
    print("  the old denominator was 42% too large. If you are comparing")
    print("  against notes from session 6, compare shapes, not numbers.")
    print("  Two things at once, and the second is the one that has been")
    print("  missed four times now:")
    print("  1. The top class under ~10% of Kenya, with the four flood-prone")
    print("     landmarks still High or Very high.")
    print("  2. A CREDIBLE SHAPE. Hazard classes should form a pyramid:")
    print("     Very high smaller than High, High smaller than Moderate. The")
    print("     A >= 0 row is the previous behaviour and is top-heavy")
    print("     (Very high five times High), which is a warning that the top")
    print("     class is absorbing cells that belong further down, not that")
    print("     Kenya is unusually dangerous.")
    print("  Pick the SMALLEST floor that achieves both. A large floor buys a")
    print("  tidy number by silently refusing to warn about medium rivers,")
    print("  which is the same under-warning that withdrew run 57 wearing a")
    print("  different hat.")
    print(f"\nFinished in {time.time()-t0:.0f}s. Nothing was written.")


if __name__ == "__main__":
    main()
