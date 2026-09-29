r"""
============================================================================
WHAT IS ACTUALLY IN THIS FILE?
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS EXISTS

  `03_load_client_parcels.py` read OAK GROVE.kmz and reported "13 ring(s)".
  The file contains 1,086 placemarks. The other 1,073 were skipped in
  silence, because they are two-point line segments and the loader's ring
  test is `len(ring) >= 3`.

  Nothing lied. Nothing crashed. The load ran green, the enrichment ran
  green, the verifier ran green, and thirteen fragments of a CAD drawing sat
  in land.parcels for weeks wearing plot numbers that were array indices.

  That is rule E14 in its purest form - a green verification does not mean
  the answers are right - and it is also E16: a check that only checks what
  its author remembered is not a check. The loader's author remembered to
  count the rings it built. Nobody counted the ones it threw away.

  So: before any file is loaded, this says what is in it. It loads nothing,
  writes nothing and touches no database. It is allowed to be wrong about
  what the file MEANS. It is not allowed to be quiet about what the file
  CONTAINS.

WHAT IT REPORTS
  Every placemark, grouped by CAD layer and entity type, with the number of
  coordinate points on each. The last column is the one that matters:

     points  what it is
     ------  --------------------------------------------------------------
        2    a line SEGMENT. Not a parcel. Cannot be one.
      3-4    a short polyline, or a triangle. Usually a fragment.
       5+    a closed ring, or a long boundary line. Could be a parcel.

  If most of the file is in the "2" row, the file is a CAD drawing exported
  to KML and the parcels are the FACES the lines enclose, not the lines.
  Use 04_polygonize_cad.py.

USAGE
  python kmz_probe.py "sample_parcels/OAK GROVE.kmz"
  python kmz_probe.py somefile.kml --layers
============================================================================
"""
import re
import sys
import zipfile
import argparse
from pathlib import Path
from collections import Counter, defaultdict

# A CAD export writes its DXF attributes into an HTML table inside the
# placemark's description CDATA. That table is where Layer and Entity live,
# and it is the only place they live - KML itself has no concept of a layer.
TD = r"<td>{}</td>\s*\n*\s*<td>(.*?)</td>"


def read_kml(path):
    p = Path(path)
    if not p.exists():
        sys.exit(f"Not found: {p}")
    if p.suffix.lower() == ".kmz":
        with zipfile.ZipFile(p) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                sys.exit(f"No .kml inside {p.name}. Contents: {z.namelist()}")
            if len(names) > 1:
                print(f"NOTE: {len(names)} .kml files inside. Reading the "
                      f"first, {names[0]}. The others are NOT being read and "
                      f"may contain the rest of the scheme.")
            return z.read(names[0]).decode("utf-8", "ignore"), names[0]
    return p.read_text(encoding="utf-8", errors="ignore"), p.name


def field(blk, name):
    m = re.search(TD.format(name), blk, re.S)
    return m.group(1).strip() if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--layers", action="store_true",
                    help="list every layer with its point-count profile")
    a = ap.parse_args()

    raw, inner = read_kml(a.path)
    print("=" * 74)
    print(f"FILE PROBE  {Path(a.path).name}")
    print("=" * 74)
    doc = re.search(r"<Document[^>]*>\s*<name>(.*?)</name>", raw, re.S)
    print(f"  inner document   : {inner}")
    print(f"  document <name>  : {doc.group(1).strip() if doc else '(none)'}")
    print(f"  size             : {len(raw):,} bytes")

    # Geometry tags, counted on the raw text. Deliberately not parsed with an
    # XML library: Google Earth emits gx: prefixes it never declares, and
    # ElementTree refuses the whole file over it. A refusal here would be a
    # probe that cannot probe the files most likely to need probing.
    print("\n  GEOMETRY TAGS")
    for tag in ("Polygon", "LinearRing", "LineString", "Point",
                "MultiGeometry", "Model", "gx:Track"):
        n = raw.count("<" + tag)
        if n:
            print(f"    <{tag}>{'':<{max(0, 14 - len(tag))}} {n:>6,}")
    if raw.count("<Polygon") == 0 and raw.count("<LineString") > 0:
        print("\n    NO POLYGONS. Every geometry in this file is a line.")
        print("    A line has no inside, so nothing here can be measured as")
        print("    land until the faces are recovered from the network.")

    blocks = re.split(r"<Placemark[^>]*>", raw)[1:]
    print(f"\n  placemarks       : {len(blocks):,}")

    named = 0
    pts_hist = Counter()
    layers = defaultdict(Counter)
    ents = Counter()
    by_layer_ent = defaultdict(Counter)

    for blk in blocks:
        if re.search(r"<name>(.*?)</name>", blk, re.S | re.I):
            named += 1
        lay = field(blk, "Layer") or "(no layer attribute)"
        ent = field(blk, "Entity") or "(no entity attribute)"
        ents[ent] += 1
        n = 0
        m = re.search(r"<coordinates>(.*?)</coordinates>", blk, re.S | re.I)
        if m:
            n = len([t for t in m.group(1).split() if "," in t])
        pts_hist[n] += 1
        layers[lay][n] += 1
        by_layer_ent[lay][ent] += 1

    # THE FINDING THAT COST THIS PROJECT THIRTEEN FAKE PARCELS.
    #
    # A placemark with no <name> is not a plot with a missing label. It is a
    # geometry that was never labelled, and any reference we attach to it is
    # one we made up. The old loader's fallback was PLOT-{index}, which reads
    # exactly like a plot number and is not one.
    print(f"  with a <name>    : {named:,}")
    if named == 0:
        print("\n    NOT ONE PLACEMARK IS NAMED. Any parcel_ref taken from")
        print("    this file would be invented. Whatever numbering ends up")
        print("    on these parcels is OURS and must say so in provenance.")
    elif named < len(blocks):
        print(f"    {len(blocks) - named:,} placemarks have no name. A "
              f"positional fallback")
        print("    (PLOT-1, PLOT-2 ...) would read like a plot number and "
              "would not be one.")

    print("\n  POINTS PER PLACEMARK")
    print("    points  count   what that can be")
    for n in sorted(pts_hist):
        c = pts_hist[n]
        if n == 0:
            what = "no coordinates at all"
        elif n == 1:
            what = "a single point"
        elif n == 2:
            what = "a LINE SEGMENT. Cannot be a parcel."
        elif n <= 4:
            what = "a short polyline or a triangle"
        else:
            what = "a ring or a long boundary line. Could be a parcel."
        print(f"    {n:>6}  {c:>6,}   {what}")

    seg = pts_hist[2]
    if seg and seg > len(blocks) * 0.5:
        print(f"\n    {seg:,} of {len(blocks):,} placemarks are two-point "
              f"segments.")
        print("    THIS IS A CAD DRAWING EXPORTED TO KML, not a parcel file.")
        print("    The plots are the faces the segments enclose. A loader "
              "that")
        print("    needs 3+ points will silently keep only the stragglers.")
        print("\n    Next:  python 04_polygonize_cad.py "
              f"\"{Path(a.path).name}\" --dry-run")

    print("\n  ENTITY TYPES (from the DXF attributes in the description)")
    for e, c in ents.most_common():
        print(f"    {e:<26} {c:>6,}")

    print("\n  CAD LAYERS")
    print("    every layer is a drafting decision, not a fact about the "
          "ground.")
    print("    A plot's frontage is often drawn on the road layer.")
    for lay, hist in sorted(layers.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(hist.values())
        segs = hist[2]
        rings = sum(c for n, c in hist.items() if n >= 5)
        print(f"    {lay:<26} {tot:>6,}  ({segs:,} segments, "
              f"{rings:,} with 5+ points)")
        if a.layers:
            for e, c in by_layer_ent[lay].most_common():
                print(f"        {e:<22} {c:>6,}")

    print("=" * 74)


if __name__ == "__main__":
    main()
