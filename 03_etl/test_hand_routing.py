r"""
============================================================================
TEST - flow-routing HAND, on synthetic terrain with a KNOWN answer
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS EXISTS
  etl_24's HAND step takes several minutes on 117 million cells. Debugging a
  routing algorithm at that scale, by looking at whether Garissa "seems about
  right", is how runs 55, 56 and 57 each burned an hour to discover a
  structural error. This runs the SAME algorithm on a 300 x 200 synthetic
  landscape where the correct HAND is known by construction, in a few seconds.

THE LANDSCAPE (a cross-section, west to east)

     200 m  |            /\  <- ridge crest at col 100
            |          /    \
     150 m  |        /       \            ____---- col 299
            |      /          \      ___--
     100 m  |  \_/  <- VALLEY A \  _-
            |   col 0            \/  <- VALLEY B, col 110, elevation 0
       0 m  +--------------------------------------------------------

  A test cell at column 95 sits just WEST of the crest, so water leaving it
  runs downhill into VALLEY A. But valley B is far closer in a straight line
  (15 cells away versus 95).

WHAT THE TWO METHODS MUST SAY ABOUT THAT CELL
  Euclidean "nearest mapped drainage" (runs 55-57) measures it against the
  nearest channel in any direction, which is valley B, ACROSS THE RIDGE.
  Flow routing measures it against valley A, which is where its water
  actually goes. This is the Garissa failure in miniature and it is the whole
  reason the method was rebuilt, so it is what the test asserts.

How to run (from 03_etl with venv active):
  python test_hand_routing.py
============================================================================
"""

import os
import sys
import tempfile
from pathlib import Path

# PostgreSQL 16 ships its own PROJ database on PATH, and it is older than the
# one rasterio's wheel expects, so importing rasterio in this shell picks up
# C:\Program Files\PostgreSQL\16\...\proj.db and every EPSG lookup fails with
# "DATABASE.LAYOUT.VERSION.MINOR = 2 whereas a number >= 6 is expected".
# etl_24 already clears these; the test has to do it too, BEFORE rasterio is
# imported.
for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np

for _old, _new in [("in1d", "isin"), ("bool8", "bool_"), ("float_", "float64"),
                   ("int0", "intp"), ("uint0", "uintp"), ("alltrue", "all"),
                   ("sometrue", "any")]:
    if not hasattr(np, _old) and hasattr(np, _new):
        setattr(np, _old, getattr(np, _new))

import rasterio
from pysheds.grid import Grid

H, W = 200, 300
VALLEY_A, RIDGE, VALLEY_B = 0, 100, 110
CHANNEL_MIN_CELLS = 200
MAX_JUMP_PASSES = 32
TEST_COL = 95
TILT_PER_ROW = 0.5

DIRMAP = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1),
          4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}


def build_dem():
    """Cross-section profile, tilted south so water drains off the bottom."""
    c = np.arange(W, dtype="float64")
    prof = np.empty(W, dtype="float64")
    west = c <= RIDGE
    prof[west] = 100.0 + (c[west] / RIDGE) * 100.0          # 100 -> 200
    mid = (c > RIDGE) & (c <= VALLEY_B)
    prof[mid] = 200.0 - ((c[mid] - RIDGE) / (VALLEY_B - RIDGE)) * 200.0
    east = c > VALLEY_B
    prof[east] = ((c[east] - VALLEY_B) / (W - 1 - VALLEY_B)) * 150.0
    dem = np.tile(prof, (H, 1))
    dem -= np.arange(H, dtype="float64").reshape(-1, 1) * TILT_PER_ROW
    return dem.astype("float32")


def hand_by_flow_routing(dem):
    """EXACTLY the algorithm in etl_24 step 4, on a small grid."""
    tmp = Path(tempfile.gettempdir()) / "_hand_test_dem.tif"
    prof = {"driver": "GTiff", "dtype": "float32", "count": 1,
            "crs": "EPSG:4326", "width": W, "height": H, "nodata": -9999.0,
            "transform": rasterio.Affine(1 / 3600, 0, 36.0,
                                         0, -1 / 3600, 0.0)}
    with rasterio.open(tmp, "w", **prof) as d:
        d.write(dem, 1)

    grid = Grid.from_raster(str(tmp))
    dem_r = grid.read_raster(str(tmp))
    inflated = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dem_r)))
    fdir = grid.flowdir(inflated)
    acc = grid.accumulation(fdir)

    cond = np.asarray(inflated, dtype="float32")
    fdir_arr = np.asarray(fdir, dtype="int32")
    acc_arr = np.asarray(acc, dtype="float32")
    del grid, dem_r, inflated, fdir, acc
    tmp.unlink(missing_ok=True)

    valid = np.ones((H, W), dtype=bool)
    channels = acc_arr >= CHANNEL_MIN_CELLS

    N = H * W
    nxt = np.arange(N, dtype="int32").reshape(H, W)
    base = nxt.copy()
    f_in, b_in, n_in = (fdir_arr[1:-1, 1:-1], base[1:-1, 1:-1],
                        nxt[1:-1, 1:-1])
    for code, (dr, dc) in DIRMAP.items():
        m = (f_in == code)
        if m.any():
            n_in[m] = b_in[m] + dr * W + dc
    del f_in, b_in, n_in, base

    nxt = nxt.ravel()
    ch_flat = channels.ravel()
    nxt[ch_flat] = np.flatnonzero(ch_flat)
    step1 = nxt.copy()          # one step downslope, before any jumping

    passes = 0
    for p in range(MAX_JUMP_PASSES):
        nxt2 = nxt[nxt]
        done = np.array_equal(nxt2, nxt)
        nxt = nxt2
        passes = p + 1
        if done:
            break

    cflat = cond.ravel()
    resolved = ch_flat[nxt].reshape(H, W)
    hand = (cflat - cflat[nxt]).reshape(H, W)
    outlet_col = (nxt % W).reshape(H, W)
    hand[channels] = 0.0
    resolved |= channels
    diag = {"fdir": fdir_arr, "step1": step1, "final": nxt}
    return hand, resolved, channels, outlet_col, passes, diag


def hand_by_euclidean(dem, channels):
    """The WITHDRAWN run-57 method, reproduced only so the test can show the
    difference is real rather than asserted."""
    from scipy import ndimage
    _, idx = ndimage.distance_transform_edt(~channels, return_distances=True,
                                            return_indices=True)
    return dem - dem[idx[0], idx[1]]


def main():
    failures = []

    def check(name, ok, detail):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failures.append(name)

    print(__doc__.split("How to run")[0].strip()[:0] or "", end="")
    print("Building synthetic terrain and routing flow ...\n")
    dem = build_dem()
    hand, resolved, channels, outlet_col, passes, diag = \
        hand_by_flow_routing(dem)

    print(f"Channel cells: {int(channels.sum()):,} of {H*W:,} "
          f"({100.0*channels.mean():.2f}%)")
    ch_cols = np.unique(np.nonzero(channels.any(axis=0))[0])
    print(f"Channel columns: {ch_cols.tolist()}")
    print(f"Downslope walk converged after {passes} passes.\n")

    # --- 1. The property the old method could not guarantee -----------------
    check("HAND is non-negative everywhere it is defined",
          bool((hand[resolved] >= -1e-3).all()),
          f"min = {float(hand[resolved].min()):.4f} m")

    # --- 2. Channels are their own outlet ----------------------------------
    check("HAND is exactly 0 on channel cells",
          bool((hand[channels] == 0).all()),
          f"max on channels = {float(hand[channels].max()):.4f} m")

    # --- 3. THE GARISSA TEST: correct valley, not the nearest one ----------
    r = H // 2
    oc = int(outlet_col[r, TEST_COL])
    check("cell west of the ridge drains to VALLEY A, not the nearer VALLEY B",
          oc < RIDGE,
          f"outlet column = {oc} (valley A is <{RIDGE}, valley B is "
          f"{VALLEY_B}); straight-line nearest would have been {VALLEY_B}")

    # --- 4. And the two methods genuinely disagree there -------------------
    try:
        eu = hand_by_euclidean(dem, channels)
        fr_v, eu_v = float(hand[r, TEST_COL]), float(eu[r, TEST_COL])
        check("flow routing and the withdrawn Euclidean method disagree here",
              abs(fr_v - eu_v) > 50.0,
              f"flow routing {fr_v:.1f} m vs Euclidean {eu_v:.1f} m "
              f"(difference {abs(fr_v-eu_v):.1f} m)")
    except ImportError:
        print("  [SKIP] Euclidean comparison: scipy not installed")

    # --- 5. Monotonic: higher up the hillside means higher HAND ------------
    prof = hand[r, 1:RIDGE]
    check("HAND rises monotonically up the valley-A hillside",
          bool((np.diff(prof) >= -1e-3).all()),
          f"smallest step between adjacent cells = "
          f"{float(np.diff(prof).min()):.4f} m")

    # --- 6. Everything stranded is stranded for a LEGITIMATE reason --------
    # WHAT THIS CHECK USED TO SAY, AND WHY IT WAS WRONG BOTH TIMES.
    # First it asserted ">99% of all cells resolve", which ignored that
    # etl_24 deliberately makes border cells terminal. Then it asserted
    # "every INTERIOR cell resolves", which is not true of any bounded
    # landscape with a tilt: water is entitled to leave through the edge, and
    # in this test valley A sits ON column 0, so cells beside it terminate on
    # the border before their accumulation makes them a channel.
    #
    # Both versions tested the synthetic landscape rather than the algorithm.
    # What the algorithm actually promises is narrower and checkable: a cell
    # fails to reach a channel ONLY because it left the grid. Not because the
    # DEM has a pit that conditioning missed, and above all not because the
    # walk fell into a cycle.
    #
    # The cycle case is the one worth the trouble. Pointer jumping CONVERGES
    # on a 2-cycle -- a->b, b->a becomes a->a, b->b after a single pass -- so
    # it would report a clean convergence while quietly measuring HAND
    # against the wrong cell. It is invisible at 117 million cells and cheap
    # to rule out here.
    interior = np.zeros((H, W), dtype=bool)
    interior[1:-1, 1:-1] = True
    stranded = interior & ~resolved
    n_str = int(stranded.sum())
    n_border = int((~interior & ~resolved).sum())

    if n_str:
        # WHY are they stranded? Three candidate causes, and they need
        # different fixes, so the test names which one rather than leaving it
        # to be guessed at:
        #   (a) no flow direction at all (pysheds wrote 0, a pit it could not
        #       resolve) -> the cell never moves,
        #   (b) it moves, but its path leaves the grid through a border cell
        #       that is not a channel -> correct behaviour, expected near
        #       edges,
        #   (c) it lands in a CYCLE, two cells pointing at each other -> a
        #       real defect in the conditioning, and the one that would
        #       silently corrupt HAND at scale.
        print()
        print("  Diagnosing the stranded interior cells:")
        fd = diag["fdir"]
        s1 = diag["step1"].reshape(H, W)
        fin = diag["final"].reshape(H, W)
        flat_self = np.arange(H * W).reshape(H, W)

        no_dir = stranded & ~np.isin(fd, list(DIRMAP.keys()))
        print(f"    (a) no valid D8 code (pysheds pit/edge): "
              f"{int(no_dir.sum())}")

        # Where does each straggler END UP? If the terminus is a border cell,
        # it drained off the grid, which is the documented convention.
        term = fin[stranded]
        term_r, term_c = term // W, term % W
        on_border = int(((term_r == 0) | (term_r == H - 1) |
                         (term_c == 0) | (term_c == W - 1)).sum())
        print(f"    (b) path terminates on a border cell (drains off-grid): "
              f"{on_border}")

        # A cycle shows up as a cell that still moves after convergence.
        moved = stranded & (fin != flat_self) & (s1 != flat_self)
        cyc = int((moved & (fin[np.clip(fin // W, 0, H - 1),
                                np.clip(fin % W, 0, W - 1)] != fin)).sum())
        print(f"    (c) terminates in a cycle (would be a real defect): "
              f"{cyc}")

        cols = np.bincount(np.nonzero(stranded)[1], minlength=W)
        top = np.argsort(cols)[::-1][:6]
        print("    busiest columns: "
              + ", ".join(f"col {c} x{cols[c]}" for c in top if cols[c]))
        print(f"    (channel columns run 0-80 and 110-280; 281-299 have "
              f"none)")
        print()
    else:
        no_dir = np.zeros((H, W), dtype=bool)
        on_border, cyc = 0, 0

    check("no cell is stranded by a pit that conditioning missed",
          int(no_dir.sum()) == 0,
          f"{int(no_dir.sum())} cell(s) with no valid D8 code")
    check("no cell is stranded in a routing cycle",
          cyc == 0,
          f"{cyc} cell(s) terminating in a cycle")
    check("every stranded cell is stranded because it left the grid",
          on_border == n_str,
          f"{on_border} of {n_str} interior stragglers drain off-grid; "
          f"{n_border} border cells terminal by design "
          f"({100.0*resolved.mean():.2f}% resolved overall)")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        sys.exit(1)
    print("All checks passed. The routing step is sound; run "
          "etl_24_hazards_flood.py.")


if __name__ == "__main__":
    main()
