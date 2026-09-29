r"""
============================================================================
RECOVER PLOTS FROM A CAD DRAWING EXPORTED TO KML
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHAT WENT WRONG, STATED PLAINLY

  OAK GROVE.kmz is not a parcel file. It is an AutoCAD drawing that somebody
  exported to Google Earth. It holds 1,086 placemarks, every one of them a
  LineString and 1,025 of them a single two-point SEGMENT, spread over
  fifteen drafting layers.

  There are no plots in that file. There are lines. The plots are the shapes
  the lines enclose.

  `03_load_client_parcels.py` needs three points to build a ring, so it kept
  the thirteen stragglers - a 191-point polyline, two arcs, some verges - and
  discarded the rest without a word. Those thirteen were loaded, enriched,
  scored, and drawn on a client-facing map as plots. They are not plots.

  Worse: not one placemark in that file has a <name>. Every parcel_ref on
  those rows came from the loader's positional fallback, PLOT-{index}. So
  PLOT-365 is line segment number 365 of a CAD export. The number reads
  exactly like a plot number and carries no information about the ground.

WHY POLYGONIZING IS NOT INVENTING GEOMETRY

  This is the distinction the loader's own header draws about THIKA ALL.csv,
  and it lands on the other side of the line.

  The CSV is 1,715 beacons with no topology. Nothing in it says which beacon
  belongs to which plot, so building polygons from it would mean CHOOSING
  boundaries. That is invention and we refuse it.

  The KMZ is different. Every boundary is already drawn. The lines meet, they
  close, and the faces between them are determined - there is exactly one set
  of them and no choice to make. Recovering a face is reading the drawing,
  not deciding what it should have said. Two independent things confirm the
  reading: 463 of the faces land between 420 and 480 m2, which is one plot
  module repeated across a scheme, and the whole set totals 99.9 acres.

WHAT IS RECOVERED AND WHAT IS NOT

  RECOVERED: the boundaries, at full precision, exactly as drawn.
  NOT RECOVERED: the plot numbers. They are not in the file in any form -
  no names, no labels, no attributes. The numbering this script assigns is
  a MAP LABEL of ours, and every row says so in its provenance. To print a
  real plot number, the client must send the numbered source: the DXF with
  its text entities, a shapefile with an attribute table, or the mutation
  drawing.

WHY THE WHOLE LINE NETWORK GOES IN, NOT THE "SUBDIVISION" LAYERS

  Restricting the input to the layers whose names look like plot boundaries
  loses 72 real plots, because their frontage line was drawn on the `roads`
  layer instead. Which layer a line sits on is a drafting habit, not a fact
  about the ground. So every line is noded together and the FACES are
  filtered afterwards, by size and by shape, where the evidence is.

WHY THE GEOMETRY WORK HAPPENS IN POSTGIS

  ST_Node, ST_Polygonize and the gate all run on the same GEOS. Doing the
  noding in Python with a different library would mean a face could
  polygonize in one engine and fail validation in the other, which is the
  kind of disagreement that takes a week to find. It also means this script
  needs no geometry library at all.

WHAT IT WILL NOT DO WITHOUT BEING TOLD
  --dry-run is the default. It reports, writes the two preview files, and
  stops. Nothing reaches the database until --load, and the thirteen bad
  parcels are not withdrawn until --retire-stale.

USAGE
  python 04_polygonize_cad.py --dry-run
  python 04_polygonize_cad.py --load --retire-stale
  python 04_polygonize_cad.py --dry-run --min-m2 300 --max-acres 2
============================================================================
"""
import os
import re
import sys
import json
import zipfile
import argparse
from pathlib import Path
from collections import Counter

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
SAMPLES = BASE / "sample_parcels"
ENV_DIR = BASE.parent / "03_etl"
sys.path.insert(0, str(BASE))
from parcel_gate import gate, report, canonical_key, Verdict   # noqa: E402

DEFAULT_KMZ = "OAK GROVE.kmz"
PROJECT = "OAK GROVE"
REF_PREFIX = "OG"
TEST_COMPANY_SLUG = "geocode-test"

# WGS 84 / UTM zone 37S. Thika and Juja sit at 37 degrees east, near the
# centre of the zone, where scale distortion is about one part in 2,500. The
# geometry is transformed in and out of it only so that areas are in metres
# and the noding tolerance means something; the stored parcel is 4326
# throughout, so this choice cannot move a boundary.
METRIC_SRID = 32737

# Faces smaller than this are drawing artefacts: the little triangle where
# two segments cross slightly past each other. The gate's own floor is 40 m2;
# this is higher because a plotted residential scheme has no 100 m2 plots and
# leaving them in means 22 more rows for a human to dismiss by hand.
MIN_M2 = 150.0

# Above four acres, in a scheme whose plot module is 450 m2, a face is a
# block, a phase, or the drawing's own frame. Not a reject in principle -
# large parcels are real - but it is a question for the client, so it is held
# back rather than loaded.
MAX_ACRES = 4.0

# Perimeter squared over area. A circle scores 12.6, a square 16, a 15 x 30
# metre plot 18, a 6 x 200 metre road corridor 118. Forty separates plots
# from corridors with a wide margin either side, which is what a threshold
# has to do to be worth having.
MAX_COMPACTNESS = 40.0

# Two faces of the same block share a boundary, so they are zero metres
# apart. Half a metre is enough to group them and far too little to bridge a
# road.
BLOCK_EPS_M = 0.5


# ---------------------------------------------------------------------------
# READING THE FILE
# ---------------------------------------------------------------------------
def read_lines(path):
    """-> [(layer, [(lon, lat), ...])]. Every coordinate string in the file.

    Not parsed with ElementTree. Google Earth writes gx: prefixes it never
    declares and ElementTree refuses the whole document over it, which would
    make this fail on precisely the files it exists to read.
    """
    p = Path(path)
    if not p.exists():
        sys.exit(f"Not found: {p}")
    if p.suffix.lower() == ".kmz":
        with zipfile.ZipFile(p) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                sys.exit(f"No .kml inside {p.name}")
            if len(names) > 1:
                print(f"   NOTE: {len(names)} .kml files inside; reading "
                      f"{names[0]} only.")
            raw = z.read(names[0]).decode("utf-8", "ignore")
    else:
        raw = p.read_text(encoding="utf-8", errors="ignore")

    out = []
    for blk in re.split(r"<Placemark[^>]*>", raw)[1:]:
        m = re.search(r"<td>Layer</td>\s*\n*\s*<td>(.*?)</td>", blk, re.S)
        layer = m.group(1).strip() if m else "(none)"
        for c in re.finditer(r"<coordinates>(.*?)</coordinates>", blk,
                             re.S | re.I):
            pts = []
            for tok in c.group(1).split():
                bits = tok.split(",")
                if len(bits) >= 2:
                    try:
                        pts.append((float(bits[0]), float(bits[1])))
                    except ValueError:
                        pass
            # Consecutive duplicates make a zero-length segment that GEOS
            # will node into nothing. Dropping them here keeps the count
            # honest rather than losing them silently later.
            clean = [pts[0]] if pts else []
            for q in pts[1:]:
                if q != clean[-1]:
                    clean.append(q)
            if len(clean) >= 2:
                out.append((layer, clean))
    return out


def wkt_line(pts, ndp=None):
    """repr(), not a format string. THIS LINE IS THE WHOLE SCRIPT.

    The first version wrote coordinates as %.8f. Eight decimal places of
    longitude is 1.1 mm, which sounds like more precision than any survey
    could justify, and it silently destroyed more than half the scheme:

        %.8f  (1.1 mm)         720 faces -> 308
        full precision         720 faces

    The reason is that polygonizing needs the network NODED, and a line only
    nodes against another where they actually touch. In this drawing a plot's
    dividing line ends exactly on the block boundary, exact to the last bit
    the file carries. Round both to a millimetre and the endpoint lands just
    off the boundary, the dividing line becomes a dangle, and the two plots
    it separated merge into one face of double the size. Nothing errors. You
    get 274 plots of 886 m2 instead of 688 of 450 m2, and every one of them
    is wrong in a way that looks entirely plausible.

    So no coordinate is rounded anywhere on the way in. repr() round-trips a
    Python float exactly. The `ndp` argument exists only for the sensitivity
    check below, which deliberately does round, in order to measure how much
    that would cost.
    """
    if ndp is None:
        return "LINESTRING(" + ", ".join(f"{x!r} {y!r}" for x, y in pts) + ")"
    return ("LINESTRING(" +
            ", ".join(f"{round(x, ndp)} {round(y, ndp)}" for x, y in pts) +
            ")")


def kml_doc(rows):
    """rows: [(ref, kml_polygon_fragment)] -> a KML document as text.

    Written so it can be dropped straight onto the original in Google Earth
    Pro. Comparing the two by eye is the only test that answers the question
    that was actually asked, which was whether this looks like the ground.
    """
    body = []
    for ref, frag in rows:
        body.append(f"<Placemark><name>{ref}</name>"
                    f"<styleUrl>#g</styleUrl>{frag}</Placemark>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f'<name>{PROJECT} - recovered plots</name>'
        '<Style id="g"><LineStyle><color>ff2d5314</color><width>2</width>'
        '</LineStyle><PolyStyle><color>4000ff00</color></PolyStyle></Style>'
        + "".join(body) +
        '</Document></kml>')


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kmz", nargs="?", default=str(SAMPLES / DEFAULT_KMZ))
    ap.add_argument("--load", action="store_true",
                    help="actually write to the database")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retire-stale", action="store_true",
                    help="withdraw active parcels of this project that this "
                         "file does not produce")
    ap.add_argument("--limit", type=int, default=0,
                    help="load only the first N, for a trial run")
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--prefix", default=REF_PREFIX)
    ap.add_argument("--min-m2", type=float, default=MIN_M2)
    ap.add_argument("--max-acres", type=float, default=MAX_ACRES)
    ap.add_argument("--compactness", type=float, default=MAX_COMPACTNESS)
    ap.add_argument("--metric-srid", type=int, default=METRIC_SRID)
    a = ap.parse_args()

    if not a.load:
        a.dry_run = True

    print("=" * 74)
    print(f"RECOVER PLOTS FROM A LINE NETWORK   {Path(a.kmz).name}")
    print("=" * 74)

    feats = read_lines(a.kmz)
    if not feats:
        sys.exit("No coordinate strings in that file at all.")
    lay = Counter(l for l, _ in feats)
    seg = sum(1 for _, p in feats if len(p) == 2)
    print(f"\n1. The file")
    print(f"   {len(feats):,} lines on {len(lay)} layer(s); "
          f"{seg:,} are two-point segments")
    for name, n in lay.most_common(8):
        print(f"      {name:<28} {n:>6,}")
    if len(lay) > 8:
        print(f"      ... and {len(lay) - 8} more layers")
    print("   Every layer goes in. Which layer a line was drawn on is a")
    print("   drafting habit, not a fact about the ground, and restricting")
    print("   the input to the subdivision layers loses the plots whose")
    print("   frontage was drawn on the road layer.")

    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")

    srid = int(a.metric_srid)
    conn = engine.connect()
    try:
        # Temp tables belong to one connection, so everything below shares
        # this one. They vanish when it closes, including on a crash, which
        # is the point: a failed run leaves nothing behind to confuse the
        # next one.
        conn.execute(text("DROP TABLE IF EXISTS _cad_lines"))
        conn.execute(text(
            f"CREATE TEMP TABLE _cad_lines "
            f"(layer text, g geometry(LineString, {srid}))"))
        conn.execute(
            text(f"INSERT INTO _cad_lines (layer, g) VALUES "
                 f"(:l, ST_Transform(ST_GeomFromText(:w, 4326), {srid}))"),
            [{"l": l, "w": wkt_line(p)} for l, p in feats])

        print("\n2. Noding and polygonizing")
        conn.execute(text("DROP TABLE IF EXISTS _cad_faces"))
        conn.execute(text(f"""
            CREATE TEMP TABLE _cad_faces AS
            SELECT row_number() OVER () AS fid, d.g,
                   ST_Area(d.g) AS a, ST_Perimeter(d.g) AS p
              FROM (SELECT (ST_Dump(ST_Polygonize(n.g))).geom AS g
                      FROM (SELECT ST_Node(ST_Union(g)) AS g
                              FROM _cad_lines) n) d"""))
        total = conn.execute(text("SELECT count(*) FROM _cad_faces")).scalar()
        print(f"   {total:,} closed faces")
        if not total:
            sys.exit("   No faces. The lines do not close - the drawing has "
                     "gaps.\n   Nothing can be recovered from it without "
                     "snapping, and snapping\n   moves boundaries, which we "
                     "do not do. Ask for the DXF.")

        # HOW MUCH DOES PRECISION MATTER HERE?
        #
        # This exists because rounding the input to a millimetre cost this
        # file 412 of its 720 faces, and produced a result that looked
        # perfectly reasonable: fewer plots, each about twice the size,
        # no error, no warning. Anything that quietly halves a scheme has
        # to be measured rather than assumed away.
        #
        # So the same network is polygonized again on a 1 mm grid and the
        # counts are compared. This is not a pass or a fail. It is the
        # answer to "how exact does this drawing have to be", and on a CAD
        # export the answer is usually "completely", which is worth knowing
        # before anyone downstream decides eight decimal places is plenty.
        conn.execute(text("DROP TABLE IF EXISTS _cad_coarse"))
        conn.execute(text(
            f"CREATE TEMP TABLE _cad_coarse (g geometry(LineString, {srid}))"))
        conn.execute(
            text(f"INSERT INTO _cad_coarse (g) VALUES "
                 f"(ST_Transform(ST_GeomFromText(:w, 4326), {srid}))"),
            [{"w": wkt_line(p, ndp=8)} for _, p in feats])
        coarse = conn.execute(text("""
            SELECT count(*) FROM (
              SELECT (ST_Dump(ST_Polygonize(n.g))).geom
                FROM (SELECT ST_Node(ST_Union(g)) AS g
                        FROM _cad_coarse) n) x""")).scalar()
        conn.execute(text("DROP TABLE _cad_coarse"))
        lost = total - coarse
        print(f"   the same network rounded to 1 mm gives {coarse:,} faces "
              f"({lost:+,})")
        if abs(lost) > total * 0.02:
            print("   THIS DRAWING'S TOPOLOGY IS EXACT ONLY AT FULL "
                  "PRECISION.")
            print("   Nothing downstream may round these coordinates. A "
                  "dividing line")
            print("   that stops a fraction of a millimetre short of the "
                  "block boundary")
            print("   is a dangle, and the two plots it separated merge into "
                  "one face of")
            print("   double the size, with no error anywhere.")
            precision_note = (
                f" The drawing's topology is exact only at full precision: "
                f"rounding the input to 1 mm yields {coarse} faces instead of "
                f"{total}, merging plots in pairs without any error. No "
                f"coordinate was rounded on the way in.")
        else:
            precision_note = ""

        amax = a.max_acres * 4046.86
        binds = {"amin": a.min_m2, "amax": amax, "cmp": a.compactness}

        print("\n3. Which faces are plots")
        drops = conn.execute(text("""
            SELECT CASE
                     WHEN a < :amin THEN 'smaller than the floor'
                     WHEN a > :amax THEN 'larger than the ceiling'
                     WHEN p * p / NULLIF(a, 0) > :cmp THEN 'corridor-shaped'
                     ELSE 'kept' END AS why,
                   count(*), min(a), max(a)
              FROM _cad_faces GROUP BY 1 ORDER BY 2 DESC"""), binds).all()
        for why, n, lo, hi in drops:
            print(f"   {why:<26} {n:>6,}   {lo:>12,.0f} to {hi:>12,.0f} m2")
        print(f"   floor {a.min_m2:,.0f} m2, ceiling {a.max_acres:g} acres "
              f"({amax:,.0f} m2), compactness {a.compactness:g}")

        # THE FACES THAT WERE HELD BACK, NAMED.
        #
        # A count of rejects is a number nobody checks. On this file three of
        # them turned out to be stray rectangles sitting 14 km off site,
        # which is only visible if the rejects have coordinates attached.
        held = conn.execute(text("""
            SELECT fid, round(a::numeric, 0),
                   round(ST_X(ST_Transform(ST_Centroid(g), 4326))::numeric, 5),
                   round(ST_Y(ST_Transform(ST_Centroid(g), 4326))::numeric, 5)
              FROM _cad_faces
             WHERE NOT (a >= :amin AND a <= :amax
                        AND p * p / NULLIF(a, 0) <= :cmp)
             ORDER BY a DESC LIMIT 8"""), binds).all()
        if held:
            print("   largest held back (check these by eye before you "
                  "widen a threshold):")
            for fid, ar, x, y in held:
                print(f"      face {fid:<5} {ar:>12,.0f} m2   at {y},{x}")

        # THE NUMBERING.
        #
        # There is nothing to derive it from, so it is derived from position
        # and says so. Blocks first, by how far north they start, then west
        # to east; within a block, along the block from its south-west corner
        # so that consecutive numbers are neighbours on the ground. That last
        # part is what makes a scheme map readable, and it is the only reason
        # this is not simply sorted by latitude.
        #
        # It is deterministic: the same file produces the same numbers.
        rows = conn.execute(text(f"""
            WITH kept AS (
              SELECT fid, g, a,
                     ST_ClusterDBSCAN(g, {BLOCK_EPS_M}, 1) OVER () AS blk
                FROM _cad_faces
               WHERE a >= :amin AND a <= :amax
                 AND p * p / NULLIF(a, 0) <= :cmp
            ),
            blocks AS (
              SELECT blk AS b, ST_Collect(g) AS bg FROM kept GROUP BY blk
            ),
            ordered AS (
              SELECT k.fid, k.g, k.a, k.blk,
                     ST_YMax(b.bg) AS north, ST_XMin(b.bg) AS west,
                     ST_Distance(ST_Centroid(k.g),
                                 ST_SetSRID(ST_MakePoint(ST_XMin(b.bg),
                                                         ST_YMin(b.bg)),
                                            {srid})) AS along
                FROM kept k JOIN blocks b ON b.b = k.blk
            )
            SELECT fid, blk,
                   ST_AsText(ST_Transform(g, 4326)),
                   ST_AsGeoJSON(ST_Transform(g, 4326)),
                   ST_AsKML(ST_Transform(g, 4326)),
                   round(a::numeric, 1),
                   round((a / 4046.86)::numeric, 4)
              FROM ordered
             ORDER BY north DESC, west ASC, along ASC, fid"""), binds).all()

        n_blocks = len({r[1] for r in rows})
        acres = [float(r[6]) for r in rows]
        print(f"\n   {len(rows):,} plots in {n_blocks} block(s)")
        if acres:
            s = sorted(acres)
            print(f"   size: smallest {s[0]:.3f} ac, median "
                  f"{s[len(s) // 2]:.3f} ac, largest {s[-1]:.3f} ac")
            print(f"   total {sum(acres):.1f} acres "
                  f"({sum(acres) * 0.404686:.1f} ha)")

        width = max(3, len(str(len(rows))))
        refs = [f"{a.prefix}-{i:0{width}d}" for i in range(1, len(rows) + 1)]

        # ---- the preview, written before anything is decided --------------
        gj = {"type": "FeatureCollection", "features": [
            {"type": "Feature",
             "properties": {"ref": ref, "block": int(r[1]),
                            "area_m2": float(r[5]), "acres": float(r[6])},
             "geometry": json.loads(r[3])}
            for ref, r in zip(refs, rows)]}
        p_gj = BASE / f"recovered_{a.project.replace(' ', '_')}.geojson"
        p_kml = BASE / f"recovered_{a.project.replace(' ', '_')}.kml"
        p_gj.write_text(json.dumps(gj), encoding="utf-8")
        p_kml.write_text(kml_doc(list(zip(refs, [r[4] for r in rows]))),
                         encoding="utf-8")
        print(f"\n4. Preview written")
        print(f"   {p_kml.name}")
        print(f"   {p_gj.name}")
        print("   OPEN THE .kml IN GOOGLE EARTH PRO, ON TOP OF THE ORIGINAL.")
        print("   If the recovered plots sit exactly on the drawn ones, the")
        print("   reading is right. Nothing else settles that question, and")
        print("   no count printed above settles it either.")

        # ---- the gate ------------------------------------------------------
        #
        # EVERYTHING FROM HERE RUNS IN ONE TRANSACTION ON ONE CONNECTION, and
        # a dry run is that transaction rolled back rather than a different
        # code path. The reason is specific and it was very nearly a bug:
        #
        #   The gate rejects a parcel that overlaps an ACTIVE parcel of the
        #   same company. The thirteen fragments are still active, and one of
        #   them is a 191-point polyline closed into a polygon that lies
        #   across a large part of the site. Gated against a database that
        #   still holds it, dozens of correct plots would be rejected for
        #   overlapping a thing that is not a parcel.
        #
        # So the withdrawal happens FIRST, inside the transaction, and the
        # gate sees the database as it will be. A dry run that gates against
        # a different database than the load is a dry run that answers a
        # different question, which is rule E14 wearing a new hat.
        print(f"\n5. Gate")
        cid = conn.execute(text(
            "SELECT company_id FROM clients.companies WHERE slug = :s"),
            {"s": TEST_COMPANY_SLUG}).scalar()
        if cid is None:
            sys.exit("   Test company missing. Run 01_create_test_parcels.sql")

        wkts = [r[2] for r in rows]
        # Staleness is judged against every ref THIS FILE PRODUCES, not
        # against the subset a --limit run happens to load. Otherwise a trial
        # run of twenty plots would call the other 668 stale and, with
        # --retire-stale, withdraw them.
        all_refs = set(refs)
        if a.limit:
            refs, wkts = refs[:a.limit], wkts[:a.limit]
            print(f"   --limit {a.limit}: only the first {a.limit} considered")

        existing = {r[0] for r in conn.execute(text("""
            SELECT parcel_ref FROM land.parcels
             WHERE company_id = :c AND project_name = :p
               AND status = 'active'"""),
            {"c": cid, "p": a.project}).all()}
        stale = sorted(existing - all_refs)

        # THE THIRTEEN. Not "a phase the client left out of this export",
        # which is the case the old loader was right to refuse to guess
        # about. These are fragments of a line network that were mistaken for
        # parcels, and we know that because we have now read the file they
        # came from. Withdrawing them is still a decision, so it takes a flag.
        if stale:
            if a.retire_stale:
                for ref in stale:
                    conn.execute(text("""
                        UPDATE land.parcels
                           SET status = 'rejected', updated_at = now()
                         WHERE company_id = :c AND project_name = :p
                           AND parcel_ref = :r AND status = 'active'"""),
                        {"c": cid, "p": a.project, "r": ref})
                print(f"   {len(stale)} stale parcel(s) withdrawn first, so "
                      f"the gate is not\n   comparing new plots against them.")
            else:
                print(f"   {len(stale)} parcel(s) of this project are ACTIVE "
                      f"and not in this file.")
                print("   They are being left in place, which means the gate "
                      "will reject any")
                print("   new plot that overlaps one. If the numbers below "
                      "look wrong, that")
                print("   is why. Re-run with --retire-stale.")

        # Same ground drawn twice. Polygonize cannot produce two faces over
        # one area, so this should find nothing, which is exactly why it is
        # worth running. If it ever fires, the reading is wrong.
        keys = [canonical_key(conn, w) for w in wkts]
        seen = {}
        for k, ref in zip(keys, refs):
            seen.setdefault(k, []).append(ref)
        twins = {r for g in seen.values() if len(g) > 1 for r in g}
        if twins:
            print(f"   {len(twins)} faces describe the same ground as another "
                  f"face. That cannot\n   happen when polygonizing a single "
                  f"network. Stop and read the file again.")

        usable, rejected, quiet, why = [], 0, Counter(), Counter()
        for ref, w in zip(refs, wkts):
            if ref in twins:
                rejected += 1
                continue
            v, conf, findings = gate(conn, w, cid, ref=ref)
            if v == Verdict.REJECT:
                rejected += 1
                for h, _ in findings:
                    why[h.split(" by ")[0].split(" to ")[0]] += 1
                if rejected <= 10:
                    report(ref, v, findings)
                continue
            if findings:
                # 688 accepted plots printing three lines each is 2,000 lines
                # nobody reads. Counted here, printed as a summary.
                for h, _ in findings:
                    quiet[h.split(" by ")[0].split(" to ")[0]] += 1
            usable.append((ref, w, conf))
        if rejected > 10:
            print(f"   ... {rejected - 10} further rejections not printed")
        print(f"   {len(usable):,} accepted, {rejected} rejected")
        for h, n in why.most_common():
            print(f"      {n:>5,} rejected: {h}")
        for h, n in quiet.most_common():
            print(f"      {n:>5,} accepted with a note: {h}")

        if not usable:
            conn.rollback()
            sys.exit("   Nothing loadable.")

        # ---- load ----------------------------------------------------------
        note = (
            f"RECOVERED GEOMETRY. Polygonized from the line network in "
            f"{Path(a.kmz).name}, which is an AutoCAD drawing exported to KML "
            f"and contains no polygons. Every boundary is exactly as drawn; "
            f"the faces are determined by the network and were not chosen. "
            f"KML is WGS84 by specification, so no CRS assumption applies. "
            f"*** THE PLOT NUMBER IS OURS, NOT THE SCHEME'S. The source file "
            f"has no names, labels or attributes of any kind. "
            f"'{a.prefix}-nnn' is a map label assigned by position (block "
            f"from north-west, then along the block) and MUST NOT be printed "
            f"to a buyer as the scheme's plot number. For a real plot number, "
            f"get the numbered source from the client: the DXF with its text "
            f"entities, a shapefile with an attribute table, or the mutation "
            f"drawing. ***" + precision_note)

        if a.dry_run:
            # The withdrawal above and everything the gate learned from it
            # are discarded here. Nothing this run did survives.
            conn.rollback()
            print("\n6. DRY RUN. Rolled back. Nothing written.")
            print("   Look at the KML first. Then:")
            print(f"     python {Path(__file__).name} --load --retire-stale")
            return

        # RUNNING THIS TWICE ON AN UNCHANGED FILE MUST CHANGE NOTHING.
        #
        # The first version did not, and it cost 688 rows. The load was run,
        # then run again a minute later, and the second run superseded all
        # 688 parcels and re-inserted them at version 2 with byte-identical
        # geometry. Nothing broke - everything downstream filters on
        # status = 'active' - but the parcel table doubled, and half of it is
        # a version history of an event that never happened.
        #
        # A version means the client changed something. Manufacturing one
        # because a command was typed twice makes the version number a record
        # of our keystrokes rather than of their land. So the geometry is
        # compared to what is already active, with ST_Equals rather than a
        # string or hash comparison: the same ring wound the other way or
        # started at a different corner is the SAME GROUND, and this must not
        # treat it as a change.
        n = superseded = unchanged = 0
        for ref, w, conf in usable:
            if ref in existing:
                same = conn.execute(text("""
                    SELECT ST_Equals(geom,
                             ST_Multi(ST_MakeValid(ST_GeomFromText(:w, 4326))))
                           AND confidence IS NOT DISTINCT FROM :conf
                      FROM land.parcels
                     WHERE company_id = :c AND parcel_ref = :r
                       AND status = 'active'"""),
                    {"c": cid, "r": ref, "w": w, "conf": conf}).scalar()
                if same:
                    unchanged += 1
                    continue
                conn.execute(text("""
                    UPDATE land.parcels
                       SET status = 'superseded', updated_at = now()
                     WHERE company_id = :c AND parcel_ref = :r
                       AND status = 'active'"""), {"c": cid, "r": ref})
                superseded += 1
            ver = conn.execute(text("""
                SELECT coalesce(max(version), 0) + 1 FROM land.parcels
                 WHERE company_id = :c AND parcel_ref = :r"""),
                {"c": cid, "r": ref}).scalar()
            conn.execute(text("""
                INSERT INTO land.parcels
                    (company_id, parcel_ref, project_name, listing_status,
                     geom, confidence, version, status, test_expectation)
                VALUES (:c, :ref, :p, 'available',
                        ST_Multi(ST_MakeValid(ST_GeomFromText(:w, 4326)))
                            ::geometry(MultiPolygon, 4326),
                        :conf, :v, 'active', :note)"""),
                {"c": cid, "ref": ref, "p": a.project, "w": w,
                 "conf": conf, "v": ver, "note": note})
            n += 1
        conn.commit()

        print(f"\n6. Load")
        if unchanged and not n:
            print(f"   NOTHING TO DO. All {unchanged:,} parcels are already "
                  f"loaded with exactly")
            print("   this geometry. No new versions were created.")
        else:
            print(f"   {n:,} parcel(s) inserted as project '{a.project}' "
                  f"({superseded} replaced an earlier version)")
            if unchanged:
                print(f"   {unchanged:,} left alone - already active with "
                      f"exactly this geometry.")
        if stale:
            if a.retire_stale:
                print(f"   {len(stale)} parcel(s) withdrawn, not deleted. "
                      f"Their enrichment,")
                print("   scores and any issued reports are intact and still "
                      "reachable by")
                print("   parcel_id:")
            else:
                print(f"   {len(stale)} parcel(s) are still ACTIVE and are "
                      f"not in this file.")
                print("   They were left alone. Re-run with --retire-stale to "
                      "withdraw them.")
            for ref in stale[:20]:
                print(f"      {ref}")
            if len(stale) > 20:
                print(f"      ... and {len(stale) - 20} more")

        # The count that matters here is what enrichment will face, which is
        # every ACTIVE parcel of this project - not how many rows this run
        # happened to insert. On a re-run that inserts nothing, printing `n`
        # said "that is now 0 parcels", which is both wrong and alarming.
        live = conn.execute(text("""
            SELECT count(*) FROM land.parcels
             WHERE company_id = :c AND project_name = :p
               AND status = 'active'"""),
            {"c": cid, "p": a.project}).scalar()
        print("\nNEXT")
        print("   python enrich_01_engine.py")
        print(f"   '{a.project}' now has {live:,} active parcels. Expect it "
              f"to take a while,")
        print("   and expect the widget's scheme map to need paging: it "
              "labels 1-9")
        print("   then A-Z and gives up at 35, which was fine for five "
              "plots.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
