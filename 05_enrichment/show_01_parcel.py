r"""
============================================================================
SHOW ONE COMPLETE PARCEL, EXACTLY AS THE DATABASE HOLDS IT
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS EXISTS

  E14. A green verification does not mean the answers are right. Every one of
  the four landmark defects in session 11 passed verification: the query was
  right, the join was right, the distance was right, and the column still
  answered the question NEXT to the one a buyer was asking. A disused airstrip
  is a real airport at a correctly computed distance. A village is a real
  place. Nothing in an assertion suite notices that.

  What notices is a person reading one whole parcel and asking, field by
  field, "would I say that to a buyer standing on this plot?" That has been a
  rule with no tool behind it, which makes it a reminder rather than a
  control (section 6). This is the tool.

  It asserts nothing and it can fail nothing. It prints. Reading it is the
  check, and the reading is not optional.

WHAT IT PRINTS

  Every column of the active enrichment row for one active parcel, with the
  source and confidence attached to each field where field_sources carries
  them, then the suitability score and its breakdown.

  NULLs are printed as NULL and never as blank. A blank reads as zero, and a
  blank and a zero are opposite claims - where field_sources records the
  radius that was searched, the NULL is printed with it, so "no school within
  25 km" stays distinguishable from "we did not look".

USAGE

  python show_01_parcel.py                 # first active parcel by ref
  python show_01_parcel.py PLOT-1071       # one named parcel
  python show_01_parcel.py --list          # what is available to look at
============================================================================
"""
import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
ENV_DIR = BASE.parent / "03_etl"

# A4/B4: values and pictures leave this build, never geometry. Nothing in
# parcel_intelligence holds geometry today, and this refuses to be the place
# that starts.
GEOM_HINT = ("geom", "geometry", "wkb", "wkt", "boundary")


def is_geometry(col, val):
    if any(h in col.lower() for h in GEOM_HINT):
        return True
    if isinstance(val, (bytes, bytearray, memoryview)):
        return True
    if isinstance(val, str) and val[:60].upper().lstrip().startswith(
            ("POLYGON", "MULTIPOLYGON", "POINT", "LINESTRING", "SRID=",
             "0103", "0106")):
        return True
    return False


def as_dict(v):
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except (ValueError, TypeError):
            return {}
    return v if isinstance(v, dict) else {}


def main():
    args = [a for a in sys.argv[1:]]
    want_list = "--list" in args
    ref = next((a for a in args if not a.startswith("-")), None)

    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")

    with engine.connect() as conn:
        avail = conn.execute(text("""
            SELECT p.parcel_ref, p.project_name, p.listing_status,
                   (i.parcel_id IS NOT NULL) AS enriched,
                   (s.parcel_id IS NOT NULL) AS scored
              FROM land.parcels p
              LEFT JOIN analytics.parcel_intelligence i
                     ON i.parcel_id = p.parcel_id AND i.status = 'active'
              LEFT JOIN analytics.suitability_scores s
                     ON s.parcel_id = p.parcel_id AND s.status = 'active'
             WHERE p.status = 'active'
             ORDER BY p.parcel_ref
        """)).mappings().all()

        if want_list or not avail:
            print(f"\n{len(avail)} active parcel(s)\n")
            for a in avail:
                print(f"  {a['parcel_ref']:<24} "
                      f"{(a['project_name'] or '-'):<20} "
                      f"{'enriched' if a['enriched'] else 'NOT enriched':<13} "
                      f"{'scored' if a['scored'] else 'not scored'}")
            if not avail:
                sys.exit("\nNo active parcels. Run 03_load_client_parcels.py")
            return

        if ref is None:
            ref = next((a["parcel_ref"] for a in avail if a["enriched"]), None)
            if ref is None:
                sys.exit("No active parcel has enrichment yet. Run "
                         "enrich_01_engine.py first.")

        row = conn.execute(text("""
            SELECT p.parcel_ref, p.project_name, p.listing_status,
                   p.confidence AS parcel_confidence, p.version AS parcel_ver,
                   round(ST_Area(p.geom::geography)) AS area_sqm_calc, i.*
              FROM analytics.parcel_intelligence i
              JOIN land.parcels p ON p.parcel_id = i.parcel_id
             WHERE p.parcel_ref = :r
               AND i.status = 'active' AND p.status = 'active'
        """), {"r": ref}).mappings().all()

        if not row:
            sys.exit(f"No active enrichment for '{ref}'. "
                     f"Try:  python show_01_parcel.py --list")
        if len(row) > 1:
            sys.exit(f"ABORT: {len(row)} active enrichment rows for '{ref}'. "
                     f"Two versions of the same parcel are live at once.")
        r = dict(row[0])

        score = conn.execute(text("""
            SELECT s.* FROM analytics.suitability_scores s
              JOIN land.parcels p ON p.parcel_id = s.parcel_id
             WHERE p.parcel_ref = :r
               AND s.status = 'active' AND p.status = 'active'
        """), {"r": ref}).mappings().first()

    src = as_dict(r.get("field_sources"))
    conf = as_dict(r.get("field_confidence"))

    print("=" * 76)
    print(f"PARCEL {r['parcel_ref']}   "
          f"project: {r.get('project_name') or '-'}   "
          f"listing: {r.get('listing_status') or '-'}")
    print(f"computed area: {r.get('area_sqm_calc')} m2   "
          f"boundary confidence: {r.get('parcel_confidence')}   "
          f"parcel version: {r.get('parcel_ver')}")
    print("=" * 76)
    print("\nRead every line. The question is not whether the number is "
          "correct.\nIt is whether it answers what a buyer standing on this "
          "plot is asking.\n")

    skip = {"parcel_ref", "project_name", "listing_status", "parcel_confidence",
            "parcel_ver", "area_sqm_calc", "field_sources", "field_confidence"}
    nulls = []
    for col in r:
        if col in skip:
            continue
        val = r[col]
        if is_geometry(col, val):
            print(f"  {col:<34} [geometry withheld - A4/B4]")
            continue
        note = []
        s = src.get(col)
        if s is not None:
            note.append(json.dumps(s) if isinstance(s, (dict, list)) else str(s))
        c = conf.get(col)
        if c is not None:
            note.append(f"conf {c}")
        tail = f"   <- {' | '.join(note)}" if note else ""
        if val is None:
            nulls.append(col)
            print(f"  {col:<34} NULL{tail}")
        else:
            shown = json.dumps(val, default=str) if isinstance(
                val, (dict, list)) else str(val)
            if len(shown) > 200:
                shown = shown[:200] + " ..."
            print(f"  {col:<34} {shown}{tail}")

    if nulls:
        print(f"\n  {len(nulls)} field(s) NULL. A NULL is only honest if it "
              f"carries what was\n  searched - check each one above says so, "
              f"or the report will print a\n  blank where a buyer reads a "
              f"zero.")

    print("\n" + "=" * 76)
    if not score:
        print("NO ACTIVE SCORE for this parcel.")
        print("If that is a blocked parcel, that is blocking working. If it "
              "is not,\nscore_01_suitability.py has not been run since the "
              "last enrichment.")
    else:
        s = dict(score)
        print("SUITABILITY")
        for k in ("overall_score", "residential_score", "agricultural_score",
                  "commercial_score", "investment_score", "confidence",
                  "blocked", "blocked_reason", "model_version", "version"):
            if k in s:
                print(f"  {k:<34} "
                      f"{'NULL' if s[k] is None else s[k]}")
        bd = as_dict(s.get("score_breakdown"))
        if bd:
            print("\n  breakdown")
            print("  " + json.dumps(bd, indent=2, default=str
                                    ).replace("\n", "\n  ")[:4000])
    print("=" * 76)


if __name__ == "__main__":
    main()
