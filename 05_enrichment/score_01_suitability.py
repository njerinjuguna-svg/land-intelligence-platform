r"""
============================================================================
SUITABILITY SCORING v0.1
Land Intelligence Platform - Geocode Spatial Solutions Ltd

Reads analytics.parcel_intelligence, writes analytics.suitability_scores.

THE BREAKDOWN IS THE PRODUCT. THE SCORE IS THE INDEX TO IT.
  A score without its components is a number nobody can argue with, and in
  this market that is a liability, not a feature. A buyer told "62/100" can
  only accept or reject it. A buyer told "62, and here is the flood class,
  the slope, the soil and what each contributed" can DISAGREE WITH US - and
  a number a client can check is the only kind worth selling.

  So score_breakdown carries, for every score: each component, its raw
  value, the points it contributed, the weight, the confidence, the caveats
  that must be displayed alongside it, and anything that was missing. It is
  built to render directly as the buyer-facing card, field for field.

A BLOCKING FINDING IS NOT A LOW SCORE. THIS IS THE CENTRAL RULE.
  Land inside a gazetted protected area is not "12/100 residential". It is
  NOT FOR SALE, and scoring it 12 invites somebody to rank it against a 15
  and conclude it is merely worse. The same holds for a parcel whose
  boundary we do not trust: every number would be computed on the wrong
  ground.

  Those parcels get NULL scores and a stated reason. Refusing to score is a
  product feature; it is the same instinct that made the engine refuse an
  NDVI value with a missing scale tag.

WEIGHTS ARE A PRODUCT JUDGEMENT AND ARE LABELLED AS ONE.
  Nothing here is calibrated against sale prices - we have none. Every
  weight below is an opinion about what a Kenyan land buyer cares about,
  written down where it can be argued with and changed. They are NOT
  measurements and the breakdown says so on every row.

  When transaction data exists, these become fittable. Until then the
  honest position is: the components are measured, the weighting is ours.

MISSING INPUTS LOWER CONFIDENCE. THEY NEVER SILENTLY SCORE MID.
  A component with no data is dropped and the remaining weights are
  renormalised, the omission is listed in `missing`, and the score's
  confidence falls. Substituting a neutral 0.5 would let an absence
  masquerade as an average - the exact failure the enrichment engine
  refuses everywhere else.

How to run (from 05_enrichment, with the 03_etl venv active):
  python score_01_suitability.py --dry-run
  python score_01_suitability.py
  python verify_02_suitability.py
============================================================================
"""

import os
import sys
import json

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV_DIR = BASE.parent / "03_etl"
MODEL_VERSION = "0.1.0-judgement"

# A parcel below this confidence is NOT SCORED. PLOT-950 sits at 3: its
# boundary was repaired at load and six independent layers disagree with its
# neighbours. Scoring it would price ground that is not the plot.
MIN_PARCEL_CONFIDENCE = 4

FLOOD_QUALITY = {"very_low": 1.00, "low": 0.80, "moderate": 0.45,
                 "high": 0.15, "very_high": 0.00, "permanent_water": 0.00}

# ---------------------------------------------------------------------------
# THE WEIGHTS. Opinions, written where they can be argued with.
# Each entry: (component key, weight, human label)
# ---------------------------------------------------------------------------
WEIGHTS = {
    "residential": [
        ("flood",        0.28, "Flood hazard"),
        ("slope",        0.16, "Ground slope"),
        ("black_cotton", 0.16, "Foundation soil"),
        ("road",         0.14, "Road access"),
        ("services",     0.14, "Schools and health nearby"),
        ("connectivity", 0.12, "Mobile coverage"),
    ],
    "agricultural": [
        ("rainfall",     0.30, "Rainfall"),
        ("drought",      0.18, "Drought exposure"),
        ("ndvi",         0.18, "Vegetation vigour"),
        ("soil_ph",      0.14, "Soil pH"),
        ("slope_farm",   0.12, "Workable slope"),
        ("water_point",  0.08, "Water point nearby"),
    ],
    "commercial": [
        ("paved_road",   0.30, "Paved road access"),
        ("population",   0.24, "People nearby"),
        ("built",        0.18, "Existing development"),
        ("connectivity", 0.16, "Mobile coverage"),
        ("flood",        0.12, "Flood hazard"),
    ],
    "investment": [
        ("nl_trend",     0.34, "Growth in night-time light"),
        ("built",        0.20, "Existing development"),
        ("paved_road",   0.18, "Paved road access"),
        ("population",   0.16, "People nearby"),
        ("flood",        0.12, "Flood hazard"),
    ],
}

# ---------------------------------------------------------------------------
# CAPS. SOME COMPONENTS ARE GATES, NOT CONTRIBUTIONS.
#
# The first run of this model gave TEST-LODWAR-01 a residential score of 54
# while its flood class was VERY HIGH. The arithmetic was right - flood carries
# 0.28 of the residential weight, so it can only ever remove 28 points, and
# good road access and coverage made the rest back.
#
# THE WEIGHT WAS NOT TOO LOW; THE SHAPE WAS WRONG. A buyer looking for a
# homesite does not trade flood risk against mobile coverage. Past a point the
# hazard decides the answer and the other components stop mattering, which is
# a CEILING, not a smaller addend. Raising the weight instead would have been
# the E6 mistake: tuning a constant when the model is what is wrong.
#
# A cap is always recorded in the breakdown, with what it cut and why, so it
# can be argued with rather than discovered.
CAPS = {
    "residential": [
        (lambda r: r.get("flood_risk_class") == "very_high", 35,
         "Very high flood class over a material share of the parcel"),
        (lambda r: r.get("flood_risk_class") == "high", 55,
         "High flood class over a material share of the parcel"),
        (lambda r: r.get("in_riparian_buffer") is True, 45,
         "Part of this parcel is inside a riparian reserve, which cannot be "
         "built on"),
    ],
    "commercial": [
        (lambda r: r.get("flood_risk_class") == "very_high", 50,
         "Very high flood class over a material share of the parcel"),
    ],
    "agricultural": [],
    "investment": [
        (lambda r: r.get("flood_risk_class") == "very_high", 55,
         "Very high flood class over a material share of the parcel"),
    ],
}

CAVEAT = {
    "flood": "Flood hazard is MODELLED from terrain, not measured from flood "
             "records. It cannot see dike or drain failure and is not a "
             "substitute for a site visit.",
    "black_cotton": "Where the soil check reads 'none' on flat peri-urban land "
                    "around Nairobi it is INCONCLUSIVE, not a clean bill. "
                    "Checklist C16.",
    "rainfall": "This rainfall layer runs about 145 mm wet. Use it to compare "
                "places, not as a calibrated total.",
    "ndvi": "Vegetation is a single year (2024), not an average, and 2024 was "
            "wet after the 2020-23 drought.",
    "population": "Population is MODELLED, not a census count: +16% against "
                  "the 2019 census nationally. Prefer comparisons to figures.",
    "nl_trend": "Night-light trend is a SUM and scales with the size of the "
                "ward. Compare directions of travel, never rank a large ward "
                "against a small one on it.",
    "connectivity": "Mobile coverage is a percentage for the surrounding "
                    "SUBLOCATION, not a property of this parcel.",
    "services": "Health facilities sit at ward centroids, not true GPS. These "
                "distances are accurate to roughly the size of a ward.",
}


def band(v, lo, hi, invert=False):
    """Linear 0..1 between lo and hi, clamped. Deliberately not a curve.

    A smooth curve would imply a precision none of these inputs have. A
    straight ramp between two stated endpoints is arguable, which is the
    property we want.
    """
    if v is None:
        return None
    v = float(v)
    q = (v - lo) / (hi - lo)
    q = max(0.0, min(1.0, q))
    return 1.0 - q if invert else q


def components(r):
    """Every component as (quality 0..1 or None, displayed raw value).

    Returning None - rather than a default - is what makes a missing input
    visible downstream instead of average.
    """
    fc = r.get("flood_risk_class")
    bc = r.get("black_cotton_risk")
    # C16: 'none' is not evidence of absence on flat ground near Nairobi.
    # It is scored as UNKNOWN there, not as good news.
    bc_q = None
    if bc == "likely":
        bc_q, bc_txt = 0.25, "likely black cotton"
    elif bc == "none":
        flat = (r.get("slope_mean_pct") is not None
                and float(r["slope_mean_pct"]) < 3.5)
        if flat:
            bc_q, bc_txt = None, "inconclusive (C16 - flat ground)"
        else:
            bc_q, bc_txt = 1.0, "no black cotton indicated"
    else:
        bc_txt = str(bc)

    return {
        "flood":        (FLOOD_QUALITY.get(fc), fc),
        "slope":        (band(r.get("slope_mean_pct"), 15.0, 1.0),
                         None if r.get("slope_mean_pct") is None
                         else f"{r['slope_mean_pct']}°"),
        "black_cotton": (bc_q, bc_txt),
        "road":         (band(r.get("dist_any_road_m"), 3000.0, 0.0),
                         _m(r.get("dist_any_road_m"))),
        "paved_road":   (band(r.get("dist_paved_road_m"), 15000.0, 0.0),
                         _m(r.get("dist_paved_road_m"))),
        "services":     (_services(r)),
        "connectivity": (band(r.get("coverage_4g_pct"), 40.0, 100.0),
                         None if r.get("coverage_4g_pct") is None
                         else f"{float(r['coverage_4g_pct']):.0f}% 4G"),
        "rainfall":     (band(r.get("rainfall_normal_mm_yr"), 350.0, 1200.0),
                         None if r.get("rainfall_normal_mm_yr") is None
                         else f"{r['rainfall_normal_mm_yr']} mm/yr"),
        "drought":      (band(r.get("rainfall_driest_year_pct"), 50.0, 100.0),
                         None if r.get("rainfall_driest_year_pct") is None
                         else f"driest year {r['rainfall_driest_year_pct']}% "
                              f"of normal"),
        "ndvi":         (band(r.get("ndvi_mean"), 0.15, 0.70),
                         None if r.get("ndvi_mean") is None
                         else f"NDVI {r['ndvi_mean']}"),
        "soil_ph":      (_ph(r.get("soil_ph"))),
        "slope_farm":   (band(r.get("slope_mean_pct"), 12.0, 0.5),
                         None if r.get("slope_mean_pct") is None
                         else f"{r['slope_mean_pct']}°"),
        "water_point":  (band(r.get("dist_water_point_m"), 8000.0, 0.0),
                         _m(r.get("dist_water_point_m"))),
        "population":   (band(r.get("pop_density_km2"), 20.0, 1500.0),
                         None if r.get("pop_density_km2") is None
                         else f"{r['pop_density_km2']} /km² (ward)"),
        "built":        (band(r.get("built_up_pct_1km"), 0.0, 25.0),
                         None if r.get("built_up_pct_1km") is None
                         else f"{r['built_up_pct_1km']}% built within 1 km"),
        "nl_trend":     (band(r.get("nightlights_trend_radiance_yr"),
                              0.0, 250.0),
                         None if r.get("nightlights_trend_radiance_yr") is None
                         else f"+{float(r['nightlights_trend_radiance_yr']):.0f}"
                              f"/yr (ward)"),
    }


def _m(v):
    if v is None:
        return None
    v = float(v)
    if v == 0.0:
        return "on this parcel"      # D18: containment, not a small distance
    return f"{v/1000:.1f} km" if v >= 1000 else f"{v:.0f} m"


def _ph(v):
    if v is None:
        return None, None
    v = float(v)
    # Most crops want 5.5-7.5. Score distance from the middle of that band.
    q = 1.0 - min(1.0, abs(v - 6.5) / 2.0)
    return q, f"pH {v}"


def _services(r):
    parts = [band(r.get("dist_primary_school_m"), 10000.0, 0.0),
             band(r.get("dist_clinic_m"), 15000.0, 0.0)]
    have = [p for p in parts if p is not None]
    if not have:
        return None, None
    return (sum(have) / len(have),
            f"school {_m(r.get('dist_primary_school_m'))}, "
            f"clinic {_m(r.get('dist_clinic_m'))}")


def score_one(kind, r, comp):  # noqa: C901
    """-> (score 0..100 or None, breakdown dict).

    Weights of components with no data are REDISTRIBUTED across the rest and
    the omission is named. The alternative - scoring a missing input at 0.5 -
    lets an absence read as an average, which is the one thing this project
    consistently refuses.
    """
    rows, missing, live = [], [], 0.0
    for key, w, label in WEIGHTS[kind]:
        q, raw = comp[key]
        if q is None:
            missing.append(label + (f" ({raw})" if raw else ""))
            continue
        live += w
        rows.append({"component": label, "value": raw, "weight": w,
                     "quality": round(q, 3)})
    if not rows or live < 0.5:
        # Less than half the weight has data. A number here would be a guess
        # wearing a decimal point.
        return None, {"score": None, "confidence": 0,
                      "refused": f"only {live:.0%} of the weighting had data",
                      "components": rows, "missing": missing}
    total = 0.0
    for row in rows:
        row["weight"] = round(row["weight"] / live, 3)   # renormalised
        row["points"] = round(100.0 * row["weight"] * row["quality"], 1)
        total += row["points"]
    # Confidence falls with missing weight, and is never above 4: nothing here
    # is calibrated against a sale price.
    confidence = 4 if not missing else (3 if live >= 0.8 else 2)
    caveats = sorted({CAVEAT[k] for k, _, _ in WEIGHTS[kind] if k in CAVEAT
                      and comp[k][0] is not None})

    # Apply the tightest cap that fires, and say what it cost.
    uncapped, applied = round(total, 1), []
    for test, ceiling, why in CAPS.get(kind, []):
        try:
            if test(r):
                applied.append({"ceiling": ceiling, "reason": why})
        except BaseException:
            continue
    if applied:
        ceiling = min(a["ceiling"] for a in applied)
        if uncapped > ceiling:
            total = float(ceiling)
        else:
            total = uncapped

    out = {"score": round(total, 1), "confidence": confidence,
           "components": rows, "missing": missing, "caveats": caveats,
           "weighting_note": "Weights are a PRODUCT JUDGEMENT about what a "
                             "buyer values, not a measurement. Nothing here "
                             "is fitted to sale prices - we hold none."}
    if applied:
        out["caps_applied"] = applied
        out["uncapped_score"] = uncapped
        out["cap_note"] = ("A CEILING WAS APPLIED, not a deduction. Past this "
                           "point the constraint decides the answer and the "
                           "remaining components stop trading against it - "
                           "nobody weighs flood risk against mobile coverage. "
                           "The uncapped figure is shown so the cap can be "
                           "argued with.")
    return round(total, 1), out


def blocking(r):
    """Reasons this parcel must not be scored at all.

    NULL IS NOT FALSE, AND HERE THE DIFFERENCE IS THE WHOLE POINT.

    `if r.get("in_protected_area")` treats None and False identically, which
    is correct Python and wrong product. The engine now writes NULL when no
    commercially usable source covers the parcel AND a non-commercial one
    (WDPA) places it inside a park - "we do not know", not "it is clear".

    Reading that as clear ground would let a gazetted national park be
    scored, priced and listed. It nearly did: TEST-ABERDARES-01,
    TEST-KAKAMEGA-01 and TEST-TANADELTA-01 all flipped from blocked to
    scoreable in one run when the licence source changed underneath them.

    A blocking check must fail CLOSED. Any answer other than a confident
    False stops the score.
    """
    if r.get("in_protected_area") is None:
        return {"rule": "protected area unresolved",
                "reason": "We cannot currently establish whether this parcel "
                          "lies inside a gazetted protected area. The data "
                          "that would answer it is not licensed for use in a "
                          "commercial product, and no cleared source covers "
                          "this ground. An unresolved answer is not a clear "
                          "one, so the parcel is not scored.",
                "display": "Not rated — protected status unconfirmed"}
    if r.get("in_protected_area"):
        return {"rule": "protected area",
                "reason": "This parcel intersects a gazetted protected area. "
                          "Land inside one is normally not saleable, so a "
                          "score would invite a comparison that should never "
                          "be made.",
                "display": "Not for sale — protected land"}
    c = r.get("parcel_confidence")
    if c is not None and int(c) < MIN_PARCEL_CONFIDENCE:
        return {"rule": "boundary not trusted",
                "reason": f"The parcel is loaded at confidence {c}, below the "
                          f"scoring floor of {MIN_PARCEL_CONFIDENCE}. Every "
                          f"score would be computed on ground we are not "
                          f"confident is the plot.",
                "display": "Not rated — boundary unverified"}
    return None


def main():
    dry = "--dry-run" in sys.argv
    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")
    print(f"Suitability scoring {MODEL_VERSION}")

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.parcel_ref, p.confidence AS parcel_confidence, i.*
              FROM analytics.parcel_intelligence i
              JOIN land.parcels p ON p.parcel_id = i.parcel_id
             WHERE i.status = 'active' AND p.status = 'active'
             ORDER BY p.parcel_ref
        """)).mappings().all()
    if not rows:
        sys.exit("No enrichment rows. Run: python enrich_01_engine.py")
    print(f"{len(rows)} parcel(s)\n" + "=" * 74)

    written = blocked = 0
    try:
        for r in rows:
            r = dict(r)
            ref = r["parcel_ref"]
            block = blocking(r)
            comp = components(r)

            if block:
                blocked += 1
                scores = {k: None for k in WEIGHTS}
                breakdown = {"model_version": MODEL_VERSION,
                             "blocked": block, "best_use": None,
                             "scores": {}}
                print(f"{ref:22} BLOCKED — {block['rule']}")
            else:
                scores, detail = {}, {}
                for kind in WEIGHTS:
                    s, d = score_one(kind, r, comp)
                    scores[kind] = s
                    detail[kind] = d
                have = {k: v for k, v in scores.items() if v is not None}
                best = max(have, key=have.get) if have else None
                breakdown = {"model_version": MODEL_VERSION, "blocked": None,
                             "best_use": best,
                             "best_use_note": "The overall score is the "
                             "highest of the four, NOT their mean. Land is "
                             "bought for a purpose; averaging a strong "
                             "agricultural score against a weak commercial "
                             "one produces a number describing no buyer.",
                             "scores": detail}
                print(f"{ref:22} "
                      + "  ".join(f"{k[:4]} {('--' if v is None else f'{v:.0f}')}"
                                  for k, v in scores.items())
                      + f"   best: {best or '—'}")

            if dry:
                continue
            overall = None
            if not block:
                have = [v for v in scores.values() if v is not None]
                overall = max(have) if have else None
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE analytics.suitability_scores SET status='superseded'
                     WHERE parcel_id = :p AND status = 'active'"""),
                    {"p": r["parcel_id"]})
                nxt = conn.execute(text("""
                    SELECT coalesce(max(version),0)+1
                      FROM analytics.suitability_scores WHERE parcel_id = :p"""),
                    {"p": r["parcel_id"]}).scalar()
                conn.execute(text("""
                    INSERT INTO analytics.suitability_scores
                      (parcel_id, intel_id, residential_score,
                       agricultural_score, commercial_score, investment_score,
                       overall_score, score_breakdown, model_version, version)
                    VALUES (:pid, :iid, :res, :agr, :com, :inv, :ovr,
                            :bd, :mv, :v)"""),
                    {"pid": r["parcel_id"], "iid": r.get("intel_id"),
                     "res": scores.get("residential"),
                     "agr": scores.get("agricultural"),
                     "com": scores.get("commercial"),
                     "inv": scores.get("investment"), "ovr": overall,
                     "bd": json.dumps(breakdown, default=str),
                     "mv": MODEL_VERSION, "v": nxt})
            written += 1

        print("=" * 74)
        if dry:
            print(f"DRY RUN. {len(rows)} scored, nothing written. "
                  f"{blocked} blocked.")
        else:
            print(f"DONE. {written} row(s) written, {blocked} blocked.")
        print("\nNOW CHECK IT:  python verify_02_suitability.py")

    except BaseException:
        # BaseException, not Exception: a SystemExit guard must not slip past.
        raise


if __name__ == "__main__":
    main()
