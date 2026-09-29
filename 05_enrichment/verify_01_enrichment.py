r"""
============================================================================
VERIFY THE ENRICHMENT ENGINE
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHAT THIS CHECKS, AND WHY EACH CHECK EXISTS

  A. LANDMARK EXPECTATIONS. Twelve parcels at places six sessions of testing
     already validated. The expectations were written into
     land.parcels.test_expectation BEFORE this engine existed, so the engine
     cannot be judged against its own output (rule E4).

     They are restated here as EXECUTABLE assertions. Prose in a column is a
     reminder; an assertion that fails a run is a control.

  B. DUPLICATE GEOMETRY. Found on the first real client file: PLOT-1069 and
     PLOT-1070 are ST_Equals - two plot numbers, one polygon.

     THIS IS A PRODUCT FEATURE, NOT A DATA-QUALITY NUISANCE. In a Kenyan
     subdivision, two references sharing one geometry is either a drafting
     duplicate or THE SAME GROUND ALLOCATED TWICE. Selling one plot to two
     buyers is a known failure in this market, and a platform that enriches
     both silently would bill for the error rather than catch it.

  C. NEIGHBOUR DIVERGENCE. PLOT-950 arrived self-intersecting. ST_MakeValid
     repaired it and the area went 2.10 -> 8.50 acres. The readings then
     showed what that really cost: slope 14.38 degrees where every other plot
     in the scheme reads 1.35-4.63, and very_high flood on 31% of its area
     where its neighbours are 100% very_low.

     The repair did not just change the acreage. IT CHANGED WHICH GROUND WAS
     MEASURED - the polygon spread into a valley that is not part of the plot.
     A parcel whose readings diverge sharply from its immediate neighbours is
     the signature of that, and it is worth catching automatically.

  D. FIELD COVERAGE. Which columns came back NULL, and for how many parcels.
     A silent NULL is indistinguishable from a zero in a report.

  KNOWN GAPS ARE REPORTED SEPARATELY FROM FAILURES. The Athi-Kapiti black
  cotton case is documented as unresolvable with the layers we hold. It must
  not appear as a pass - that would launder a limitation into a success - and
  it must not appear as a failure either, because nothing is broken.

REQUIRES a real (non-dry) engine run first:
  python enrich_01_engine.py

How to run:
  python verify_01_enrichment.py
============================================================================
"""

import os
import sys
import json
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
ENV_DIR = BASE.parent / "03_etl"

# ---------------------------------------------------------------------------
# A. THE ASSERTIONS. Named before the engine existed - see 01_create_test_
#    parcels.sql, whose test_expectation column is the prose original.
#    (field, operator, value, why it matters)
# ---------------------------------------------------------------------------
EXPECT = {
    "TEST-KAREN-01": [
        ("flood_risk_class", "==", "very_low",
         "THE COMMERCIALLY CRITICAL ONE. Prime Nairobi residential. A false "
         "flood warning here devalues expensive land on a modelled number."),
        ("black_cotton_risk", "==", "none",
         "Nitisols - deep red coffee soil. Clay-rich but stable, NOT black "
         "cotton."),
    ],
    "TEST-ABERDARES-01": [
        ("flood_risk_class", "==", "very_low",
         "Steep slopes shed water, they do not collect it."),
        ("slope_mean_pct", ">", 4.0,
         "Cross-check: if slope is low here the coordinate is wrong, not the "
         "flood layer."),
    ],
    "TEST-GARISSA-01": [
        ("flood_risk_class", "==", "very_high",
         "25% of this parcel is very_high. The landmark that withdrew run 57."),
        ("__cell_differs", "==", True,
         "RULE D2: the town sits on a terrace, so the parcel's dominant class "
         "and its worst material class MUST disagree. If they agree, the "
         "footprint logic is not running."),
    ],
    "TEST-KANO-01": [
        ("flood_risk_class", "in", ("high", "very_high"),
         "Straightforward floodplain, no terrace complication - the easy "
         "control."),
        ("black_cotton_risk", "==", "likely", "Vertisols on the Kano plains."),
    ],
    "TEST-TANADELTA-01": [
        ("flood_risk_class", "==", "very_high", "Tana delta floodplain."),
        ("__breakdown_classes", ">=", 4,
         "50 acres must show a MIX of classes. A single class across 450 m "
         "means footprint sampling is not working."),
    ],
    "TEST-BUDALANGI-01": [
        ("flood_risk_class", "==", "moderate",
         "Floods by DIKE FAILURE, which HAND structurally cannot see. "
         "Moderate is the honest reading of the terrain."),
        ("dist_permanent_water_m", "<", 1000.0,
         "RULE D3: this is what carries the real warning here, not the hazard "
         "class."),
    ],
    "TEST-KERICHO-01": [
        ("rainfall_normal_mm_yr", ">", 1500.0, "Wet highland."),
        ("__rain_single_cell", "==", True,
         "A 400 m parcel sits inside ONE 5 km CHIRPS cell, so min and max "
         "MUST equal the mean. A spread would be invented."),
    ],
    "TEST-LODWAR-01": [
        ("rainfall_normal_mm_yr", "<", 400.0, "Arid."),
        ("rainfall_driest_year_pct", "<", 80.0, "Real drought exposure."),
    ],
    "TEST-KITENGELA-01": [
        ("black_cotton_risk", "==", "likely", "Vertisols, flat, Clay texture."),
        ("flood_risk_class", "==", "very_low", "Not a floodplain."),
    ],
    "TEST-RUAI-01": [
        ("black_cotton_risk", "==", "likely", "Vertisols on the Athi fringe."),
        ("flood_risk_class", "==", "very_low", "Not a floodplain."),
    ],
    "TEST-KAKAMEGA-01": [
        ("flood_risk_class", "==", "very_low", "Forest on a rise."),
        ("rainfall_normal_mm_yr", ">", 1800.0, "Wettest part of Kenya."),
        # These three are the prose expectation in 01_create_test_parcels.sql
        # made executable, WORD FOR WORD: "EXPECT landcover_class_worldcover
        # = Tree cover and a HIGH ndvi_mean. landcover_composition should be
        # dominated by one class - this is the cleanest composition test in
        # the set." Written before the layer existed; not adjusted to it.
        ("landcover_class_worldcover", "==", "Tree cover",
         "Kakamega Forest read 96% Tree cover in verify_19. The least "
         "ambiguous land cover in Kenya - if this is not Tree cover, the "
         "coordinate is wrong, not the layer."),
        ("ndvi_mean", ">", 0.6,
         "Closed-canopy equatorial rainforest. 0.6 is a floor, not a target: "
         "healthy forest sits well above it, so a pass near 0.6 is itself "
         "worth a look."),
        ("__dominant_share", ">=", 80.0,
         "The composition test. One class should dominate this parcel - a "
         "flat spread here means the polygon is straddling the forest edge "
         "or the sampling is not clipping to the footprint."),
    ],
}

# ---------------------------------------------------------------------------
# ORDERINGS. (field, must_be_higher, must_be_lower, why)
#
# An absolute threshold on a modelled layer is a guess wearing a decimal
# point - "NDVI above 0.5" depends on the year, the sensor and the
# compositing, and when it fails you cannot tell whether the engine broke or
# the number was always wrong.
#
# WHAT CANNOT BE ARGUED WITH IS THE ORDER. Rainforest is greener than desert.
# A city is more built than a delta. If an ordering INVERTS, something is
# wrong with the layer, the coordinate or the sampling - and nothing had to be
# invented to find out. An ordering also fails loudly when a layer returns a
# constant, which a one-sided threshold quietly passes.
#
# This is also rule D9 made executable: "more than" is the kind of statement
# this product is entitled to make, so these are the ones that must hold.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# LANDMARK IDENTITIES. Added with the landmarks layer, and a different KIND of
# assertion from everything above: those check a modelled number against a
# documented expectation, these check a NAME against a fact about Kenya that
# no model produced. If Ruai's nearest airport stops being JKIA, the join is
# wrong or the parcel moved - nothing else can cause it.
# ---------------------------------------------------------------------------
# EVERY NULL MUST BE READABLE.
#
# The first version of this check listed the fields it expected to find
# unexplained and passed if all of them carried a note. It passed - and
# temp_mean_c and solar_kwh_m2_day were sitting NULL with nothing attached,
# because they were not on the list. A check that only checks what its author
# remembered is the same failure as a rule that only lives in a comment.
#
# So it is inverted: scan EVERY null column on every parcel, and demand that
# each one is explained. A column added next session fails loudly until
# somebody decides what its NULL means.
#
# There are exactly two honest kinds of NULL:
#
#   not_sourced      - we hold no layer at all. Stamped by the engine.
#   searched_nothing - we searched a stated radius and found none.
#
# THE SECOND IS NOT IMPLEMENTED. `src[...]` is written inside the hit branch
# of every layer, so a genuine "nothing within 25 km" writes nothing at all -
# despite the SEARCH_M docstring promising it does. That is why no report can
# yet say "no school within 25 km" instead of leaving a blank.
#
# The columns below are that debt, named. They are NOT permission: when the
# radius stamping lands, this list empties and the check tightens by itself.
SEARCHED_NOTHING_DEBT = {
    "dist_bus_stop_m", "dist_railway_station_m", "dist_market_m",
    "dist_police_m", "dist_major_road_m", "nearest_major_road_name",
    "dist_town_centre_m", "nearest_town_name", "nearest_town_type",
    "dist_airport_m", "nearest_airport_name",
    "dist_intl_airport_m", "nearest_intl_airport_name",
    "nearest_railway_station_name",
    "dist_river_m", "dist_water_point_m", "dist_permanent_water_m",
    "dist_primary_school_m", "dist_secondary_school_m",
    "dist_hospital_m", "dist_clinic_m", "dist_tower_m",
    "in_protected_area", "in_riparian_buffer",
    "coverage_2g_pct", "coverage_4g_pct", "coverage_admin_level",
    "coverage_admin_name", "coverage_vintage",
    "black_cotton_risk", "flood_nearby_pct",
}

# Bookkeeping columns. They are not claims about the parcel and a NULL in one
# says nothing to a buyer.
NOT_A_CLAIM = {
    "intel_id", "parcel_id", "run_id", "version", "status", "computed_at",
    "created_at", "updated_at", "engine_version", "field_sources",
    "field_confidence", "parcel_ref", "project_name", "test_expectation",
}

LANDMARK_IDENTITY = {
    "TEST-RUAI-01": ("nearest_airport_name",
                     "Jomo Kenyatta International Airport",
                     "Ruai sits east of Nairobi; JKIA is the obvious one."),
    # Was PLOT-457, which turned out to be a CAD fragment (array position,
    # not a plot) and was retired when Oak Grove was re-polygonized in
    # session 14. OG-001 is a real recovered plot on the same ground.
    "OG-001": ("nearest_intl_airport_name",
                 "Jomo Kenyatta International Airport",
                 "OAK GROVE is at Juja. Every plot in the scheme had "
                 "nearest_airport_name = GSU Airstrip, which is operational, "
                 "correctly measured and not somewhere anyone flies from. "
                 "This column is the repair, so this parcel is where it is "
                 "checked."),
    "TEST-KAREN-01": ("nearest_airport_name", "Wilson Airport",
                      "Karen's nearest is Wilson, NOT JKIA - and the two are "
                      "on opposite sides of the city, so confusing them would "
                      "mean the nearest-neighbour search is broken."),
    "TEST-LODWAR-01": ("nearest_airport_name", "Lodwar Airport",
                       "The parcel is in Lodwar town; 245 m is right."),
    "TEST-GARISSA-01": ("nearest_town_name", "Garissa",
                        "The parcel is in Garissa. If the nearest town is "
                        "somewhere else, the town filter is wrong."),
    "TEST-KERICHO-01": ("nearest_town_name", "Kericho",
                        "Same, and dist_town_centre_m is 0 - the parcel is "
                        "inside the town it names."),
}

# NAMES THAT MUST NEVER REACH A BUYER.
#
# TEST-TANADELTA-01 came back with nearest_airport_name = "Shekiko Airport
# (disused)". The distance was right and the join was right; the ANSWER was
# still wrong, because a disused airstrip is not an airport anyone can fly
# into, and putting it on a listing page as "your nearest airport" is a false
# promise made in OSM's own words.
#
# The engine cannot tell a defunct facility from a live one by geometry. The
# name says it outright, so the name is what is checked.
DEFUNCT_WORDS = ("disused", "abandoned", "former", "closed", "ruins",
                 "ruined", "derelict", "proposed", "under construction")
NAME_FIELDS = ["nearest_airport_name", "nearest_intl_airport_name",
               "nearest_town_name",
               "nearest_major_road_name", "nearest_railway_station_name"]

# PAIRS THAT ARE ATOMIC. A landmark distance with no name is not a partial
# answer, it is a broken one - "12 km from an airport" implies we know which.
LANDMARK_PAIRS = [
    ("dist_town_centre_m", "nearest_town_name"),
    ("dist_airport_m", "nearest_airport_name"),
    ("dist_intl_airport_m", "nearest_intl_airport_name"),
    ("dist_major_road_m", "nearest_major_road_name"),
    ("dist_railway_station_m", "nearest_railway_station_name"),
]

ORDERINGS = [
    ("ndvi_mean", "TEST-KAKAMEGA-01", "TEST-LODWAR-01",
     "Kakamega rainforest against the Turkana desert. The widest true gap in "
     "the set. If this inverts, NDVI is being read at the wrong scale or the "
     "wrong sign."),
    ("ndvi_mean", "TEST-KERICHO-01", "TEST-GARISSA-01",
     "Tea highlands against semi-arid Garissa. A second, narrower pair - the "
     "Kakamega/Lodwar gap is so wide it would survive a broken layer."),
    ("built_up_pct_1km", "TEST-KAREN-01", "TEST-TANADELTA-01",
     "Nairobi suburb against delta floodplain. Also a check on the D8 "
     "divisor: dividing by a nominal area rather than the true geography "
     "area tends to flatten exactly this difference."),
    # WITHDRAWN, and the reasoning is kept because the mistake is instructive.
    #
    #   ("dist_primary_school_m", "TEST-TANADELTA-01", "TEST-KAREN-01",
    #    "Remote delta against inner Nairobi...")
    #
    # It FAILED: Tana delta 0 m against Karen 741 m. The engine was right and
    # THE TEST WAS WRONG, on two counts:
    #
    #   1. KAREN IS NAIROBI'S LOWEST-DENSITY RESIDENTIAL AREA - big plots,
    #      few schools per km2. "Urban therefore closer amenities" does not
    #      hold for the one Nairobi parcel in this set. The premise was about
    #      cities in general and the parcel is a specific exception.
    #   2. 0 m IS NOT A SMALL DISTANCE, IT IS CONTAINMENT. A primary school
    #      lies INSIDE the 50-acre delta parcel. Ordering by distance silently
    #      treats "there is a school on this land" as the extreme of "nearby",
    #      which is a different kind of fact.
    #
    # The claim attached to it - "if THIS ordering inverts the
    # nearest-neighbour search is wrong, not the data" - was an overclaim, and
    # it is what made the failure look alarming. The search is demonstrably
    # fine: Kitengela 4,656 m, Aberdares 10,008 m, Athi 3,200 m, Tana
    # SECONDARY 14,140 m are all sensible and varied, and the Kakamega parcel
    # independently reads protected_area 0 m, river 0 m and 99.87% tree cover
    # - three layers agreeing it sits inside Kakamega Forest.
    #
    # Replaced with hospitals, where remoteness genuinely dominates because
    # the feature is RARE: Kenya has 37,930 schools and far fewer hospitals,
    # so a remote parcel cannot contain one by accident.
    ("dist_hospital_m", "TEST-TANADELTA-01", "TEST-KAREN-01",
     "Remote delta against Nairobi. Hospitals are rare enough that distance "
     "to one really is a remoteness measure - unlike primary schools, which "
     "are dense enough that a large rural parcel can contain one. NOTE C8: "
     "these sit at ward centroids, so only the ORDER is meaningful here, "
     "never the metres."),
    ("pop_density_km2", "TEST-KAREN-01", "TEST-TANADELTA-01",
     "Nairobi ward against a Tana delta ward. Rule D9 in executable form - "
     "'more people near A than B' is the KIND of statement this product is "
     "entitled to make about population, and this is one of them. The "
     "absolute figures are not census-calibrated (C3) and are not asserted."),
    ("nightlights_radiance_mean", "TEST-RUAI-01", "TEST-TANADELTA-01",
     "Ruai ranked TOP of the absolute-radiance trend in verify_26; the delta "
     "is unlit. Radiance is not linear in economic activity (D13), but the "
     "ORDER survives that - which is exactly why this is an ordering and not "
     "a threshold."),
]

# ---------------------------------------------------------------------------
# LICENCE EXPOSURE. Not a pass/fail - a standing inventory.
#
# Which fields, on this run, were answered from a source that is not cleared
# for commercial redistribution. A1 (WDPA is non-commercial) and A4 (OSM is
# ODbL share-alike) are the two open items, and the question a lawyer or an
# acquirer will actually ask is "which numbers in this report came from
# where". This section answers it from the data rather than from memory.
# ---------------------------------------------------------------------------
LICENCE_WATCH = ["in_riparian_buffer", "dist_river_m", "in_protected_area",
                 "dist_any_road_m", "dist_paved_road_m", "dist_tower_m",
                 "coverage_4g_pct", "coverage_2g_pct",
                 "dist_town_centre_m", "dist_airport_m", "dist_major_road_m",
                 "dist_intl_airport_m",
                 "dist_market_m", "dist_police_m", "dist_bus_stop_m",
                 "dist_railway_station_m"]

# Documented limitations. Checked, reported, and counted SEPARATELY - never
# as passes, because a known gap dressed as a pass is how a limitation
# quietly becomes a claim.
KNOWN_GAPS = {
    "TEST-ATHIPLAINS-01": [
        ("black_cotton_risk", "none",
         "SoilGrids maps the Athi-Kapiti plains as Luvisols on two separate "
         "probes and they ARE classic black cotton. Measured: iSDA texture "
         "and slope BOTH point the wrong way against Karen, so neither can "
         "rescue the miss. Checklist C16. A report must say INCONCLUSIVE "
         "here, never 'safe'."),
    ],
}


def get(row, field):
    return row.get(field)


def check(op, got, want):
    if got is None:
        return False
    if op == "==":
        return got == want
    if op == "in":
        return got in want
    if op == ">":
        return float(got) > float(want)
    if op == "<":
        return float(got) < float(want)
    if op == ">=":
        return float(got) >= float(want)
    return False


def main():
    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")

    # p.status = 'active' is NOT optional, and it was missing until the
    # loader learned to supersede.
    #
    # Superseding a parcel does not touch its enrichment - deliberately, so
    # that reports already issued to buyers still resolve. The old land.parcels
    # row goes to 'superseded' or 'rejected' and keeps its parcel_id; its
    # analytics.parcel_intelligence row stays 'active' against that same id.
    # Filtering on i.status alone therefore pulls in two kinds of ghost:
    #
    #   withdrawn parcels - rejected by the gate on a later load, still
    #     carrying the enrichment computed when they were accepted. They are
    #     no longer for sale and must not be verified.
    #   stale twins - an accepted re-load creates a NEW parcel_id at v+1 with
    #     fresh enrichment, while v1's enrichment is still 'active'. Both rows
    #     share a parcel_ref, and the dict keyed on parcel_ref below keeps
    #     whichever the sort happened to hand back last. That is a verifier
    #     silently checking last week's answers and printing them green.
    #
    # The scorer already filters on both (score_01_suitability.py). The
    # delivery API already filters on both. This was the one reader that did
    # not - which is E14 again: a green verification is not the same thing as
    # a right answer.
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.parcel_ref, p.project_name, i.*
            FROM analytics.parcel_intelligence i
            JOIN land.parcels p ON p.parcel_id = i.parcel_id
            WHERE i.status = 'active' AND p.status = 'active'
            ORDER BY p.parcel_ref
        """)).mappings().all()
    if not rows:
        sys.exit("No enrichment rows. Run:  python enrich_01_engine.py")

    # A control, not a reminder (section 6). The dict below is keyed on
    # parcel_ref, so two active rows for one ref would not error - one would
    # simply overwrite the other and the run would look clean. If the status
    # filter above is ever weakened, or the loader ever leaves two rows active
    # for the same ref, this stops the verifier instead of letting it grade
    # an arbitrary half of the evidence.
    seen = {}
    for r in rows:
        seen.setdefault(r["parcel_ref"], []).append(r["parcel_id"])
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    if dupes:
        for ref, pids in sorted(dupes.items()):
            print(f"  {ref}: parcel_ids {', '.join(str(p) for p in pids)}")
        sys.exit("ABORT: more than one active enrichment row per parcel_ref. "
                 "Two versions of the same parcel are live at once - the "
                 "loader superseded one and left the other, or the status "
                 "filter is wrong. Fix that before trusting any result here.")

    data = {r["parcel_ref"]: dict(r) for r in rows}
    print("=" * 76)
    print(f"ENRICHMENT VERIFICATION - {len(data)} parcel(s)")
    print("=" * 76)

    # ---- A. landmark assertions -----------------------------------------
    print("\nA. LANDMARK EXPECTATIONS (written before the engine existed)\n")
    npass = nfail = 0
    failures = []
    for ref, checks in EXPECT.items():
        row = data.get(ref)
        if row is None:
            print(f"   {ref:22} NOT ENRICHED - skipped")
            continue
        for field, op, want, why in checks:
            if field == "__cell_differs":
                got = row.get("flood_risk_class") != row.get(
                    "flood_risk_class_cell")
            elif field == "__breakdown_classes":
                b = row.get("flood_risk_breakdown")
                b = json.loads(b) if isinstance(b, str) else (b or {})
                got = len(b)
            elif field == "__rain_single_cell":
                got = (row.get("rainfall_min_mm_yr")
                       == row.get("rainfall_max_mm_yr")
                       == row.get("rainfall_normal_mm_yr"))
            elif field == "__dominant_share":
                c = row.get("landcover_composition")
                c = json.loads(c) if isinstance(c, str) else (c or {})
                got = max(c.values()) if c else None
            else:
                got = row.get(field)
            ok = check(op, got, want)
            if ok:
                npass += 1
                print(f"   PASS  {ref:22} {field:26} = {got}")
            else:
                nfail += 1
                print(f"   FAIL  {ref:22} {field:26} = {got}  "
                      f"(expected {op} {want})")
                failures.append((ref, field, got, want, why))

    # ---- known gaps -------------------------------------------------------
    print("\n   KNOWN GAPS - documented limitations, NOT passes\n")
    ngap = 0
    for ref, checks in KNOWN_GAPS.items():
        row = data.get(ref)
        if row is None:
            continue
        for field, expected, why in checks:
            got = row.get(field)
            state = "as documented" if got == expected else "CHANGED"
            ngap += 1
            print(f"   GAP   {ref:22} {field:26} = {got}  ({state})")
            if got != expected:
                print(f"         ^ this gap has MOVED. Re-read C16 before "
                      f"assuming it is fixed.")

    # ---- B. duplicate geometry -------------------------------------------
    print("\nB. DUPLICATE AND OVERLAPPING GEOMETRY\n")
    with engine.connect() as conn:
        dups = conn.execute(text("""
            SELECT a.parcel_ref, b.parcel_ref, a.project_name,
                   ST_Equals(a.geom, b.geom) AS identical,
                   round((100 * ST_Area(ST_Intersection(a.geom, b.geom))
                          / NULLIF(ST_Area(a.geom), 0))::numeric, 1) AS pct
            FROM land.parcels a JOIN land.parcels b
              ON a.parcel_ref < b.parcel_ref
             AND a.project_name IS NOT DISTINCT FROM b.project_name
            WHERE a.status = 'active' AND b.status = 'active'
              AND ST_Intersects(a.geom, b.geom)
            ORDER BY 4 DESC, 5 DESC
        """)).all()
    if not dups:
        print("   None. No two parcels share ground.")
    touching = 0
    for a, b, proj, ident, pct in dups:
        if ident:
            print(f"   *** IDENTICAL GEOMETRY: {a} and {b} ({proj})")
            print(f"       Two references, one polygon. Either a drafting")
            print(f"       duplicate or THE SAME GROUND ALLOCATED TWICE.")
            print(f"       A client upload must reject this, not enrich both.")
        elif float(pct or 0) < 0.5:
            # Adjacent plots SHARE A BOUNDARY. That is what a subdivision is.
            # Reporting it as an overlap finding is noise, and noise in a
            # verification report is how real findings get skimmed past.
            touching += 1
        else:
            print(f"   OVERLAP {pct}% of {a} lies inside {b} ({proj})")
            print(f"       Real overlap, not a shared boundary. Two buyers "
                  f"could be sold the same ground.")
    if touching:
        print(f"   ({touching} adjacent pair(s) share a boundary - normal "
              f"subdivision layout, not reported)")

    # ---- C. neighbour divergence -----------------------------------------
    print("\nC. PARCELS DIVERGING FROM THEIR NEIGHBOURS\n")
    by_proj = {}
    for ref, r in data.items():
        by_proj.setdefault(r.get("project_name") or "(landmarks)", []).append(
            (ref, r))
    # "NEIGHBOURS" MUST MEAN NEIGHBOURS.
    #
    # The first version grouped by project_name alone and flagged
    # TEST-ABERDARES-01 for having a steep slope against its "project median".
    # Its project is 'Flood validation' - landmarks deliberately scattered
    # across Kenya precisely BECAUSE they differ. Aberdares is supposed to be
    # steep; it passed that very assertion two sections earlier.
    #
    # The check assumed project = subdivision on contiguous land. True for
    # OAK GROVE, false for the test groupings. So contiguity is now measured
    # rather than assumed: a group only qualifies if its parcels sit within a
    # few kilometres of each other, which is what makes "diverges from its
    # neighbours" a meaningful statement at all.
    flagged = 0
    with engine.connect() as conn:
        spans = {r[0]: float(r[1] or 0) for r in conn.execute(text("""
            SELECT project_name,
                   ST_MaxDistance(ST_Collect(geom)::geometry,
                                  ST_Collect(geom)::geometry)::numeric * 111320
            FROM land.parcels WHERE status = 'active'
              AND project_name IS NOT NULL
            GROUP BY project_name""")).all()}
    CONTIGUOUS_M = 10_000.0
    for proj, members in by_proj.items():
        if proj == "(landmarks)" or len(members) < 4:
            continue
        span = spans.get(proj)
        if span is None or span > CONTIGUOUS_M:
            print(f"   {proj}: parcels span {span/1000:.0f} km - not a "
                  f"contiguous scheme, divergence check skipped")
            continue
        vals = [(ref, float(r["slope_mean_pct"])) for ref, r in members
                if r.get("slope_mean_pct") is not None]
        if len(vals) < 4:
            continue
        arr = np.array([v for _, v in vals])
        med = float(np.median(arr))
        for ref, v in vals:
            if med > 0 and v > max(3.0 * med, med + 5.0):
                flagged += 1
                print(f"   *** {ref} slope {v:.2f} deg against a project "
                      f"median of {med:.2f}")
                print(f"       Neighbouring plots in one subdivision do not "
                      f"differ like this.")
                print(f"       If this parcel was REPAIRED at load, the "
                      f"repair likely moved the")
                print(f"       polygon onto ground that is not the plot. "
                      f"Check the mutation drawing.")
    if not flagged:
        print("   None. Every parcel reads consistently with its neighbours.")

    # ---- D. field coverage ------------------------------------------------
    print("\nD. FIELD COVERAGE\n")
    watch = ["flood_risk_class", "flood_risk_breakdown", "dist_any_road_m",
             "dist_permanent_water_m", "soil_type", "soil_ph", "soil_texture",
             "black_cotton_risk", "rainfall_normal_mm_yr", "slope_mean_pct",
             "ndvi_mean", "landcover_class_worldcover",
             "landcover_composition", "landcover_class_io",
             "built_up_pct_1km",
             "in_riparian_buffer", "dist_river_m", "in_protected_area",
             "dist_primary_school_m", "dist_secondary_school_m",
             "dist_hospital_m", "dist_clinic_m", "dist_water_point_m",
             "pop_density_km2", "nightlights_radiance_mean",
             "nightlights_trend_radiance_yr", "coverage_4g_pct",
             "coverage_2g_pct", "dist_tower_m",
             "dist_town_centre_m", "nearest_town_name", "dist_airport_m",
             "nearest_airport_name", "dist_intl_airport_m",
             "nearest_intl_airport_name", "dist_major_road_m", "dist_market_m",
             "dist_police_m", "dist_bus_stop_m", "dist_railway_station_m",
             "field_confidence", "field_sources"]
    for f in watch:
        n = sum(1 for r in data.values() if r.get(f) is not None)
        bar = "#" * int(20 * n / max(1, len(data)))
        flag = "" if n == len(data) else f"   <- {len(data)-n} NULL"
        print(f"   {f:26} {n:3}/{len(data):<3} {bar:20}{flag}")

    # ---- E. orderings -----------------------------------------------------
    print("\nE. ORDERINGS THAT MUST HOLD\n")
    for field, hi_ref, lo_ref, why in ORDERINGS:
        hi, lo = data.get(hi_ref), data.get(lo_ref)
        a = hi.get(field) if hi else None
        b = lo.get(field) if lo else None
        if a is None or b is None:
            print(f"   SKIP  {field:26} {hi_ref.replace('TEST-','')}={a}, "
                  f"{lo_ref.replace('TEST-','')}={b} - not comparable")
            continue
        a, b = float(a), float(b)
        short = f"{hi_ref.replace('TEST-','')} {a:g} vs " \
                f"{lo_ref.replace('TEST-','')} {b:g}"
        if a > b:
            npass += 1
            print(f"   PASS  {field:26} {short}")
        else:
            nfail += 1
            print(f"   FAIL  {field:26} {short}  <- INVERTED")
            failures.append((f"{hi_ref} vs {lo_ref}", field, a, f"> {b}", why))

    # ---- F. licence exposure ----------------------------------------------
    print("\nF. LICENCE EXPOSURE ON THIS RUN (inventory, not pass/fail)\n")
    seen = {}
    for ref, r in data.items():
        fs = r.get("field_sources") or {}
        fs = json.loads(fs) if isinstance(fs, str) else fs
        for col in LICENCE_WATCH:
            note = fs.get(col)
            if not isinstance(note, dict):
                continue
            lic = note.get("licence") or note.get("license")
            if not lic:
                continue
            key = (col, lic, note.get("source"))
            seen[key] = seen.get(key, 0) + 1
    if not seen:
        print("   No licence recorded on any watched field. That is itself a")
        print("   finding: these layers HAVE licences, so nothing recording")
        print("   one means the lineage is not reaching field_sources.")
    else:
        for (col, lic, source), n in sorted(seen.items()):
            print(f"   {col:24} {str(source or '?'):22} {lic:24} "
                  f"{n}/{len(data)} parcels")
        print()
        print("   A1: WDPA is NON-COMMERCIAL - replace with KWS or get "
              "written clearance.")
        print("   A4: OSM is ODbL SHARE-ALIKE - riparian_buffers is the HIGH "
              "exposure item,")
        print("       because it is DERIVED GEOMETRY and therefore "
              "unambiguously a database.")

    # ---- G. landmark invariants -------------------------------------------
    print("\nG. LANDMARK INVARIANTS\n")

    for ref, (field, want, why) in LANDMARK_IDENTITY.items():
        got = (data.get(ref) or {}).get(field)
        if got == want:
            npass += 1
            print(f"   PASS  {ref:22} {field:28} = {got}")
        else:
            nfail += 1
            print(f"   FAIL  {ref:22} {field:28} = {got!r}, want {want!r}")
            failures.append((ref, field, got, want, why))

    # A NAMED major road is a SUBSET of what dist_paved_road_m searches
    # (motorway/trunk/primary, named) inside a superset (those plus secondary,
    # named or not). A subset's nearest member can never be closer than the
    # superset's, so this holds on every parcel, always. It is the one
    # assertion in this file that needs no knowledge of Kenya at all - which
    # is exactly why it is worth having.
    bad = []
    for ref, r in data.items():
        maj, pav = r.get("dist_major_road_m"), r.get("dist_paved_road_m")
        if maj is None or pav is None:
            continue
        if float(maj) < float(pav) - 0.5:
            bad.append((ref, float(maj), float(pav)))
    if bad:
        nfail += len(bad)
        for ref, maj, pav in bad:
            print(f"   FAIL  {ref:22} major road {maj:.0f} m < paved "
                  f"{pav:.0f} m  <- IMPOSSIBLE")
            failures.append((ref, "dist_major_road_m", maj, f">= {pav}",
                             "A named motorway/trunk/primary road is a subset "
                             "of the roads dist_paved_road_m searches. The "
                             "subset cannot hold a nearer member."))
    else:
        n = sum(1 for r in data.values()
                if r.get("dist_major_road_m") is not None
                and r.get("dist_paved_road_m") is not None)
        npass += 1
        print(f"   PASS  named major road >= paved road on all {n} "
              f"comparable parcel(s)")

    # Same subset argument as the roads, one table over: every international
    # airport is also an airport, so the international answer can never be
    # the nearer of the two. If it ever is, the facility_type filter is
    # matching rows the unfiltered query is somehow missing.
    bada = []
    for ref, r in data.items():
        i_, a_ = r.get("dist_intl_airport_m"), r.get("dist_airport_m")
        if i_ is None or a_ is None:
            continue
        if float(i_) < float(a_) - 0.5:
            bada.append((ref, float(i_), float(a_)))
    if bada:
        nfail += len(bada)
        for ref, i_, a_ in bada:
            print(f"   FAIL  {ref:22} international {i_:.0f} m < any airport "
                  f"{a_:.0f} m  <- IMPOSSIBLE")
            failures.append((ref, "dist_intl_airport_m", i_, f">= {a_}",
                             "Every international airport is an airport. The "
                             "filtered subset cannot hold a nearer member."))
    else:
        n = sum(1 for r in data.values()
                if r.get("dist_intl_airport_m") is not None
                and r.get("dist_airport_m") is not None)
        npass += 1
        print(f"   PASS  international airport >= any airport on all {n} "
              f"comparable parcel(s)")

    miss = []
    for ref, r in data.items():
        for dcol, ncol in LANDMARK_PAIRS:
            if (r.get(dcol) is None) != (r.get(ncol) is None):
                miss.append((ref, dcol, ncol))
    if miss:
        nfail += len(miss)
        for ref, dcol, ncol in miss:
            print(f"   FAIL  {ref:22} {dcol} and {ncol} disagree on NULL")
            failures.append((ref, dcol, "half a pair", "both or neither",
                             "A distance with no name implies we know which "
                             "landmark it is. We do not."))
    else:
        npass += 1
        print("   PASS  every landmark name/distance pair is both or neither")

    defunct = []
    for ref, r in data.items():
        for f in NAME_FIELDS:
            nm = r.get(f)
            if nm and any(w in str(nm).lower() for w in DEFUNCT_WORDS):
                defunct.append((ref, f, nm))
    if defunct:
        nfail += len(defunct)
        for ref, f, nm in defunct:
            print(f"   FAIL  {ref:22} {f} = {nm!r}  <- DEFUNCT")
            failures.append((ref, f, nm, "a facility in service",
                             "OSM says in the name that this facility is not "
                             "in service. Offering it to a buyer as their "
                             "nearest is a false promise in the source's own "
                             "words. Filter it in etl_30, not here."))
    else:
        npass += 1
        print("   PASS  no published landmark name marks a defunct facility")

    # Railway stations must not leak into the bus-stage answer. They live in
    # the same table and are separated only by stop_type, so an equal pair is
    # the signature of that filter having been dropped.
    leaks = [ref for ref, r in data.items()
             if r.get("dist_bus_stop_m") is not None
             and r.get("dist_railway_station_m") is not None
             and abs(float(r["dist_bus_stop_m"])
                     - float(r["dist_railway_station_m"])) < 0.5]
    if leaks:
        nfail += len(leaks)
        for ref in leaks:
            print(f"   FAIL  {ref:22} bus stage == railway station distance")
            failures.append((ref, "dist_bus_stop_m", "equal", "different",
                             "Both come from transport.bus_stops and are "
                             "separated only by stop_type. Equal distances "
                             "mean a station is being served as a matatu "
                             "stage."))
    else:
        npass += 1
        print("   PASS  no railway station is being served as a bus stage")

    # A town centre is never a village or a suburb - see layer_landmarks.
    wrong = [(ref, r["nearest_town_type"]) for ref, r in data.items()
             if r.get("nearest_town_type")
             and r["nearest_town_type"] not in
             ("national_capital", "city", "town")]
    if wrong:
        nfail += len(wrong)
        for ref, t in wrong:
            print(f"   FAIL  {ref:22} nearest_town_type = {t!r}")
            failures.append((ref, "nearest_town_type", t, "city/town/capital",
                             "8,679 of 9,323 places are villages. If one is "
                             "answering dist_town_centre_m, the column has "
                             "stopped measuring access to a town and started "
                             "measuring OSM tagging density."))
    else:
        npass += 1
        print("   PASS  no village or suburb is answering as a town centre")

    # ---- H. controls that must keep firing ---------------------------------
    #
    # A control nobody checks becomes a reminder again the first time someone
    # edits the layer it lives in. These do not test the ground - they test
    # that the safeguards are still switched on.
    print("\nH. CONTROLS STILL FIRING\n")

    # C16. 'none' is not a clearance. black_cotton_inconclusive must be TRUE
    # wherever the taxonomy said 'none' and the ground is flat or unmeasured,
    # because that is the exact case SoilGrids cannot separate (Karen vs the
    # Athi-Kapiti plains). Karen is EXPECTED to be flagged. If this ever
    # passes with a lower count than the flat parcels, the flag has stopped
    # failing closed and 'none' is reaching a buyer as safe ground.
    FLAT_DEG = 3.5
    should, missing = [], []
    for ref, r in data.items():
        if r.get("black_cotton_risk") == "likely":
            continue
        sl = r.get("slope_mean_pct")
        if r.get("black_cotton_risk") is None or sl is None \
                or float(sl) < FLAT_DEG:
            should.append(ref)
            if not r.get("black_cotton_inconclusive"):
                missing.append((ref, r.get("black_cotton_risk"), sl))
    if missing:
        nfail += len(missing)
        for ref, bc, sl in missing:
            print(f"   FAIL  {ref:22} black_cotton_risk={bc!r} slope={sl} "
                  f"but inconclusive is not set")
            failures.append((ref, "black_cotton_inconclusive", False, True,
                             "C16: on flat or unmeasured ground the taxonomy "
                             "check cannot clear the soil, so 'none' must "
                             "carry the inconclusive flag. Without it a "
                             "renderer prints 'none' as safe ground."))
    else:
        npass += 1
        print(f"   PASS  C16 inconclusive flag set on all {len(should)} "
              f"parcel(s) it must cover")

    # A NULL that carries no reason cannot be told apart from a NULL that
    # means 'we searched and found nothing'. Every field we hold no source
    # for must say so in field_sources on every parcel.
    unexplained = {}
    for ref, r in data.items():
        srcs = r.get("field_sources")
        if isinstance(srcs, str):
            try:
                srcs = json.loads(srcs)
            except (ValueError, TypeError):
                srcs = {}
        srcs = srcs or {}
        for col, val in r.items():
            if val is not None:
                continue
            if col in NOT_A_CLAIM or col in SEARCHED_NOTHING_DEBT:
                continue
            if col not in srcs:
                unexplained.setdefault(col, []).append(ref)
    if unexplained:
        nfail += len(unexplained)
        for col, refs in sorted(unexplained.items()):
            print(f"   FAIL  {col:28} NULL with no reason on "
                  f"{len(refs)} parcel(s)")
            failures.append((col, "field_sources", "absent", "not_sourced note",
                             "A NULL with no note cannot be distinguished "
                             "from 'searched and found nothing'. The report "
                             "can then never state the absence honestly."))
    else:
        npass += 1
        print(f"   PASS  every NULL is explained or named debt, on all "
              f"{len(data)} parcel(s)")
        print(f"         ({len(SEARCHED_NOTHING_DEBT)} column(s) exempt as "
              f"searched-found-nothing debt - see the note above)")

    # ---- verdict ----------------------------------------------------------
    print("\n" + "=" * 76)
    print(f"{npass} passed, {nfail} FAILED, {ngap} known gap(s) reported")
    if nfail:
        print("\nFAILURES:")
        for ref, field, got, want, why in failures:
            print(f"  {ref} / {field}: got {got}, expected {want}")
            print(f"    WHY IT MATTERS: {why}")
        print("\nBefore changing the engine, CHECK THE TEST (rule: before")
        print("believing a failure, check the test). Three of this session's")
        print("bugs were in the verification, not the thing verified.")
    else:
        print("\nAll landmark expectations hold.")
    print("=" * 76)
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
