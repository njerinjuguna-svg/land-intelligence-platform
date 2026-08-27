r"""
============================================================================
INSPECT SAMPLE PARCELS - read before loading, decide the CRS by measurement
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHAT THIS IS FOR
  Two client files landed in 05_enrichment/sample_parcels:

    THIKA ALL.csv   1,715 rows of  id, northing, easting
    OAK GROVE.kmz   zipped KML

  Nothing is loaded until we know what they contain and, above all, WHICH
  COORDINATE REFERENCE SYSTEM the CSV is in. This script reports; it writes
  nothing to the database.

THE CRS QUESTION, AND WHY IT IS THE WHOLE BALL GAME
  The CSV coordinates look like UTM zone 37S:

      northing ~9,882,500   (southern hemisphere, 10,000,000 minus offset)
      easting    ~276,000   (west of zone 37's central meridian at 39 E)

  Which puts them around 37.07 E, 1.04 S - Thika. Good. But UTM zone 37S
  exists in two datums that matter here:

      EPSG:21037  Arc 1960 / UTM zone 37S   <- Survey of Kenya's datum,
                                               what cadastral surveys use
      EPSG:32737  WGS 84  / UTM zone 37S   <- what GPS and web maps use

  **They differ by roughly 150-200 metres in Kenya.** On a national rainfall
  grid that is nothing. On an eighth-acre plot it is a different plot.

  This project has already lost two runs to an assumed CRS: etl_17, where
  iSDA was served as a LOCAL_CS that PROJ could not use, and etl_22, where
  SoilGrids was assumed to be Homolosine and is actually EPSG:4326. Lesson 10
  was written after the first and ignored before the second.

  SO WE MEASURE IT. KML is defined by its specification to be WGS84 longitude
  and latitude - no ambiguity, nothing to assume. If the KMZ covers the same
  ground as the CSV, then transforming the CSV under each candidate datum and
  comparing against the KML settles it: the correct datum lands on the
  polygons, the wrong one lands ~200 m away.

  That is a test that can only pass for one reason, which is the kind this
  project prefers over "do these numbers look sensible".

How to run (from 05_enrichment, venv active):
  python 02_inspect_sample_parcels.py
============================================================================
"""

import os
import sys
import csv
import math
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

try:
    from pyproj import Transformer
except ImportError:
    sys.exit("ERROR: pyproj missing. With the venv active: pip install pyproj")

BASE = Path(__file__).resolve().parent
SAMPLES = BASE / "sample_parcels"

CANDIDATES = {
    "EPSG:21037": "Arc 1960 / UTM 37S  (Survey of Kenya cadastral datum)",
    "EPSG:32737": "WGS 84 / UTM 37S    (GPS / web mapping)",
    "EPSG:21036": "Arc 1960 / UTM 36S  (western Kenya - wrong zone here)",
}


def read_csv_points(path):
    """id, northing, easting -> [(id, northing, easting)].

    COLUMN ORDER IS NORTHING THEN EASTING, which is the opposite of the
    x,y most software expects. Established by magnitude, not by assumption:
    a value near 9,880,000 can only be a southern-hemisphere northing, and one
    near 276,000 can only be an easting. Getting this backwards would place
    the parcels in the Indian Ocean.
    """
    pts = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            try:
                a, b = float(row[1]), float(row[2])
            except ValueError:
                continue          # header or junk line
            north, east = (a, b) if a > b else (b, a)
            pts.append((row[0].strip(), north, east))
    return pts


def read_kmz(path):
    """-> (list of (name, [(lon, lat), ...]), raw placemark count)."""
    polys = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not names:
            return [], 0
        raw = z.read(names[0]).decode("utf-8", "ignore")
    # Google Earth KML routinely uses gx: and other prefixes WITHOUT declaring
    # them, and ElementTree rejects that with "unbound prefix". Declare the
    # usual suspects rather than fighting the parser; fall back to pulling
    # coordinates out textually if it is malformed beyond that.
    import re
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raw2 = re.sub(r"<kml([^>]*)>",
                      '<kml\\1 xmlns:gx="http://www.google.com/kml/ext/2.2" '
                      'xmlns:atom="http://www.w3.org/2005/Atom">',
                      raw, count=1)
        try:
            root = ET.fromstring(raw2)
            print("   (undeclared namespace prefixes repaired)")
        except ET.ParseError:
            rings = []
            for m in re.finditer(r"<coordinates>(.*?)</coordinates>",
                                 raw, re.S | re.I):
                ring = []
                for tok in m.group(1).split():
                    bits = tok.split(",")
                    if len(bits) >= 2:
                        try:
                            ring.append((float(bits[0]), float(bits[1])))
                        except ValueError:
                            pass
                if len(ring) >= 3:
                    rings.append((f"ring_{len(rings) + 1}", ring))
            print("   (KML malformed; coordinates extracted textually)")
            return rings, len(rings)
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    marks = root.findall(".//k:Placemark", ns) or root.findall(".//Placemark")
    for pm in marks:
        nm = pm.find("k:name", ns)
        nm = nm.text.strip() if nm is not None and nm.text else "(unnamed)"
        for tag in (".//k:coordinates", ".//coordinates"):
            node = pm.find(tag, ns) if tag.startswith(".//k:") else pm.find(tag)
            if node is None or not node.text:
                continue
            ring = []
            for tok in node.text.split():
                bits = tok.split(",")
                if len(bits) >= 2:
                    ring.append((float(bits[0]), float(bits[1])))
            if len(ring) >= 3:
                polys.append((nm, ring))
            break
    return polys, len(marks)


def main():
    csv_path = SAMPLES / "THIKA ALL.csv"
    kmz_path = SAMPLES / "OAK GROVE.kmz"

    print("=" * 74)
    print("SAMPLE PARCEL INSPECTION - nothing is loaded, nothing is written")
    print("=" * 74)

    # ---- CSV -------------------------------------------------------------
    if not csv_path.exists():
        sys.exit(f"Not found: {csv_path}")
    pts = read_csv_points(csv_path)
    ns = [p[1] for p in pts]
    es = [p[2] for p in pts]
    print(f"\n1. {csv_path.name}")
    print(f"   {len(pts):,} points")
    print(f"   northing {min(ns):,.1f} .. {max(ns):,.1f}  "
          f"(span {max(ns)-min(ns):,.0f} m)")
    print(f"   easting  {min(es):,.1f} .. {max(es):,.1f}  "
          f"(span {max(es)-min(es):,.0f} m)")
    area_ha = (max(ns) - min(ns)) * (max(es) - min(es)) / 10_000
    print(f"   bounding box {area_ha:,.1f} ha ({area_ha*2.471:,.0f} acres)")
    print(f"   -> {len(pts)/(area_ha*2.471):.1f} points per acre. At 4 corners "
          f"per plot that is ~{len(pts)/4:.0f} plots, "
          f"~{area_ha*2.471/max(1,len(pts)/4):.2f} acres each.")
    print("   (An eighth-acre plot is the standard Kenyan subdivision unit.)")

    print("\n2. Where does it land under each candidate CRS?")
    for epsg, label in CANDIDATES.items():
        try:
            tr = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True)
            lon, lat = tr.transform(sum(es)/len(es), sum(ns)/len(ns))
            print(f"   {epsg}  {lat:9.5f}, {lon:9.5f}   {label}")
        except BaseException as exc:
            print(f"   {epsg}  FAILED: {type(exc).__name__}")
    print("   Thika town is about -1.0387, 37.0834. All candidates will look")
    print("   plausible at this zoom - THAT IS THE POINT. The datums differ by")
    print("   ~200 m, which does not show up as an obviously wrong answer.")

    # ---- KMZ -------------------------------------------------------------
    if not kmz_path.exists():
        print(f"\n3. {kmz_path.name} not found - cannot run the CRS test.")
        return
    polys, nmarks = read_kmz(kmz_path)
    print(f"\n3. {kmz_path.name}")
    print(f"   {nmarks} placemark(s), {len(polys)} with usable rings")
    if not polys:
        print("   No coordinates parsed. Rename to .zip, extract, and check "
              "the KML by hand.")
        return
    all_lon = [c[0] for _, r in polys for c in r]
    all_lat = [c[1] for _, r in polys for c in r]
    print(f"   longitude {min(all_lon):.5f} .. {max(all_lon):.5f}")
    print(f"   latitude  {min(all_lat):.5f} .. {max(all_lat):.5f}")
    print(f"   first few names: "
          f"{', '.join(n for n, _ in polys[:5])}")

    # ---- THE TEST --------------------------------------------------------
    # VERSION 2. The first version compared the CENTROID of 1,715 CSV points
    # against the CENTROID of 13 KML placemarks and returned an identical
    # 272 m for two datums that differ from each other by ~200 m. Identical
    # answers from different inputs means the test was not measuring the
    # datum: the KMZ covers 13 plots out of ~429, so the extent mismatch
    # swamped the signal.
    #
    # That is lesson 19 committed in the verification rather than the ETL -
    # a test that could not fail cleanly.
    #
    # THE TEST THAT CAN ONLY PASS FOR ONE REASON: a KML ring corner IS a
    # survey beacon. Under the correct datum every corner sits within a metre
    # or two of a CSV point. Under the wrong one, every corner is ~200 m from
    # the nearest one. Nothing about differing extents affects that - we ask
    # each corner about its OWN nearest neighbour, not about an average.
    print("\n4. THE CRS TEST - nearest survey point to each KML corner")
    print("   A KML ring corner should BE a survey beacon. The correct datum")
    print("   puts them on top of each other; the wrong one is ~200 m out.")
    print()

    corners = [c for _, ring in polys for c in ring]
    # thin very dense rings so the comparison stays quick
    if len(corners) > 400:
        corners = corners[::max(1, len(corners) // 400)]
    klat0 = sum(c[1] for c in corners) / len(corners)
    mlon = 111320.0 * math.cos(math.radians(klat0))
    mlat = 110574.0

    results = []
    for epsg, label in CANDIDATES.items():
        try:
            tr = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True)
            lons, lats = tr.transform([p[2] for p in pts], [p[1] for p in pts])
            px = np.asarray(lons) * mlon
            py = np.asarray(lats) * mlat
            best = []
            for clon, clat in corners:
                d = np.hypot(px - clon * mlon, py - clat * mlat)
                best.append(float(d.min()))
            best = np.asarray(best)
            med = float(np.median(best))
            within2 = 100.0 * float((best <= 2.0).sum()) / best.size
            results.append((med, epsg, label, within2))
            print(f"   {epsg}  median {med:9,.1f} m   "
                  f"{within2:5.1f}% of corners within 2 m   {label}")
        except BaseException as exc:
            print(f"   {epsg}  FAILED: {type(exc).__name__}: {exc}")

    if results:
        results.sort()
        med, best_epsg, label, within2 = results[0]
        runner = results[1][0] if len(results) > 1 else float("inf")
        print()
        if med <= 5.0 and runner > 50.0:
            print(f"   *** {best_epsg} IS THE CSV'S CRS ***")
            print(f"       {label}")
            print(f"       median corner-to-beacon {med:.1f} m, "
                  f"{within2:.1f}% within 2 m")
            print(f"       next best is {runner:,.0f} m - not a close call")
            print(f"\n   USE {best_epsg} IN THE LOADER.")
        elif med <= 5.0:
            print(f"   {best_epsg} fits ({med:.1f} m) but so does the runner-up")
            print(f"   ({runner:.1f} m). Two datums cannot both be right -")
            print(f"   something is wrong with this test, not the data.")
        else:
            print(f"   NO CANDIDATE FITS. Closest is {best_epsg} at a median "
                  f"{med:,.0f} m.")
            print("   Most likely the KMZ and the CSV cover DIFFERENT SITES -")
            print("   'THIKA ALL' and 'OAK GROVE' are different names, and the")
            print("   KMZ holds 13 plots against ~429 in the CSV.")
            print("   IF SO THIS TEST CANNOT SETTLE THE CRS. Ask the surveyor")
            print("   who produced the CSV. Do NOT guess: Arc 1960 and WGS 84")
            print("   differ by ~200 m here, which is wider than the plots.")

    print("\n" + "=" * 74)
    print("NOTHING WAS LOADED. Confirm the CRS above, then the loader can")
    print("build polygons and write them to land.parcels.")
    print("=" * 74)


if __name__ == "__main__":
    main()
