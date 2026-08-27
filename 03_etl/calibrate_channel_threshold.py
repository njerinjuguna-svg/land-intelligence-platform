r"""
============================================================================
CALIBRATION - choosing CHANNEL_MIN_KM2 for etl_24 flood hazard
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS IS A SEPARATE SCRIPT
  Runs 55, 56, 57, 59 and 61 all ended the same way: a number came out wrong,
  a knob got turned, and the next run was judged on whether the answer looked
  better. That is not calibration, it is search with a bias toward whatever
  finishes first, and it produced a layer that called Garissa "Low".

  This sweeps the channel threshold across a range IN ONE PASS and prints the
  whole curve, so the number gets picked by looking at how the layer behaves
  across the range rather than at one run in isolation. It writes NOTHING: no
  raster, no catalogue entry, no etl_runs row. It cannot ship anything, which
  is the point.

WHAT IT NEEDS
  The conditioning cache that etl_24 leaves behind:
    data/raw/hazards/_dem_work_93m.tif
    data/raw/hazards/_cond_93m.tif
    data/raw/hazards/_fdir_93m.tif
    data/raw/hazards/_acc_93m.tif
  Run etl_24_hazards_flood.py at least once to create them (~27 min). After
  that this script is a few minutes per threshold.

WHAT THE NUMBERS MEAN, AND WHICH ONE DECIDES IT
  For each candidate threshold you get:
    network %       - share of Kenya that is channel. A real 1:50,000 drainage
                      network is well under 2%. Run 61 sat at 3.92%.
    <=2m, <=5m      - share of Kenya each hazard threshold would capture. The
                      top class needs to land under about 10%, and lower is
                      more credible than higher.
    median HAND     - rises as the network thins, because your outlet moves
                      further downstream and therefore lower.
    LANDMARKS       - HAND in metres at the seven places we already know the
                      answer for. THIS IS THE COLUMN THAT DECIDES IT. A
                      threshold that gets the national share into a plausible
                      band while putting Garissa at 40 m is not a better
                      threshold, it is a worse one that happens to look tidy.

  Garissa and Budalangi must come out LOW (they flood). Karen and the
  Aberdares must come out HIGH (they do not). Chalbi should be excluded as
  filled ground, or read high; it is a desert.

How to run (from 03_etl with venv active):
  python calibrate_channel_threshold.py
  python calibrate_channel_threshold.py 10 25 50 100 200
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

WORK_DEG = 3.0 / 3600.0
FILL_TOL_M = 0.5
MAX_JUMP_PASSES = 32
DEFAULT_SWEEP = [5.0, 15.0, 30.0, 60.0, 120.0]

DIRMAP = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1),
          4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}

# name, lon, lat, what the layer MUST say
SPOTS = [
    ("Budalangi, Nzoia",    34.150,  0.150, "low  (floods)"),
    ("Kano plains",         34.950, -0.200, "low  (floods)"),
    ("Tana delta",          40.300, -2.500, "low  (floods)"),
    ("Garissa on the Tana", 39.650, -0.450, "low  (floods)"),
    ("Nairobi Karen",       36.700, -1.330, "high (upland)"),
    ("Chalbi desert",       37.300,  3.150, "high (desert)"),
    ("Aberdares slopes",    36.700, -0.450, "high (steep)"),
]


def main():
    global FILL_TOL_M
    args = sys.argv[1:]
    if "--fill-tol" in args:
        i = args.index("--fill-tol")
        try:
            FILL_TOL_M = float(args[i + 1])
        except (IndexError, ValueError):
            sys.exit("--fill-tol needs a number, e.g. --fill-tol 3")
        del args[i:i + 2]
    try:
        sweep = [float(a) for a in args] if args else list(DEFAULT_SWEEP)
    except ValueError:
        sys.exit("Usage: python calibrate_channel_threshold.py "
                 "[--fill-tol M] [km2 ...]")

    missing = [p.name for p in (DEM_WORK, COND_CACHE, FDIR_CACHE, ACC_CACHE)
               if not p.exists()]
    if missing:
        sys.exit("Conditioning cache missing: " + ", ".join(missing) +
                 "\nRun etl_24_hazards_flood.py once to build it.")

    t0 = time.time()
    print("Loading the conditioning cache ...", flush=True)
    with rasterio.open(DEM_WORK) as s:
        orig = s.read(1).astype("float32")
        nd = s.nodata
        H, W = s.height, s.width
        transform = s.transform
    with rasterio.open(COND_CACHE) as s:
        cond = s.read(1).astype("float32")
    with rasterio.open(FDIR_CACHE) as s:
        fdir = s.read(1).astype("int16")
    with rasterio.open(ACC_CACHE) as s:
        acc = s.read(1).astype("float32")

    valid = np.isfinite(orig) & (orig != (nd if nd is not None else -9999.0))
    n_valid = int(valid.sum())
    np.subtract(cond, orig, out=orig)          # orig -> fill depth
    fill_depth = orig
    del orig

    cell_km2 = (WORK_DEG * 111320) * (WORK_DEG * 110574) / 1e6
    print(f"Grid {W:,} x {H:,}, {n_valid/1e6:.0f}M valid cells, "
          f"{cell_km2*1e6:,.0f} m2 per cell")

    # HOW MUCH FILL IS BASIN, AND HOW MUCH IS JUST A SURFACE MODEL?
    # GLO-30 is a DSM: buildings and tree canopy put metre-scale pits all over
    # it, and fill_depressions fills those exactly as it fills a salt pan. A
    # tolerance of 0.5 m therefore does not separate "closed basin" from
    # "suburb with trees in it" -- which is why Nairobi Karen came back
    # undefined. The tolerance has to be read off this table, not assumed.
    print("\nFILL DEPTH: how far conditioning had to raise the ground")
    print(f"{'tolerance m':>13}{'% of Kenya excluded':>22}")
    for t in (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 25.0):
        print(f"{t:>13.2f}{100.0*float((fill_depth > t).sum())/n_valid:>21.2f}%")
    fd_pos = fill_depth[(fill_depth > 0.01) & valid]
    if fd_pos.size:
        ps = [50, 75, 90, 95, 99, 99.9]
        qs = np.percentile(fd_pos, ps)
        print("   of cells with ANY fill, depth percentiles:")
        print("   " + "".join(f"{p:>9}%" for p in ps))
        print("   " + "".join(f"{q:>10.1f}" for q in qs))
    del fd_pos
    gc.collect()

    filled = (fill_depth > FILL_TOL_M) & valid
    print(f"\nUsing FILL_TOL_M = {FILL_TOL_M} m -> "
          f"{100.0*filled.sum()/n_valid:.1f}% of Kenya treated as invented "
          f"ground")

    # ONE-STEP DOWNSTREAM INDEX, built once. This does not depend on the
    # threshold, so rebuilding it per candidate would triple the sweep for no
    # reason.
    print("Building the one-step downstream index ...", flush=True)
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
    not_valid_flat = np.flatnonzero(~valid.ravel())
    down[not_valid_flat] = not_valid_flat
    del not_valid_flat
    gc.collect()

    spot_rc = []
    inv = ~transform
    for name, lon, lat, expect in SPOTS:
        c, r = inv * (lon, lat)
        spot_rc.append((name, int(r), int(c), expect))

    rows = []
    for thr_km2 in sweep:
        t1 = time.time()
        thr_cells = thr_km2 / cell_km2
        channels = (acc >= thr_cells) & valid & ~filled
        n_chan = int(channels.sum())
        if n_chan == 0:
            print(f"\n{thr_km2:g} km2: no channels at all, skipping")
            continue

        nxt = down.copy()
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
        del nxt
        gc.collect()
        hand[channels] = 0.0
        ok = (resolved | channels) & valid & ~filled
        np.clip(hand, 0, 32000, out=hand)
        del resolved
        gc.collect()

        hv = hand[ok]
        le2 = 100.0 * float((hv <= 2.0).sum()) / n_valid
        le5 = 100.0 * float((hv <= 5.0).sum()) / n_valid
        med = float(np.median(hv)) if hv.size else float("nan")
        # LANDMARKS ARE JUDGED ON A NEIGHBOURHOOD, NOT ONE CELL.
        # etl_24's own spot check reads the worst class within ~1 km, because
        # a single 93 m DSM cell carries canopy, buildings and a coordinate
        # that may be a few hundred metres off. Reporting one cell here meant
        # this script was holding the layer to a STRICTER test than the layer
        # actually has to pass, which is a good way to tune a threshold to fix
        # a landmark that was never broken.
        HALF = 5                                  # 11 x 11 cells ~ 1 km
        spots = []
        for nm, r, c, ex in spot_rc:
            r0, c0 = max(0, r - HALF), max(0, c - HALF)
            blk = hand[r0:r + HALF + 1, c0:c + HALF + 1]
            bok = ok[r0:r + HALF + 1, c0:c + HALF + 1]
            bfill = filled[r0:r + HALF + 1, c0:c + HALF + 1]
            point = float(hand[r, c]) if ok[r, c] else None
            worst = float(blk[bok].min()) if bok.any() else None
            if worst is None:
                why = "all fill" if bfill.all() else "off-grid"
            else:
                why = ""
            spots.append((nm, point, worst, why, ex))
        rows.append({
            "thr": thr_km2,
            "net": 100.0 * n_chan / n_valid,
            "def": 100.0 * float(ok.sum()) / n_valid,
            "le2": le2, "le5": le5, "med": med, "spots": spots,
        })
        print(f"  {thr_km2:>6.0f} km2 done in {time.time()-t1:.0f}s "
              f"(network {100.0*n_chan/n_valid:.2f}%, "
              f"<=2 m {le2:.2f}%)", flush=True)
        del hv, hand, ok, channels, ch_flat
        gc.collect()

    # ---------------------------------------------------------------- table
    print("\n" + "=" * 78)
    print("NATIONAL SHARES")
    print(f"{'km2':>7}{'network%':>10}{'defined%':>10}"
          f"{'<=2m%':>9}{'<=5m%':>9}{'median m':>11}")
    for x in rows:
        print(f"{x['thr']:>7.0f}{x['net']:>10.2f}{x['def']:>10.1f}"
              f"{x['le2']:>9.2f}{x['le5']:>9.2f}{x['med']:>11.1f}")

    print("\nLOWEST HAND WITHIN ~1 km OF EACH LANDMARK (metres)")
    print("This is what etl_24's spot check actually reads: the WORST case")
    print("nearby, not the one cell the coordinate happens to land on.")
    print("(dash = no cell within 1 km has a HAND value; reason in brackets)")
    hdr = f"{'landmark':24}{'must be':15}" + "".join(
        f"{x['thr']:>9.0f}" for x in rows)
    print(hdr)
    for i, (nm, _, _, ex) in enumerate(spot_rc):
        line = f"{nm:24}{ex:15}"
        for x in rows:
            _, _, worst, why, _ = x["spots"][i]
            line += f"{'-':>9}" if worst is None else f"{worst:>9.1f}"
        why0 = x["spots"][i][3]
        print(line + (f"   [{why0}]" if why0 else ""))

    print("\nSINGLE CELL AT THE COORDINATE (for comparison only)")
    print("Where this differs a lot from the row above, the coordinate is on")
    print("a terrace or a rooftop, not the floodplain, and the row above is")
    print("the honest number.")
    print(hdr)
    for i, (nm, _, _, ex) in enumerate(spot_rc):
        line = f"{nm:24}{ex:15}"
        for x in rows:
            v = x["spots"][i][1]
            line += f"{'-':>9}" if v is None else f"{v:>9.1f}"
        print(line)

    print("\nHOW TO READ THIS")
    print("  Pick the SMALLEST threshold that gets the top class under about")
    print("  10% while keeping Garissa, Budalangi, Kano and the Tana delta")
    print("  low in the NEIGHBOURHOOD table. Smaller keeps more real")
    print("  channels; the landmarks are the constraint.")
    print("  If a landmark reads '-', fix that before reading anything else:")
    print("  an upland suburb like Karen coming back as fill means the fill")
    print("  tolerance is catching DSM canopy, not closed basins.")
    print("  If no threshold satisfies both constraints, the problem is not")
    print("  the threshold and this script must not be used to hide that.")
    print(f"\nSweep finished in {time.time()-t0:.0f}s. Nothing was written.")


if __name__ == "__main__":
    main()
