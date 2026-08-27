r"""
============================================================================
PARCEL GATE - what a client's upload must survive before it is enriched
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS IS A SEPARATE MODULE AND NOT MORE CODE IN THE LOADER

  `03_load_client_parcels.py` reads one KMZ. The product reads whatever a
  client sends: a shapefile, a DXF, a spreadsheet of corners, another KMZ.
  Every one of those paths must apply the SAME refusals, and a rule that has
  to be re-implemented per format is a rule that will differ per format.

  So the gate is a function over geometry, and every upload path calls it.

THE RULE THIS MODULE EXISTS TO CLOSE

  The verifier already FINDS bad parcels. It found that PLOT-1069 and
  PLOT-1070 are one polygon under two references, and that PLOT-950's slope
  diverges from its neighbours by a factor of five. Both were found AFTER
  enrichment, in a report nobody outside this project reads.

  That is the project's oldest recurring shape, stated in the checklist as
  E1/E8/E9: **a rule you have to remember is a reminder; a rule the code
  cannot proceed without is a control.** A defect caught after enrichment is
  a defect that already has a report, a score and a page on a client's
  website. It has to be caught at the door.

  The loader's own comment is the clearest example. On a polygon whose area
  changed by more than half under repair it prints:

      *** DO NOT QUOTE THIS AREA. Go back to the surveyor. ***

  and then loads it. Everything downstream then quotes it. That is a warning
  doing a control's job, and REJECT_ON_AMBIGUOUS_AREA below is the fix.

WHAT A GATE MAY DECIDE
  accept          load it as supplied
  downgrade       load it, but at a confidence the scorer will refuse (< 4),
                  so it is enriched and visible to us but never scored or sold
  reject          do not load it at all

  Downgrade is not a soft reject. It is for geometry we believe is REAL but
  no longer exactly what the surveyor drew - a repaired self-intersection.
  Reject is for geometry that is not a parcel, or that we cannot tell apart
  from another parcel, or that would make us quote a number we do not have.

EVERY FAILURE IS REPORTED, NOT THE FIRST
  A client sending 400 plots should get one list of everything wrong with the
  file, not one problem per round trip.
============================================================================
"""

from sqlalchemy import text

# 0.01 acres is about 40 m2. No Kenyan land parcel is 40 m2; anything smaller
# is a drawing artefact - a LineString placemark or a near-degenerate sliver.
MIN_PARCEL_ACRES = 0.01

# Above this, a "plot" in a residential scheme is almost certainly a BLOCK or
# a PHASE boundary that was drawn in the same file. OAK GROVE's own KMZ turned
# out to be 13 rings of ~24 acres each - phases, not plots. Not a reject:
# large parcels are real. It is a question the client must answer.
LARGE_PARCEL_ACRES = 50.0

# A self-intersecting ring has no single correct area; ST_MakeValid picks one
# reading of several. Under this much disagreement the repair is cosmetic and
# the parcel is loadable at reduced confidence. Over it, we do not know how
# big the plot is - and we SELL the size.
AMBIGUOUS_AREA_RATIO = 1.5

# Two parcels sharing more than a token sliver of ground are not neighbours,
# they are a conflict. Adjacent plots share a BOUNDARY, which has zero area,
# so anything meaningfully above zero is an overlap in substance.
MAX_OVERLAP_PCT = 1.0

# Kenya's bounding box, generously. A parcel outside it is not a parcel in
# the wrong place - it is a CRS that was read wrong, and the whole batch is
# suspect. Rule E1's shape: check the frame before believing the contents.
KENYA_BBOX = (33.9, -4.72, 41.92, 5.03)


class Verdict:
    ACCEPT = "accept"
    DOWNGRADE = "downgrade"
    REJECT = "reject"


def _f(v, d=0.0):
    return float(v) if v is not None else d


def check_geometry(conn, wkt):
    """One parcel, on its own. -> (verdict, confidence, [findings])

    Confidence is only meaningful when the verdict is accept or downgrade.
    """
    r = conn.execute(text("""
        SELECT ST_IsValid(g),
               ST_IsValidReason(g),
               round((ST_Area(g::geography) / 4046.86)::numeric, 4),
               ST_NPoints(g),
               round((ST_Area(ST_MakeValid(g)::geography) / 4046.86)::numeric, 4),
               ST_Within(ST_Envelope(g),
                         ST_MakeEnvelope(:x0, :y0, :x1, :y1, 4326)),
               GeometryType(ST_MakeValid(g))
          FROM (SELECT ST_GeomFromText(:w, 4326) AS g) t
    """), {"w": wkt, "x0": KENYA_BBOX[0], "y0": KENYA_BBOX[1],
           "x1": KENYA_BBOX[2], "y1": KENYA_BBOX[3]}).one()

    valid, reason, raw_acres, npts, fixed_acres, in_kenya, gtype = r
    raw_acres, fixed_acres = _f(raw_acres), _f(fixed_acres)
    acres = max(raw_acres, fixed_acres)
    out = []

    if not in_kenya:
        return Verdict.REJECT, None, [
            ("outside Kenya",
             "The polygon falls outside Kenya's bounding box. This is almost "
             "never a parcel in the wrong place - it is a coordinate "
             "reference system read wrongly, which means EVERY parcel in "
             "this file is in the wrong place by the same amount. Confirm "
             "the CRS with whoever produced the file before reloading any "
             "of it.")]

    if gtype not in ("POLYGON", "MULTIPOLYGON"):
        return Verdict.REJECT, None, [
            ("not an area",
             f"This is a {gtype}, not a polygon. A line or a point has no "
             f"inside, so there is nothing to measure the land against.")]

    if acres < MIN_PARCEL_ACRES:
        return Verdict.REJECT, None, [
            ("degenerate",
             f"{npts} points enclosing {acres:.5f} acres. Below "
             f"{MIN_PARCEL_ACRES} acres (about 40 m2) this is a boundary line "
             f"or a drawing sliver, not a parcel.")]

    if not valid:
        ratio = (fixed_acres / raw_acres) if raw_acres > 0 else float("inf")
        if raw_acres <= 0 or ratio > AMBIGUOUS_AREA_RATIO \
                or ratio < 1.0 / AMBIGUOUS_AREA_RATIO:
            # THE WARNING THAT BECAME A CONTROL. The loader used to print
            # "DO NOT QUOTE THIS AREA" and load the parcel anyway, after
            # which every report quoted it.
            return Verdict.REJECT, None, [
                ("area is ambiguous",
                 f"The ring self-intersects ({reason}). Repairing it changes "
                 f"the area from {raw_acres:.2f} to {fixed_acres:.2f} acres, "
                 f"and a self-intersecting ring has NO single correct area - "
                 f"the repair picked one reading of several. We sell the "
                 f"size of the land, so we cannot load a parcel whose size "
                 f"we would be guessing. Ask for the mutation drawing.")]
        out.append(
            ("repaired",
             f"The ring self-intersected ({reason}) and was repaired. Area "
             f"moved {raw_acres:.2f} -> {fixed_acres:.2f} acres, within "
             f"tolerance. Loaded at reduced confidence: the geometry we hold "
             f"is no longer exactly what the surveyor drew, so this parcel "
             f"is enriched but will not be scored."))
        return Verdict.DOWNGRADE, 3, out

    if acres > LARGE_PARCEL_ACRES:
        out.append(
            ("unusually large",
             f"{acres:.1f} acres. Large parcels are real, but in a plotted "
             f"scheme a shape this size is usually a BLOCK or PHASE boundary "
             f"drawn in the same file rather than a sellable plot. Confirm "
             f"with the client which it is."))

    return Verdict.ACCEPT, 4, out


def check_against_others(conn, wkt, company_id, exclude_ref=None):
    """Does this ground already belong to another parcel? -> [findings]

    THE FAILURE THIS PREVENTS IS THE WORST ONE IN THE PRODUCT.
    Two references over one polygon is either a drafting duplicate or the
    same ground sold twice, and we cannot tell which from the geometry. Both
    demand a human. Neither may be enriched into two confident listings.

    Checks the DATABASE, so it catches a plot that collides with one loaded
    last month as well as one in the same file.
    """
    rows = conn.execute(text("""
        SELECT p.parcel_ref,
               ST_Equals(p.geom, ST_MakeValid(ST_GeomFromText(:w, 4326))),
               round((100 * ST_Area(ST_Intersection(
                        p.geom, ST_MakeValid(ST_GeomFromText(:w, 4326)))
                        ::geography)
                      / NULLIF(ST_Area(p.geom::geography), 0))::numeric, 2)
          FROM land.parcels p
         WHERE p.company_id = :cid
           AND p.status = 'active'
           AND (:ex IS NULL OR p.parcel_ref <> :ex)
           AND ST_Intersects(p.geom,
                             ST_MakeValid(ST_GeomFromText(:w, 4326)))
    """), {"w": wkt, "cid": company_id, "ex": exclude_ref}).all()

    out = []
    for ref, identical, pct in rows:
        pct = _f(pct)
        if identical:
            out.append(
                ("identical to " + str(ref),
                 f"This polygon is EXACTLY the same ground as {ref}. Either "
                 f"the file contains a drafting duplicate, or the same land "
                 f"has been allocated twice. The geometry cannot tell those "
                 f"apart and the difference matters enormously, so neither "
                 f"parcel is loaded until the client says which it is."))
        elif pct > MAX_OVERLAP_PCT:
            out.append(
                ("overlaps " + str(ref) + f" by {pct:.1f}%",
                 f"This polygon covers {pct:.1f}% of {ref}. Neighbouring "
                 f"plots share a BOUNDARY, which has no area - a real "
                 f"overlap means one of the two drawings is wrong, and a "
                 f"buyer could be shown analysis for ground that belongs to "
                 f"someone else."))
    return out


def canonical_key(conn, wkt):
    """A hash that is equal for two rings describing the SAME ground.

    WHY NOT COMPARE THE WKT STRINGS. The loader's first version did, and it
    would have missed the real case: the same plot drawn twice in Google
    Earth starts at a different corner or winds the other way, so the two
    strings differ while ST_Equals returns true. String equality catches only
    a copy-paste.

    ST_Normalize puts a geometry into a canonical form - rings ordered, start
    point fixed - so identical ground hashes identically. One query per
    parcel and a group-by in Python, rather than comparing every parcel with
    every other, which on a 400-plot file would be 80,000 comparisons.
    """
    return conn.execute(text("""
        SELECT md5(ST_AsBinary(ST_Normalize(
                   ST_MakeValid(ST_GeomFromText(:w, 4326)))))
    """), {"w": wkt}).scalar()


def gate(conn, wkt, company_id, ref=None):
    """The whole door. -> (verdict, confidence, [(headline, explanation)])"""
    verdict, conf, findings = check_geometry(conn, wkt)
    if verdict == Verdict.REJECT:
        return verdict, None, findings

    clashes = check_against_others(conn, wkt, company_id, exclude_ref=ref)
    if clashes:
        # A collision outranks anything geometry alone decided. A perfectly
        # valid polygon over someone else's plot is still not loadable.
        return Verdict.REJECT, None, findings + clashes

    return verdict, conf, findings


def report(ref, verdict, findings, indent="   "):
    """Print a gate result the way a client's developer needs to read it."""
    mark = {"accept": "OK      ", "downgrade": "LIMITED ",
            "reject": "REJECTED"}[verdict]
    print(f"{indent}{mark} {ref}")
    for headline, why in findings:
        print(f"{indent}         - {headline}")
        for line in _wrap(why, 66):
            print(f"{indent}           {line}")


def _wrap(s, w):
    words, line, out = s.split(), "", []
    for word in words:
        if len(line) + len(word) + 1 > w:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out
