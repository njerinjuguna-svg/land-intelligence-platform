r"""
============================================================================
REPORT CONTENT - the single source of truth for what we SAY about a parcel
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS MODULE EXISTS AT ALL

  Two things consume the intelligence: the embed widget on a client's website
  and the PDF a buyer downloads. If each of them translates the raw values
  into English separately, THEY WILL DRIFT, and the day they disagree about a
  flood class is the day a client stops trusting both.

  So the translation happens ONCE, here. api_01_embed.py and pdf_01_report.py
  are renderers. They choose fonts and layout; they do not choose words.

THE GEOMETRY FIREWALL LIVES HERE TOO
  Rule A4 and B4: we ship values and pictures, never geometry. That is not a
  convention to remember, it is enforced by `assert_no_geometry()` below,
  which every consumer calls before serialising anything outward. If it ever
  raises, something was about to hand a client a database.

WHAT THIS MODULE WILL NOT DO
  It will not invent a value, soften a refusal, or fill a gap. A parcel that
  the scorer blocked comes back with `withheld` set and no scores, and both
  renderers are expected to show that rather than route around it.
============================================================================
"""

import json
import re

# Anything shaped like geometry must never leave the building. Checked, not
# trusted: rule A4's exposure is DISTRIBUTION, so this is the boundary where
# the obligation would attach.
GEOMETRY_KEYS = re.compile(
    r"(^|_)(geom|geometry|wkt|wkb|geojson|coords?|coordinates|the_geom)($|_)",
    re.I)


class GeometryLeak(Exception):
    """Raised when a payload about to be sent outward contains geometry."""


def assert_no_geometry(payload, path="payload"):
    """Walk a structure and refuse anything that looks like geometry.

    Called by every renderer before it serialises. A convention would be
    'remember not to select geom'; this is the control that survives someone
    forgetting.
    """
    if isinstance(payload, dict):
        for k, v in payload.items():
            if GEOMETRY_KEYS.search(str(k)):
                raise GeometryLeak(
                    f"{path}.{k} looks like geometry. We ship values and "
                    f"pictures, never geometry (checklist A4 / B4). Remove it "
                    f"from the query rather than from the response.")
            assert_no_geometry(v, f"{path}.{k}")
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            assert_no_geometry(v, f"{path}[{i}]")
    elif isinstance(payload, str):
        # NO LENGTH GATE. The first version of this only inspected strings
        # longer than 60 characters, on the reasoning that geometry is bulky.
        # A four-corner MULTIPOLYGON is 57 characters and a small GeoJSON
        # Polygon is 57 - both walked straight through, and the unit test
        # below caught it on the first run.
        #
        # An arbitrary threshold inside a guard is how the guard stops being
        # one. These payloads are small; scan every string.
        head = payload.lstrip().upper()
        if head.startswith(("POLYGON", "MULTIPOLYGON", "POINT", "LINESTRING",
                            "MULTILINESTRING", "GEOMETRYCOLLECTION",
                            "SRID=")):
            raise GeometryLeak(f"{path} carries WKT geometry.")
        if '"coordinates"' in payload or '"COORDINATES"' in head:
            raise GeometryLeak(f"{path} carries GeoJSON geometry.")
    return payload


# ---------------------------------------------------------------------------
# Plain-language helpers
# ---------------------------------------------------------------------------
FLOOD_WORD = {"very_low": "very low", "low": "low", "moderate": "some",
              "high": "high", "very_high": "very high",
              "permanent_water": "permanent water"}

SURE = {4: "We're confident about this.",
        3: "We're fairly confident about this.",
        2: "Treat this as a rough guide.",
        1: "We can't be sure. See the checklist."}


def travel(m):
    """Metres -> how a person would actually describe getting there."""
    if m is None:
        return None
    m = float(m)
    if m == 0:
        return "On the plot itself"          # D18: containment, not distance
    if m < 1600:
        return f"{max(1, round(m / 80))} min walk"
    return f"{max(1, round(m / 1000 / 40 * 60))} min drive"


def spell(m):
    if m is None:
        return None
    m = float(m)
    if m == 0:
        return "on the plot"
    return f"{m/1000:.1f} km away" if m >= 1000 else f"{m:.0f} m away"


def acres(sqm):
    if not sqm:
        return None
    a = float(sqm) / 4046.86
    return f"{a:.2f} acres" if a < 10 else f"{a:.0f} acres"


def _j(v):
    return json.loads(v) if isinstance(v, str) else (v or {})


# ---------------------------------------------------------------------------
# The four questions
# ---------------------------------------------------------------------------
def _build(i, blocked):
    fc = i.get("flood_risk_class")
    bc = i.get("black_cotton_risk")
    slope = i.get("slope_mean_pct")
    # ASK THE ROW, DO NOT RE-DERIVE. `slope < 3.5` used to be written here and
    # again in _checklist, and nowhere in the engine. Two copies of a rule is
    # one copy plus a future divergence. The engine sets
    # black_cotton_inconclusive and fails toward TRUE; both readers ask it.
    unsure_soil = bool(i.get("black_cotton_inconclusive"))

    if i.get("in_protected_area"):
        return dict(tone="no", answer="No",
                    because="Our data places this land inside a gazetted "
                            "protected area.",
                    means="Walk away unless the seller shows you written "
                          "proof from the authorities that this land can be "
                          "sold. Do not pay a deposit first.", sure=2)
    if i.get("in_riparian_buffer"):
        return dict(tone="no", answer="Not on all of it",
                    because="Part of this plot falls inside a river reserve, "
                            "which by law you cannot build on.",
                    means="Have a surveyor mark the reserve on the ground "
                          "before you plan anything. What is left may still "
                          "be buildable.", sure=3)
    if bc != "likely" and unsure_soil:
        return dict(tone="unsure", answer="We can't tell you yet",
                    because="The soil maps read this ground as ordinary clay, "
                            "but flat land in this part of Kenya is often "
                            "black cotton and our data cannot tell the two "
                            "apart here.",
                    means="Do not agree a building budget until a soil test "
                          "is done. Black cotton can add a lot to what the "
                          "foundation costs.", sure=1)
    if bc == "likely":
        return dict(tone="careful", answer="Yes, but budget for the foundation",
                    because="This is black cotton soil. It swells and shrinks "
                            "with moisture.",
                    means="You can build here, but the footings cost more. "
                          "Get a soil test and have a builder price it before "
                          "you commit.", sure=3)
    if fc in ("high", "very_high"):
        return dict(tone="no", answer="Not recommended",
                    because=f"A real part of this plot sits in the "
                            f"{FLOOD_WORD.get(fc, fc)} flood category.",
                    means="If you must build, keep well away from the low "
                          "ground and expect to raise the floor level.",
                    sure=3)
    if slope is not None and float(slope) > 12:
        # No degree figure. Same reasoning as the ground card: a buyer cannot
        # do anything with "7.06 degrees", and the sentence already says the
        # thing that matters.
        return dict(tone="careful", answer="Yes, on a slope",
                    because="The ground here is steep enough that building "
                            "on it costs more than on flat land.",
                    means="Expect cut-and-fill costs, and check where water "
                          "runs during heavy rain.", sure=3)
    return dict(tone="yes", answer="Yes",
                because="The ground is workable and we found no flooding "
                        "risk and no river reserve on it.",
                means="You can build here. Still get a soil test and confirm "
                      "the boundary. Both are on the checklist.", sure=3)


def _farm(i):
    rain = i.get("rainfall_normal_mm_yr")
    driest = i.get("rainfall_driest_year_pct")
    r = float(rain) if rain is not None else None
    if r is None:
        return dict(tone="unsure", answer="Not assessed",
                    because="We have no rainfall reading for this plot.",
                    means="Ask locally what grows here.", sure=1)
    if r >= 1200:
        return dict(tone="yes", answer="Yes, this is good growing land",
                    because=f"Heavy, reliable rain of about {r:,.0f} mm a "
                            f"year.",
                    means="Proper farming land. If it also floods, that is "
                          "the same water that makes the soil rich. Plan for "
                          "it rather than against it.", sure=3)
    if r >= 800:
        return dict(tone="yes", answer="Yes, for most crops",
                    because=f"Rain is reliable, about {r:,.0f} mm a year, "
                            f"enough for maize without irrigation.",
                    means="Good for a kitchen garden, fruit trees or a small "
                          "shamba.", sure=3)
    if r >= 650:
        return dict(tone="careful", answer="With care",
                    because=f"Rain is moderate at about {r:,.0f} mm a year"
                            + (f", and in the driest years it drops to "
                               f"{float(driest):.0f}% of that"
                               if driest is not None else "") + ".",
                    means="Drought-hardy crops or grazing. Anything else "
                          "needs a water source.", sure=3)
    return dict(tone="careful", answer="Only with water",
                because=f"Rain is low, about {r:,.0f} mm a year.",
                means="You would need a borehole or a dam for anything "
                      "beyond drought-hardy crops or grazing.", sure=3)


def _flood(i):
    fc = i.get("flood_risk_class")
    cell = i.get("flood_risk_class_cell")
    if fc is None:
        return dict(tone="unsure", answer="Not assessed",
                    because="No flood reading for this plot.",
                    means="Ask neighbours what happens in a heavy season.",
                    sure=1)
    if fc in ("very_high", "high"):
        return dict(tone="no", answer="Yes, it floods",
                    because="A large part of this plot is in the highest "
                            "flood categories, and so is the land around it.",
                    means="Expect water here in a heavy season. Ask "
                          "neighbours how high it came last time. They will "
                          "know better than any map.", sure=3)
    if fc == "moderate":
        return dict(tone="careful", answer="Mostly fine, part of it is not",
                    because="Most of the plot is on safe ground, but a lower "
                            "part could take water in heavy rain."
                            + (f" The plot as a whole reads "
                               f"{FLOOD_WORD.get(cell, cell)}."
                               if cell and cell != fc else ""),
                    means="Do not put the house on the low ground. Walk the "
                          "plot after heavy rain if you can.", sure=3)
    return dict(tone="yes", answer="No flooding expected",
                because="The whole plot sits on ground that sheds water "
                        "rather than collecting it.",
                means="Flooding is not a concern here.", sure=3)


def _grow(i):
    t = i.get("nightlights_trend_radiance_yr")
    t = float(t) if t is not None else None
    built = i.get("built_up_pct_1km")
    if t is None:
        return dict(tone="unsure", answer="Not assessed",
                    because="No development reading for this area.",
                    means="Look at what is being built nearby.", sure=1)
    if t >= 150:
        return dict(tone="yes", answer="Yes, and quickly",
                    because="Lights at night here have been increasing fast, "
                            "which is what happens when people build.",
                    means="This area is on the way up. That usually shows in "
                          "land prices.", sure=3)
    if t >= 25:
        return dict(tone="careful", answer="Yes, steadily",
                    because="There is real growth in night-time lights, but "
                            "not at the pace of the fastest peri-urban areas.",
                    means="Steady area. Buy for what you will use it for, "
                          "not for a quick rise.", sure=3)
    return dict(tone="careful", answer="Quietly",
                because="Very little change in night-time lights"
                        + (f", and only {float(built):.1f}% of the "
                           f"surrounding kilometre is built on"
                           if built is not None else "") + ".",
                means="Remote or slow-moving. Buy this for what it produces, "
                      "not for price growth.", sure=3)


# ---------------------------------------------------------------------------
# The checklist - generated from findings, never boilerplate
# ---------------------------------------------------------------------------
def _checklist(i, withheld):
    out = []
    if withheld and withheld.get("rule") == "boundary not trusted":
        out.append(("Ask the seller for the mutation drawing",
                    "This is the surveyed drawing showing the plot boundary. "
                    "Without it nobody can tell you what you are buying."))
        out.append(("Do not pay a deposit until the size is confirmed",
                    "The boundary we were given does not close properly."))
    if i.get("in_protected_area"):
        out.append(("Ask the seller for written proof this land can be sold",
                    "Our data places it inside a protected area. Do not pay "
                    "anything before you have seen this."))
    if i.get("in_riparian_buffer"):
        out.append(("Ask the county where the river reserve runs",
                    "You cannot build inside it. A surveyor can mark it on "
                    "the ground."))
    # Second reader of the same rule - and the reason it is now one flag on
    # the row rather than this expression written out twice.
    bc = i.get("black_cotton_risk")
    if bc != "likely" and i.get("black_cotton_inconclusive"):
        out.append(("Get a soil test. This is the important one.",
                    "Ask for a test that says whether the soil is expansive "
                    "or black cotton. Do it before you agree a building "
                    "budget."))
    elif bc == "likely":
        # The `why` names the finding, because this item can appear on a page
        # where nothing else mentions soil. On TEST-KANO-01 the build question
        # is answered by the river reserve, so black cotton never comes up in
        # the four questions - and the checklist then told the buyer to price
        # a foundation for a soil the report had not said was there. Advice
        # arriving without its reason reads as boilerplate, and boilerplate is
        # the thing people skip.
        out.append(("Have a builder price the foundation for black cotton",
                    "The soil maps read this ground as black cotton, which "
                    "swells in the rain and shrinks in the dry. It holds a "
                    "building fine once the footings are right, but the "
                    "footings cost more - so price them before you pay for "
                    "the land, not after."))
    if i.get("flood_risk_class") in ("moderate", "high", "very_high"):
        out.append(("Ask neighbours how high the water came last season",
                    "Our flood reading is worked out from the shape of the "
                    "land. It cannot see a blocked drain or a broken dike."))
    d = i.get("dist_water_point_m")
    if d is None or float(d) > 5000:
        out.append(("Find out where water will come from",
                    "We found no mapped water point close to this plot."))
    # Always, and last - these are the ones no dataset can answer.
    out.append(("Confirm the boundary with a licensed surveyor",
                "Our measurements come from maps, not from beacons on the "
                "ground."))
    out.append(("Have your advocate do an official search at the Lands office",
                "We do not check ownership, charges or disputes. Nothing in "
                "this report is a substitute for that search."))
    return [{"do": a, "why": b} for a, b in out]


# The third element is the KIND, and it exists because of what the first four
# PDFs looked like. Athi Plains led its "What is nearby" list with
#
#     River          2 min walk      161 m away
#
# ranked first because the list sorts by distance and 161 m is the smallest
# number on the page. Read as a list of conveniences - which is exactly what a
# heading like "What is nearby" invites - that says the plot has a river close
# by, a good thing. It is not. At 161 m a watercourse is a RIPARIAN SETBACK
# and a flood pathway: a constraint on where you may build, not an amenity.
#
# Every other row on that list is something you WANT to be near and the river
# was being scored by the same rule. Distance alone cannot tell them apart, so
# the kind is declared here rather than inferred.
#     amenity - nearer is better
#     feature - nearer is a constraint; never rank it among the conveniences
NEARBY_FIELDS = [
    ("Main road", "dist_any_road_m", "amenity"),
    ("Tarmac road", "dist_paved_road_m", "amenity"),
    ("Primary school", "dist_primary_school_m", "amenity"),
    ("Secondary school", "dist_secondary_school_m", "amenity"),
    ("Clinic", "dist_clinic_m", "amenity"),
    ("Hospital", "dist_hospital_m", "amenity"),
    ("Water point", "dist_water_point_m", "amenity"),
    ("Mobile network mast", "dist_tower_m", "amenity"),
    ("River", "dist_river_m", "feature"),
]

# What each score is FOR, in the words a buyer would use. Kept here so the
# headline, the embed and the PDF cannot describe the same score differently.
USE_WORDS = {"residential": "building a home",
             "agricultural": "farming",
             "commercial": "business use",
             "investment": "holding as an investment"}
USE_SHORT = {"residential": "residential", "agricultural": "agricultural",
             "commercial": "commercial", "investment": "investment"}

LIMITS = [
    "Everything here is measured from satellite images, terrain, rainfall "
    "records and public datasets. Nobody from our team has stood on this land.",
    "This is not a valuation and not a legal opinion. It does not confirm who "
    "owns the land or where its legal boundary runs.",
    "Flood risk is worked out from the shape of the land, not from flood "
    "records. It cannot see a broken dike or a blocked drain.",
    "Always visit the plot and use an advocate and a licensed surveyor before "
    "you pay any money.",
]


def build_report(intel, score=None, parcel=None):
    """intel + score rows (as dicts) -> everything a renderer needs.

    Returns plain data only. No geometry, by construction and by check.
    """
    i, s = dict(intel or {}), dict(score or {})
    p = dict(parcel or {})
    bd = _j(s.get("score_breakdown"))
    withheld = bd.get("blocked")

    rep = {
        "ref": p.get("parcel_ref") or i.get("parcel_ref"),
        "project": p.get("project_name"),
        # SIZE: the client's stated area if they gave one, otherwise measured
        # off the boundary. See the long note in pdf_01_report.py - the column
        # is nullable and nobody populates it, which is why twenty reports
        # printed no acreage at all while the geometry held the answer.
        #
        # Their figure wins when present. If a seller advertises an eighth of
        # an acre we quote an eighth of an acre; quietly replacing it with our
        # own measurement of their plot would be a survey finding delivered as
        # a typo, and if the two disagree that is a conversation to have with
        # the client, not a number to overwrite in a buyer's report.
        "size": acres(p.get("area_sqm") if p.get("area_sqm")
                      else p.get("area_calc_sqm")),
        "size_measured": not p.get("area_sqm") and bool(p.get("area_calc_sqm")),
        "withheld": None,
        "score": None,
        "questions": [],
        "nearby": [],
        "checklist": _checklist(i, withheld),
        "limits": LIMITS,
        "generated_from": {
            "intelligence_version": i.get("version"),
            "score_version": s.get("version"),
            "model_version": s.get("model_version"),
            "computed_at": str(i.get("computed_at") or ""),
        },
    }

    if withheld:
        rep["withheld"] = {
            "title": ("We cannot report on this plot yet"
                      if withheld["rule"] == "boundary not trusted"
                      else "This plot is not for sale as far as we can tell"),
            "text": withheld["reason"],
            "display": withheld.get("display"),
        }
    else:
        best = bd.get("best_use")
        if s.get("overall_score") is not None:
            v = float(s["overall_score"])
            label = "Good" if v >= 75 else "Fair" if v >= 55 else "Poor"

            # THE CAP HAS TO SURVIVE THE SKIM.
            #
            # TEST-KANO-01 printed "89 / 100 - Good, best suited to
            # agricultural use" across the top of a plot the model had CAPPED
            # AT 35 FOR RESIDENTIAL because a large part of it is in the
            # highest flood categories. Everything needed to see that was on
            # the page: the flood question said "Yes, it floods", and the note
            # said the overall figure is the best of the four.
            #
            # None of that helps. The overwhelming majority of people opening
            # a report on a plot intend to BUILD on it, they read the big
            # number first, and "89 / 100 - Good" is what they will carry away
            # from a page whose own model says do not build here. LESSON 42
            # established that a cap is a different KIND of statement from a
            # low score. It has to look like one on the page too, or the
            # distinction only exists in the database.
            #
            # So any use that was capped is named beside the headline. The
            # cap's own reason string is NOT reproduced - those are written
            # for the breakdown and read like model internals. The four
            # questions below already say why in plain words.
            warn = []
            for kind, det in (bd.get("scores") or {}).items():
                if not isinstance(det, dict) or not det.get("caps_applied"):
                    continue
                if kind == best:
                    continue
                val = det.get("score")
                if val is None:
                    continue
                warn.append({"use": kind, "value": float(val),
                             "words": USE_WORDS.get(kind, kind)})
            warn.sort(key=lambda w: w["value"])

            # WHICH CAPPED USE THE HEADLINE NAMES, AND WHY IT IS NOT THE
            # LOWEST ONE.
            #
            # The first version took the lowest capped score. On TEST-KANO-01
            # three uses were capped - investment 32, residential 35,
            # commercial 50 - so it printed:
            #
            #     "We do not recommend this plot for HOLDING AS AN INVESTMENT
            #      - it scores 32 out of 100 for that."
            #
            # which is true, and useless. This warning exists for exactly one
            # reason: to stop somebody building a house on land the model says
            # not to build on. Kano floods. The sentence a buyer needed was
            # about BUILDING, and picking by lowest score buried it behind a
            # market opinion nobody opened the report for.
            #
            # "Lowest number" is not the same question as "worst consequence",
            # and sorting answered the first while the paragraph above it
            # promised the second. So the choice is by CONSEQUENCE, in a fixed
            # order, and investment never wins it: a weak investment score
            # costs money slowly and is argued with in the breakdown, while a
            # house on a floodplain is a different category of wrong.
            PRIORITY = ["residential", "commercial", "agricultural"]
            lead = next((w for k in PRIORITY for w in warn if w["use"] == k),
                        None)
            others = len(warn) - 1 if lead else 0

            rep["score"] = {
                "value": v,
                "best_use": best,
                "label": label,
                # ONE string, built once. Two renderers were composing this
                # themselves and the PDF produced "Good best suited to
                # residential use" - no punctuation between the band and the
                # clause, because each half read fine on its own.
                "headline": "%.0f / 100, %s" % (v, label),
                "use_line": ("Best for %s." % USE_WORDS[best]
                             if best in USE_WORDS else None),
                "not_for": warn,
                "not_for_line": (
                    None if not lead else
                    "We do not recommend this plot for %s. It scores %.0f "
                    "out of 100 for that%s. The reasons are below."
                    % (lead["words"], lead["value"],
                       "" if others <= 0 else
                       (", and one other use is limited too" if others == 1
                        else ", and %d other uses are limited too" % others))),
                "by_use": {k: (None if s.get(k + "_score") is None
                               else float(s[k + "_score"]))
                           for k in ("residential", "agricultural",
                                     "commercial", "investment")},
                "note": "The overall figure is the best of the four, not their "
                        "average. Land is bought for a purpose.",
            }
        rep["questions"] = [
            {"ask": "Can I build a house here?", **_build(i, withheld)},
            {"ask": "Can I farm it?", **_farm(i)},
            {"ask": "Will it flood?", **_flood(i)},
            {"ask": "Is this area growing?", **_grow(i)},
        ]
        for q in rep["questions"]:
            q["confidence_text"] = SURE.get(q.pop("sure", 3))

    # ---------------------------------------------------------------------
    # WHAT IS NEARBY - AND WHETHER WE ARE ENTITLED TO SAY "ON THE PLOT".
    #
    # PLOT-950's report refused to score it, saying in a red panel:
    #
    #     "Every score would be computed on ground we are not confident is
    #      the plot."
    #
    # and then, four lines lower, asserted:
    #
    #     "On the plot itself: river."
    #
    # That is a contradiction on one page, and it is the more dangerous half
    # that we got wrong. A distance survives a bad boundary reasonably well -
    # a hospital 1.6 km from roughly-there is 1.6 km from actually-there.
    # CONTAINMENT DOES NOT SURVIVE IT AT ALL. "A river crosses this land" is
    # a claim made ENTIRELY out of the boundary, and the boundary is the one
    # thing we just told the reader we do not trust. It is also, of the two
    # statements, the one a buyer would act on.
    #
    # So when the boundary is untrusted, containment is downgraded to
    # proximity - which is what the measurement can still support - and the
    # whole list is captioned. The rows are kept: a buyer whose plot we cannot
    # score is exactly the buyer who needs to know a river is right there.
    trusted = not (withheld and withheld.get("rule") == "boundary not trusted")
    rep["nearby_trusted"] = trusted

    # A MEASURED size is a boundary claim like any other. PLOT-950's own
    # checklist says "Do not pay a deposit until the size is confirmed - the
    # boundary we were given does not close properly", and printing "0.31
    # acres" in the subtitle three centimetres above that is the same
    # contradiction as "On the plot itself: river". A size the CLIENT stated
    # survives, because that is their claim and we are only repeating it.
    if not trusted and rep.get("size_measured"):
        rep["size"] = None
        rep["size_measured"] = False
    rep["nearby_caveat"] = (
        None if trusted else
        "These distances are measured from the boundary we were given, and "
        "that boundary is the reason we cannot report on this plot. Treat "
        "them as the general area, not as measurements of your plot.")

    # Same collapse as the listing view - see COLLAPSE_WHEN_EQUAL. The report
    # is the paid product; it must not invent a second health facility either.
    rep_collapsed = _collapse_map(i, [k for _, k, _ in NEARBY_FIELDS])

    for label, key, kind in NEARBY_FIELDS:
        v = i.get(key)
        if v is None:
            continue
        if key in rep_collapsed:
            if rep_collapsed[key] is None:
                continue
            label = rep_collapsed[key]
        v = float(v)
        contained = (v == 0.0) and trusted
        rep["nearby"].append({
            "what": label, "kind": kind, "metres": v, "contained": contained,
            "travel": ("At or right beside the plot" if v == 0.0 and not trusted
                       else travel(v)),
            "spelled": ("boundary not confirmed" if v == 0.0 and not trusted
                        else spell(v))})
    rep["nearby"].sort(key=lambda n: n["metres"])

    return assert_no_geometry(rep, "report")


# ===========================================================================
# THE LISTING VIEW - the seller's website, which is a DIFFERENT PRODUCT
# ===========================================================================
# TWO PRODUCTS, TWO AUDIENCES, AND THE DIFFERENCE IS NOT COSMETIC.
#
#   PHASE 1 - WHAT WE SELL TODAY. Enrichment of a SELLER'S OWN parcels,
#   displayed on the SELLER'S OWN website. They are the customer. They are
#   describing land they own to a buyer they are courting. This view presents
#   what the land IS - size, soil, rainfall, access, what is nearby - and it
#   does not editorialise.
#
#   PHASE 2 - THE GEOCODE MARKETPLACE, once there are clients. We own it, the
#   BUYER is the reader, and it carries the unbiased half: the suitability
#   verdict, the flood warning, the protected-area refusal, the "before you
#   pay" checklist, the recommendation. `clients.companies.marketplace_opt_in`
#   already exists in the schema for it.
#
# WHY THE JUDGEMENTS ARE NOT ON THE SELLER'S PAGE.
#
# A seller will always want the best for their own plots, and that is not a
# criticism - it is what a seller is FOR. Putting our refusals on their page
# asks them to host an argument against their own sale, and the first time a
# widget prints "Not for sale - protected land" on a client's live listing we
# lose the client, not the plot.
#
# It also would not survive: a client who can see the analysis on their page
# will ask us to soften it, and the moment we do, the analysis is worth
# nothing anywhere - including on the marketplace where it is the product.
#
# SO THE SPLIT IS DELIBERATE AND IT PROTECTS BOTH SIDES. Facts go on the
# seller's page. Judgements go where we own the page and the buyer is the
# reader. Nothing is falsified in either place; a fact is simply not a verdict.
#
# ONE THING NEVER MOVES: we do not print a claim we cannot source. No title
# status, no zoning, no electricity connection, no per-operator coverage. On a
# SELLER'S page that rule matters MORE, not less - a "Title Verified" badge
# on the page of the person selling the land is the single most dangerous
# thing this product could render, and it is dangerous precisely because it
# benefits them. D20 and D23 apply here without exception.
#
# WHERE THE PLOT SIZE COMES FROM.
#
# The SELLER'S figure. Not ours. They surveyed it, they are selling it, and
# they are the customer - quietly replacing their acreage with our own
# measurement of their plot is a survey finding delivered as a typo. If they
# gave us no size, the field is simply absent. The geometry-derived figure
# stays in the PDF and belongs to Phase 2, where the reader is the buyer and
# an independent measurement is the point.

SOIL_WORDS = {
    # WRB reference soil group -> what a buyer would call it, and why they care.
    # These are the groups that actually occur across the test set and the
    # main agricultural zones; anything unmapped falls through to the texture,
    # which is always populated, rather than to a blank.
    "Nitisols":   ("Deep red volcanic",
                   "The coffee soil of the central highlands. Deep, fertile "
                   "and drains well."),
    "Vertisols":  ("Black cotton",
                   "Swells in the rain and shrinks in the dry. Grows well; "
                   "the foundation costs more."),
    "Andosols":   ("Volcanic ash",
                   "Light, free-draining and very fertile."),
    "Ferralsols": ("Deep weathered red",
                   "Old, deep soil. Drains freely; needs feeding to farm hard."),
    "Acrisols":   ("Acid clay",
                   "Fertile with lime and manure; naturally on the sour side."),
    "Luvisols":   ("Clay loam",
                   "Good general-purpose soil, holds water well."),
    "Cambisols":  ("Young mixed soil",
                   "Still forming. Workable, with no strong character either way."),
    "Fluvisols":  ("River silt",
                   "Laid down by flooding, which is what makes it rich."),
    "Solonetz":   ("Sodic soil",
                   "High in salts. Hard to farm without treatment."),
    "Arenosols":  ("Sandy",
                   "Drains very fast. Needs water and organic matter."),
    "Leptosols":  ("Thin over rock",
                   "Shallow. Check depth before planning foundations or trees."),
    "Planosols":  ("Waterlogging clay",
                   "A dense layer underneath traps water after heavy rain."),
    "Gleysols":   ("Wet ground soil",
                   "Sits wet for part of the year."),
    "Phaeozems":  ("Dark fertile loam",
                   "Among the best farming soil there is."),
    "Regosols":   ("Loose young soil",
                   "Little structure yet; erodes if left bare."),
    "Calcisols":  ("Limey soil",
                   "Chalky. Fine for building, needs management to farm."),
}


def _soil_card(i):
    t = i.get("soil_type")
    tex = i.get("soil_texture")
    if t in SOIL_WORDS:
        head, note = SOIL_WORDS[t]
        return {"k": "Soil", "v": head, "n": note}
    if tex:
        # The texture is populated on every parcel, so it is a real fallback
        # rather than a shrug. Naming an unmapped WRB group at a buyer would
        # be worse than useless - "Umbrisols" tells them nothing.
        return {"k": "Soil", "v": str(tex),
                "n": "Measured from soil maps, not from a sample on site."}
    return None


def _rain_card(i):
    mm = i.get("rainfall_normal_mm_yr")
    if mm is None:
        return None
    mm = float(mm)
    if mm < 400:
        v, n = "Very low", ("Under {:,.0f} mm a year. You would need a "
                            "borehole or a dam for anything beyond grazing.")
    elif mm < 700:
        v, n = "Low", ("About {:,.0f} mm a year. Drought-hardy crops, or "
                       "irrigation for anything else.")
    elif mm < 1000:
        v, n = "Reliable", ("About {:,.0f} mm a year, enough for maize and a "
                            "kitchen garden without irrigation.")
    elif mm < 1500:
        v, n = "Good", ("About {:,.0f} mm a year. Comfortable for most crops.")
    else:
        v, n = "Heavy", ("About {:,.0f} mm a year. Plenty of water; plan "
                         "drainage rather than storage.")
    return {"k": "Rainfall", "v": v, "n": n.format(mm)}


def _flood_card(i):
    fc = i.get("flood_risk_class")
    words = {
        "very_low": ("Not expected",
                     "The plot sheds water rather than collecting it."),
        "low": ("Unlikely",
                "Low-lying ground is nearby but not on the plot."),
        "moderate": ("Possible in heavy rain",
                     "Part of this plot can take water in a heavy season."),
        "high": ("Likely",
                 "A large part of this plot is on ground that floods."),
        "very_high": ("Yes, it floods",
                      "Expect water here in a heavy season."),
        "permanent_water": ("Standing water",
                            "Part of this plot is under water year-round."),
    }
    if fc not in words:
        return None
    v, n = words[fc]
    return {"k": "Flooding", "v": v, "n": n}


def _ground_card(i):
    # NO NUMBER. slope_mean_pct holds degrees, and this card briefly printed
    # them as "About {s} in 100" - a gradient, which is a different quantity,
    # understating 7 degrees as 7 in 100 when it is 12. That was fixed with a
    # tan() conversion, and then the number was removed entirely, which is the
    # better answer:
    #
    #   "About 9 in 100" is now CORRECT and still means nothing to a buyer
    #   standing on a plot in Juja. Correct and meaningless is meaningless.
    #
    # What a buyer is asking is whether it costs more to build here, and the
    # band answers that. The degrees stay in the database for the scorer, the
    # PDF and anyone who asks; they do not go on a seller's page.
    #
    # Worth remembering as a general rule: precision the reader cannot use is
    # not rigour, it is clutter that looks like rigour.
    s = i.get("slope_mean_pct")
    if s is None:
        return None
    s = float(s)
    if s < 2:
        v, n = "Almost flat", "Easy to build on. Check that water drains away."
    elif s < 5:
        v, n = "Gently sloping", ("Easy to build on, and water runs off rather "
                                  "than sitting.")
    elif s < 10:
        v, n = "Sloping", "Buildable, with some cut and fill."
    elif s < 20:
        v, n = "Steep", "Expect real groundwork costs."
    else:
        v, n = "Very steep", "Difficult and expensive to build on."
    return {"k": "Ground", "v": v, "n": n}


# Landmarks a buyer orients by. dist_airport_m is DELIBERATELY ABSENT: it is
# the nearest aviation facility of any kind and on every OAK GROVE plot that
# is a police airstrip nobody can fly from (checklist D23). The international
# airport is the one that answers "where would I fly from".
LANDMARK_FIELDS = [
    ("dist_town_centre_m", "nearest_town_name", "{name} town centre"),
    ("dist_major_road_m", "nearest_major_road_name", "{name}"),
    # Market and the matatu stage live in the ACCESS and AMENITIES groups.
    # Listing them here as well printed each of them twice on the widget -
    # the groups answer different questions but they draw from one row, so
    # every field belongs to exactly one of them.
    # "{name} Railway Station" printed "Ruiru Railway Station Railway Station":
    # OSM names some stations with the words already in them and some without
    # (Miwani, Butere, Ngong, Webuye). The suffix is added only when missing.
    ("dist_railway_station_m", "nearest_railway_station_name", "{name}|station"),
    ("dist_intl_airport_m", "nearest_intl_airport_name", "{name}"),
]

# Split into the two groups the card layout uses. Access answers "can I get
# here"; amenities answer "what is life like here". They are different
# questions and a buyer scans them separately.
ACCESS_FIELDS = [
    ("Main road", "dist_any_road_m"),
    ("Tarmac road", "dist_paved_road_m"),
    ("Bus / matatu stage", "dist_bus_stop_m"),
]

AMENITY_FIELDS = [
    ("Primary school", "dist_primary_school_m"),
    ("Secondary school", "dist_secondary_school_m"),
    ("Clinic", "dist_clinic_m"),
    ("Hospital", "dist_hospital_m"),
    ("Water point", "dist_water_point_m"),
    ("Market", "dist_market_m"),
    ("Police station", "dist_police_m"),
]


# When two amenity fields resolve to the SAME distance they are the same
# building, and printing both invents a second one.
#
# Health is where this bites. Facilities sit at the WARD CENTROID, not at
# their true position (C8, confidence 2), so the nearest clinic and the
# nearest hospital collapse onto one point wherever a ward holds only one
# facility - which is most rural wards. Measured on this build's parcels,
# four of the five that report both give identical figures: PLOT-365
# 1391/1391, Kericho 834/834, Kitengela 1465/1465, Ruai 2015/2015. The widget
# was stacking them as two lines, and a buyer reads two lines as two places.
#
# Collapsed to one row named for what we can actually stand behind - that
# there is a health facility at that distance - and NOT for which kind, since
# at ward-centroid resolution we do not know that the two are distinct.
#
# Left as a pair wherever the distances differ (Karen 3088/2489, Lodwar
# 15550/10181, Tana Delta 23826/7939): there the data really is telling us
# about two facilities.
COLLAPSE_WHEN_EQUAL = [
    (("dist_clinic_m", "dist_hospital_m"), "Health facility"),
]


def _collapse_map(i, keys):
    """-> {key: replacement label} / {key: None} for rows to drop.

    Shared by the listing view and the report so the two products cannot
    drift apart on the same question.
    """
    collapsed = {}
    for (a, b), label in COLLAPSE_WHEN_EQUAL:
        if a in keys and b in keys:
            va, vb = i.get(a), i.get(b)
            if va is not None and vb is not None and float(va) == float(vb):
                collapsed[a] = label      # first of the pair carries the row
                collapsed[b] = None       # second is dropped
    return collapsed


def _rows(i, fields):
    collapsed = _collapse_map(i, [k for _, k in fields])
    out = []
    for label, key in fields:
        v = i.get(key)
        if v is None:
            continue
        if key in collapsed:
            if collapsed[key] is None:
                continue
            label = collapsed[key]
        v = float(v)
        out.append({"what": label, "metres": v,
                    "travel": "On the plot" if v == 0 else travel(v),
                    "spelled": spell(v)})
    out.sort(key=lambda r: r["metres"])
    return out


def _landmarks(i):
    out = []
    for dkey, nkey, tmpl in LANDMARK_FIELDS:
        v = i.get(dkey)
        if v is None:
            continue
        if nkey:
            nm = i.get(nkey)
            if not nm:
                continue          # atomic pair, per D23
            if tmpl.endswith("|station"):
                label = (str(nm) if "station" in str(nm).lower()
                         else f"{nm} Railway Station")
            else:
                label = tmpl.format(name=nm)
        else:
            label = tmpl
        v = float(v)
        out.append({"what": label, "metres": v,
                    "travel": "On the plot" if v == 0 else travel(v),
                    "spelled": spell(v)})
    out.sort(key=lambda r: r["metres"])
    return out


STATUS_WORDS = {"available": "Available", "reserved": "Reserved",
                "deposit_paid": "Deposit paid", "sold": "Sold",
                "coming_soon": "Coming soon", "under_survey": "Under survey",
                "future_phase": "Future phase", "off_market": "Off market"}


def build_listing(intel, score=None, parcel=None, siblings=None):
    """PHASE 1 - the seller's website. Facts, not verdicts. See the banner.

    Never raises on a blocked parcel and never renders a refusal. If the
    scorer declined to rate this plot, the panel simply carries no score and
    says nothing about why - THAT conversation is ours to have with the
    seller directly, not something to print on their listing in front of
    their buyer.
    """
    i, s_, p = dict(intel or {}), dict(score or {}), dict(parcel or {})
    bd = _j(s_.get("score_breakdown"))

    rep = {
        "ref": p.get("parcel_ref"),
        "project": p.get("project_name"),
        # THE SELLER'S FIGURE, and only the seller's. No geometry fallback.
        "size": acres(p.get("area_sqm")),
        "status": STATUS_WORDS.get(p.get("listing_status")),
        "price": (f"KSh {float(p['price_kes']):,.0f}"
                  if p.get("price_kes") else None),
        "score": None,
        "facts": [c for c in (_soil_card(i), _rain_card(i),
                              _flood_card(i), _ground_card(i)) if c],
        "access": _rows(i, ACCESS_FIELDS),
        "amenities": _rows(i, AMENITY_FIELDS),
        "landmarks": _landmarks(i),
        "network": {
            "has_4g": (i.get("coverage_4g_pct") is not None
                       and float(i["coverage_4g_pct"]) >= 50),
            "has_2g": (i.get("coverage_2g_pct") is not None
                       and float(i["coverage_2g_pct"]) >= 50),
            "mast": (spell(i["dist_tower_m"])
                     if i.get("dist_tower_m") is not None else None),
        },
        "scheme": siblings or [],
        "footer": "Distances and ground conditions on this page are measured "
                  "from satellite images, terrain and rainfall records.",
        "generated_from": {"intelligence_version": i.get("version"),
                           "score_version": s_.get("version")},
    }

    # A blocked parcel loses its score and gains NOTHING ELSE. No red panel,
    # no stated reason, no "not rated" badge that a buyer would read as a
    # warning. The absence is the whole treatment.
    if not bd.get("blocked") and s_.get("overall_score") is not None:
        v = float(s_["overall_score"])
        best = bd.get("best_use")
        rep["score"] = {
            "value": v,
            "label": "Good" if v >= 75 else "Fair" if v >= 55 else "Poor",
            "use_line": ("Best suited to %s" % USE_WORDS[best]
                         if best in USE_WORDS else None),
            "by_use": {k: (None if s_.get(k + "_score") is None
                           else round(float(s_[k + "_score"])))
                       for k in ("residential", "agricultural",
                                 "commercial", "investment")},
        }

    return assert_no_geometry(rep, "listing")
