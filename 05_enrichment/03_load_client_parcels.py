r"""
============================================================================
LOAD CLIENT PARCELS - real geometry from OAK GROVE.kmz
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHAT THIS LOADS, AND WHAT IT DELIBERATELY DOES NOT

  LOADS: the 13 rings from OAK GROVE.kmz.
    KML is WGS84 longitude/latitude BY SPECIFICATION, so there is no CRS
    decision to get wrong. These are real polygons drawn by whoever prepared
    the scheme, which is exactly what the enrichment engine needs to be tested
    against - the synthetic landmark parcels test whether it gets KNOWN
    answers right; these test whether it survives real geometry.

  DOES NOT LOAD: plot polygons built from THIKA ALL.csv.

    The CSV is 1,715 survey beacons with no topology. Checking the first few
    points shows why that matters: a1, a6 and a5 are COLLINEAR - the distance
    a1->a6 plus a6->a5 equals a1->a5 to within a decimetre. Those are points
    ALONG a boundary line, not the corners of one plot.

    So consecutive groups of four are not plots, and nothing in the file says
    which beacon belongs to which parcel. Reconstructing polygons from it
    would be INVENTING GEOMETRY and then selling analysis computed on it.
    The plot topology has to come from the client - a DXF, a shapefile, or the
    mutation drawing.

THE CRS, SETTLED BY ASKING
  The surveyor confirms Arc 1960 / UTM zone 37S, EPSG:21037. That matches the
  Survey of Kenya cadastral datum and it is what a Kenyan survey export should
  be in.

  It was NOT settled by measurement, and the record should say so. Two
  attempts failed:
    1. centroid-to-centroid: returned an identical 272 m for two datums that
       are ~315 m apart, because the KMZ covers a different subset than the
       CSV and the extent mismatch swamped the signal;
    2. nearest-beacon-to-corner: returned 25.7 m and 17.2 m, both of which are
       simply the mean nearest-neighbour distance in a cloud of 1,715 points
       over 127.6 ha (one point per ~27 m). It was measuring point density.

  Both were tests that could not fail cleanly - lesson 19, committed in the
  verification rather than the ETL.

  So EPSG:21037 is recorded as an ASSERTION FROM THE SURVEYOR, on every row,
  in provenance. If it is ever found to be wrong, the error is discoverable
  and every affected parcel is identifiable.

THE ONE TEST THAT IS STILL WORTH RUNNING
  With the CRS known, transform the CSV and ask how many beacons fall INSIDE
  the KML rings. If both files describe the same scheme, most should. If
  almost none do, the two files are different sites - which is likely, since
  they are named differently and 13 rings spanning the full 1.1 km extent
  means each ring is ~24 acres, i.e. blocks or phases rather than plots.

  That question does not block the load either way. It changes what the CSV
  can later be used for.

How to run (from 05_enrichment, venv active):
  python 03_load_client_parcels.py --dry-run
  python 03_load_client_parcels.py
============================================================================
"""

import os
import sys
import csv
import math
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parcel_gate import gate, report, canonical_key, Verdict

try:
    from pyproj import Transformer
except ImportError:
    sys.exit("ERROR: pyproj missing. pip install pyproj")

BASE = Path(__file__).resolve().parent
SAMPLES = BASE / "sample_parcels"
ENV_DIR = BASE.parent / "03_etl"

# Confirmed by the surveyor who produced the file. NOT confirmed by
# measurement - see the header. Override with --crs if that ever changes.
CSV_CRS = "EPSG:21037"          # Arc 1960 / UTM zone 37S
PROJECT = "OAK GROVE"
TEST_COMPANY_SLUG = "geocode-test"
# 0.01 acres is about 40 m2. Nothing sellable in Kenya is that small, so
# anything below it is a drawing artefact rather than a parcel.
MIN_PARCEL_ACRES = 0.01


def read_kml_rings(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not names:
            sys.exit("No .kml inside the .kmz")
        raw = z.read(names[0]).decode("utf-8", "ignore")

    import re
    rings, names_out = [], []
    # Google Earth writes gx: prefixes without declaring them, which
    # ElementTree rejects. Pull placemarks textually - it is robust and this
    # file has already proved malformed.
    blocks = re.split(r"<Placemark[^>]*>", raw)[1:]
    for i, blk in enumerate(blocks, 1):
        nm = re.search(r"<name>(.*?)</name>", blk, re.S | re.I)
        nm = nm.group(1).strip() if nm else f"PLOT-{i:03d}"
        for m in re.finditer(r"<coordinates>(.*?)</coordinates>",
                             blk, re.S | re.I):
            ring = []
            for tok in m.group(1).split():
                bits = tok.split(",")
                if len(bits) >= 2:
                    try:
                        ring.append((float(bits[0]), float(bits[1])))
                    except ValueError:
                        pass
            if len(ring) >= 3:
                if ring[0] != ring[-1]:
                    ring.append(ring[0])       # close it
                rings.append(ring)
                names_out.append(nm)
            break
    return names_out, rings


def read_csv_points(path):
    pts = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            try:
                a, b = float(row[1]), float(row[2])
            except ValueError:
                continue
            north, east = (a, b) if a > b else (b, a)
            pts.append((row[0].strip(), north, east))
    return pts


def wkt_polygon(ring):
    body = ", ".join(f"{lon:.8f} {lat:.8f}" for lon, lat in ring)
    return f"MULTIPOLYGON((({body})))"


def main():
    dry = "--dry-run" in sys.argv
    crs = CSV_CRS
    if "--crs" in sys.argv:
        crs = sys.argv[sys.argv.index("--crs") + 1]

    kmz = SAMPLES / "OAK GROVE.kmz"
    csvf = SAMPLES / "THIKA ALL.csv"
    if not kmz.exists():
        sys.exit(f"Not found: {kmz}")

    names, rings = read_kml_rings(kmz)
    print(f"OAK GROVE.kmz -> {len(rings)} ring(s)")
    if not rings:
        sys.exit("No usable rings.")

    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")

    # ---- THE GATE ---------------------------------------------------------
    #
    # Every rule that used to live inline here now lives in parcel_gate.py,
    # because the product will read shapefiles and DXFs as well as this KMZ
    # and a rule re-implemented per format is a rule that will differ per
    # format. What changed in the move is one thing, and it matters:
    #
    #   This section used to print "*** DO NOT QUOTE THIS AREA ***" on a
    #   polygon whose area moved by more than half under repair, and then
    #   LOAD IT ANYWAY. Everything downstream then quoted it. The gate
    #   rejects it. We sell the size of the land; we cannot load a parcel
    #   whose size we would be guessing.
    #
    # The company is resolved BEFORE the gate runs, because half the checks
    # are about collisions with parcels this client already has - a duplicate
    # is only meaningful within one company's inventory.
    with engine.connect() as conn:
        cid = conn.execute(text(
            "SELECT company_id FROM clients.companies WHERE slug = :s"),
            {"s": TEST_COMPANY_SLUG}).scalar()
    if cid is None:
        sys.exit("Test company missing. Run 01_create_test_parcels.sql.")

    # PASS 1 - WHICH RINGS DESCRIBE THE SAME GROUND AS ANOTHER RING HERE.
    #
    # This has to happen before anything is accepted, and the first version
    # got it wrong in a way the test run could not show. It kept a set of
    # WKT strings and rejected the SECOND ring that matched one already
    # accepted - so on a fresh database the duplicate's twin would have
    # LOADED, while the message printed beside it said "neither parcel is
    # loaded until the client says which it is". A message that lies is worse
    # than no message.
    #
    # It only looked correct on this run because PLOT-1069 and PLOT-1070 were
    # already in the database from a previous load, so the collision check
    # caught them both. Delete those rows and the bug reappears.
    #
    # Neither twin loads. We cannot tell a drafting duplicate from the same
    # ground sold twice, and picking one would be picking at random.
    print("\n1. Gate")
    with engine.connect() as conn:
        keys = [canonical_key(conn, wkt_polygon(r)) for r in rings]
    dupes = {}
    for k, nm in zip(keys, names):
        dupes.setdefault(k, []).append(nm[:60])
    dupe_of = {nm: [o for o in group if o != nm]
               for group in dupes.values() if len(group) > 1
               for nm in group}

    usable, rejected = [], 0
    with engine.connect() as conn:
        for i, (nm, ring) in enumerate(zip(names, rings), 1):
            w = wkt_polygon(ring)
            ref = nm[:60]

            if ref in dupe_of:
                rejected += 1
                others = ", ".join(dupe_of[ref])
                report(ref, Verdict.REJECT, [
                    (f"identical to {others} in this same file",
                     "Two placemarks in this file draw exactly the same "
                     "ground. Neither is loaded - the geometry cannot tell a "
                     "drafting duplicate from the same land allocated twice, "
                     "and the difference matters enormously. Ask the client "
                     "which is the real plot.")])
                continue

            verdict, conf, findings = gate(conn, w, cid, ref=ref)
            report(ref, verdict, findings)
            if verdict == Verdict.REJECT:
                rejected += 1
                continue
            usable.append((nm, ring, conf))

    print(f"\n   {len(usable)} accepted, {rejected} rejected, "
          f"of {len(rings)} placemarks.")
    if not usable:
        sys.exit("Nothing loadable.")

    # ---- the same-site question -----------------------------------------
    if csvf.exists():
        pts = read_csv_points(csvf)
        tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        lons, lats = tr.transform([p[2] for p in pts], [p[1] for p in pts])
        print(f"\n2. Are THIKA ALL.csv and OAK GROVE the same site?")
        print(f"   {len(pts):,} beacons transformed from {crs}")

        # BOUNDING BOX OVERLAP, not point containment.
        #
        # Containment was the wrong test and it was wrong before it ran:
        # survey beacons sit ON plot boundaries, and ST_Contains EXCLUDES
        # boundary points. Worse, these turned out to be 13 scattered plots of
        # 0.14-2.31 acres out of ~429 in the scheme, so even a perfect match
        # would have put almost no beacons "inside" them.
        #
        # Box overlap does not care about topology, sampling density or which
        # subset the KMZ happens to cover. Either the two files describe the
        # same ground or they do not.
        clon0, clon1 = min(lons), max(lons)
        clat0, clat1 = min(lats), max(lats)
        # Bounds of the USABLE parcels only - the skipped LineStrings and
        # slivers should not stretch the comparison box.
        ring_pts = [c for _, r, _ in usable for c in r]
        klon0 = min(c[0] for c in ring_pts)
        klon1 = max(c[0] for c in ring_pts)
        klat0 = min(c[1] for c in ring_pts)
        klat1 = max(c[1] for c in ring_pts)
        ox = max(0.0, min(clon1, klon1) - max(clon0, klon0))
        oy = max(0.0, min(clat1, klat1) - max(clat0, klat0))
        karea = (klon1 - klon0) * (klat1 - klat0)
        overlap = 100.0 * (ox * oy) / karea if karea > 0 else 0.0
        print(f"   CSV  bbox  {clat0:.5f}..{clat1:.5f}, "
              f"{clon0:.5f}..{clon1:.5f}")
        print(f"   KML  bbox  {klat0:.5f}..{klat1:.5f}, "
              f"{klon0:.5f}..{klon1:.5f}")
        print(f"   -> {overlap:.1f}% of the KML extent falls inside the CSV "
              f"extent")
        if overlap >= 80:
            print("   SAME SITE. The KMZ plots sit within the surveyed "
                  "scheme, which independently corroborates EPSG:21037 - a")
            print("   200 m datum error would have pushed them off the edge.")
        elif overlap >= 20:
            print("   PARTIAL OVERLAP. Same area, but the KMZ extends beyond "
                  "the surveyed points or vice versa. Worth an eye in QGIS.")
        else:
            print("   LITTLE OR NO OVERLAP - different sites, or the CRS is "
                  "wrong. Check in QGIS before trusting either file.")

    # ---- load -------------------------------------------------------------
    if dry:
        print("\nDRY RUN - nothing written.")
        return

    # ---- LOAD: SUPERSEDE, NEVER DELETE -----------------------------------
    #
    # This used to be `DELETE FROM land.parcels WHERE project_name = ...`,
    # and the database refused it:
    #
    #   ForeignKeyViolation: update or delete on table "parcels" violates
    #   foreign key constraint "parcel_intelligence_parcel_id_fkey"
    #
    # THE FOREIGN KEY WAS RIGHT AND THE LOADER WAS WRONG. A client's second
    # upload is a normal event - they correct a plot, add a phase, fix a
    # boundary - and it must not be able to erase enrichment, scores or
    # reports already issued to buyers. Had the constraint not existed, this
    # run would have silently destroyed the history of three parcels.
    #
    # `supersede, never delete` is already the rule everywhere else in this
    # build: the enrichment engine versions parcel_intelligence that way, and
    # land.parcels has carried `status` and `version` since v1.0 for exactly
    # this. The loader was the one place that ignored it.
    #
    #   accepted, already present  -> old row superseded, new row at v+1
    #   accepted, new              -> inserted at v1
    #   REJECTED, already present  -> old row marked 'rejected', not deleted
    #   present but absent from the file -> LEFT ALONE and reported
    #
    # That last one matters. A plot missing from a new file might be sold,
    # or it might be a client exporting one phase instead of all of them.
    # Guessing would be inventing a withdrawal, so we report and let a human
    # decide.
    accepted_refs = {nm[:60] for nm, _, _ in usable}
    file_refs = {nm[:60] for nm in names}

    with engine.begin() as conn:
        existing = {r[0]: r[1] for r in conn.execute(text("""
            SELECT parcel_ref, parcel_id FROM land.parcels
             WHERE company_id = :c AND project_name = :p
               AND status = 'active'"""), {"c": cid, "p": PROJECT}).all()}

        # Parcels the gate now refuses, which we previously loaded.
        withdrawn = sorted(set(existing) & (file_refs - accepted_refs))
        for ref in withdrawn:
            conn.execute(text("""
                UPDATE land.parcels SET status = 'rejected', updated_at = now()
                 WHERE company_id = :c AND parcel_ref = :r
                   AND status = 'active'"""), {"c": cid, "r": ref})

        # Parcels we hold that this file does not mention at all.
        unmentioned = sorted(set(existing) - file_refs)

        n, superseded = 0, 0
        for nm, ring, conf in usable:
            ref = nm[:60]
            if ref in existing:
                conn.execute(text("""
                    UPDATE land.parcels SET status = 'superseded',
                           updated_at = now()
                     WHERE company_id = :c AND parcel_ref = :r
                       AND status = 'active'"""), {"c": cid, "r": ref})
                superseded += 1
            ver = conn.execute(text("""
                SELECT coalesce(max(version), 0) + 1 FROM land.parcels
                 WHERE company_id = :c AND parcel_ref = :r"""),
                {"c": cid, "r": ref}).scalar()

            note = ("REAL CLIENT GEOMETRY from OAK GROVE.kmz. KML is WGS84 by "
                    "specification, so no CRS assumption applies to this "
                    "polygon. Companion file THIKA ALL.csv is EPSG:21037 per "
                    "the surveyor - ASSERTED, not confirmed by measurement.")
            if conf < 4:
                note += (" *** REPAIRED AT LOAD. The geometry held is not "
                         "exactly what the surveyor drew, so this parcel sits "
                         "below the scoring floor and will not be rated. ***")

            conn.execute(text("""
                INSERT INTO land.parcels
                    (company_id, parcel_ref, project_name, listing_status,
                     geom, confidence, version, status, test_expectation)
                VALUES (:c, :ref, :p, 'available',
                        ST_Multi(ST_MakeValid(ST_GeomFromText(:w, 4326)))
                            ::geometry(MultiPolygon, 4326),
                        :conf, :v, 'active', :note)"""),
                {"c": cid, "ref": ref, "p": PROJECT,
                 "w": wkt_polygon(ring), "conf": conf, "v": ver,
                 "note": note})
            n += 1

    print(f"\n3. Load")
    print(f"   {n} parcel(s) active as project '{PROJECT}' "
          f"({superseded} replaced an earlier version)")
    if withdrawn:
        print(f"   {len(withdrawn)} previously loaded parcel(s) now REJECTED "
              f"by the gate and withdrawn from sale:")
        for ref in withdrawn:
            print(f"      {ref}")
        print("   Their enrichment, scores and any issued reports are intact "
              "and still")
        print("   reachable by parcel_id. They are simply no longer active.")
    if unmentioned:
        print(f"   {len(unmentioned)} active parcel(s) are NOT in this file "
              f"and were LEFT ALONE:")
        for ref in unmentioned:
            print(f"      {ref}")
        print("   They may be sold, or the client may have exported one phase "
              "of several.")
        print("   Guessing would be inventing a withdrawal - ask them.")

    print("\nNEXT:")
    print("  python enrich_01_engine.py")


if __name__ == "__main__":
    main()
