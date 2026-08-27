r"""
============================================================================
VERIFY THE SUITABILITY SCORES
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHAT THIS CHECKS, AND WHY EACH CHECK EXISTS

  A. BLOCKING BEHAVES AS BLOCKING. A parcel inside a protected area, or one
     whose boundary we do not trust, must come back with NULL scores and a
     stated reason - NOT a low number. A low number invites a comparison
     ("12 is worse than 15") that must never be made about land which is not
     for sale, or about ground we cannot locate.

     This is the check most likely to rot: it is easy to "improve" the model
     later by giving blocked parcels a floor value, and that would be a
     regression wearing the clothes of a fix.

  B. THE BREAKDOWN RECONSTRUCTS THE SCORE. Every component's points must sum
     to the score it explains, and the renormalised weights must sum to 1.
     If they do not, the breakdown is decoration rather than evidence - and
     the breakdown is the thing being sold.

     AMENDED AFTER ITS FIRST RUN, and the amendment is the point. This check
     failed on six scores - every one of them capped. It was right to fail:
     the components of a capped score sum to the UNCAPPED figure, because a
     cap is a separate stated operation and not a contribution.

     The check was written before caps existed and nobody updated it. So it
     now verifies BOTH halves - components must reconstruct `uncapped_score`,
     AND the published score must equal the tightest ceiling that fired. That
     is a stronger check than the original, not a relaxed one: it would now
     also catch a cap applied at the wrong value, which the first version
     could not see at all.

  C. ORDERINGS. Same reasoning as the enrichment verifier: an absolute
     threshold on an uncalibrated score is a guess, and when it fails you
     cannot tell whether the model broke or the threshold was always wrong.
     An inverted ORDER has one explanation.

  D. NO SCORE OUTRUNS ITS EVIDENCE. A score whose confidence is 0 must be
     NULL, a score with missing components must not claim confidence 4, and
     nothing may claim confidence 5 - nothing here is fitted to sale prices.

REQUIRES a real (non-dry) scoring run first:
  python score_01_suitability.py

How to run:
  python verify_02_suitability.py
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

# (field, must_be_higher, must_be_lower, why)
ORDERINGS = [
    ("residential_score", "TEST-KAREN-01", "TEST-LODWAR-01",
     "Prime Nairobi residential against an arid town on a flood-prone river. "
     "If this inverts, the flood cap or the slope term is wired backwards."),
    ("agricultural_score", "TEST-KANO-01", "TEST-LODWAR-01",
     "1,564 mm of rain a year on the Kano plains against 211 mm at Lodwar. "
     "The widest true gap in the set that does not involve a blocked parcel."),
    ("commercial_score", "TEST-KAREN-01", "TEST-KITENGELA-01",
     "Nairobi suburb against low-density Kajiado rangeland - population, "
     "paved road and existing development all point the same way."),
]

# Parcels that MUST come back unscored, and the rule that must catch them.
MUST_BLOCK = {
    "TEST-TANADELTA-01": "protected area",
    "TEST-KAKAMEGA-01":  "protected area",
    "TEST-ABERDARES-01": "protected area",
}


def main():
    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")

    # p.status = 'active' — same defect, same reason as verify_01.
    #
    # A superseded or withdrawn parcel keeps its parcel_id and keeps its score;
    # only the land.parcels row changes status. Scoring a plot is not undone
    # when the plot stops being for sale, because a report already sold has to
    # keep resolving. So s.status alone returns scores for parcels nobody can
    # buy, and returns two rows for any parcel_ref that was re-loaded — the
    # old version's score and the new one, colliding in the dict below.
    #
    # score_01_suitability.py already filters on both. This reader did not.
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.parcel_ref, s.*
              FROM analytics.suitability_scores s
              JOIN land.parcels p ON p.parcel_id = s.parcel_id
             WHERE s.status = 'active' AND p.status = 'active'
             ORDER BY p.parcel_ref
        """)).mappings().all()
    if not rows:
        sys.exit("No scores. Run:  python score_01_suitability.py")

    # Control, not a reminder: one live score per live parcel, or stop.
    seen = {}
    for r in rows:
        seen.setdefault(r["parcel_ref"], []).append(r["parcel_id"])
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    if dupes:
        for ref, pids in sorted(dupes.items()):
            print(f"  {ref}: parcel_ids {', '.join(str(p) for p in pids)}")
        sys.exit("ABORT: more than one active score per parcel_ref. Two "
                 "versions of the same parcel are live at once. Fix that "
                 "before trusting any result here.")

    data = {}
    for r in rows:
        r = dict(r)
        bd = r["score_breakdown"]
        r["bd"] = json.loads(bd) if isinstance(bd, str) else (bd or {})
        data[r["parcel_ref"]] = r

    print("=" * 76)
    print(f"SUITABILITY VERIFICATION — {len(data)} parcel(s)")
    print("=" * 76)
    npass = nfail = 0
    failures = []

    # ---- A. blocking ------------------------------------------------------
    print("\nA. BLOCKING MUST BLOCK, NOT SCORE LOW\n")
    for ref, r in sorted(data.items()):
        blk = r["bd"].get("blocked")
        scored = [k for k in ("residential_score", "agricultural_score",
                              "commercial_score", "investment_score",
                              "overall_score") if r.get(k) is not None]
        if blk:
            if scored:
                nfail += 1
                print(f"   FAIL  {ref:22} blocked ({blk['rule']}) but still "
                      f"carries {', '.join(scored)}")
                failures.append((ref, "blocked parcel scored", scored, "NULL",
                                 "A blocked parcel with a number invites the "
                                 "comparison the block exists to prevent."))
            else:
                npass += 1
                print(f"   PASS  {ref:22} blocked — {blk['rule']}, all scores "
                      f"NULL")
        elif ref in MUST_BLOCK:
            nfail += 1
            print(f"   FAIL  {ref:22} was NOT blocked; expected "
                  f"'{MUST_BLOCK[ref]}'")
            failures.append((ref, "should be blocked", "scored",
                             MUST_BLOCK[ref],
                             "This parcel is not saleable or not locatable. "
                             "Scoring it is the failure."))
    for ref, rule in MUST_BLOCK.items():
        if ref not in data:
            print(f"   SKIP  {ref:22} not present in this run")

    # ---- B. the breakdown reconstructs the score --------------------------
    print("\nB. THE BREAKDOWN MUST RECONSTRUCT THE SCORE\n")
    checked = capped = 0
    for ref, r in sorted(data.items()):
        for kind, d in (r["bd"].get("scores") or {}).items():
            if d.get("score") is None:
                continue
            comps = d.get("components") or []
            pts = round(sum(c["points"] for c in comps), 1)
            wts = round(sum(c["weight"] for c in comps), 3)
            caps = d.get("caps_applied") or []
            # A capped score's components reconstruct the UNCAPPED figure.
            target = d.get("uncapped_score", d["score"]) if caps else d["score"]
            ok_pts = abs(pts - target) <= 0.3
            ok_wts = abs(wts - 1.0) <= 0.01
            ok_cap = True
            if caps:
                ceiling = min(c["ceiling"] for c in caps)
                expected = min(d["uncapped_score"], ceiling)
                ok_cap = abs(d["score"] - expected) <= 0.05
                capped += 1
            checked += 1
            if ok_pts and ok_wts and ok_cap:
                npass += 1
            else:
                nfail += 1
                what = ("cap arithmetic" if not ok_cap
                        else "components do not sum")
                print(f"   FAIL  {ref:20} {kind:13} {what}: points {pts} vs "
                      f"target {target}, score {d['score']}, weights {wts}")
                failures.append((ref, kind, f"pts {pts} / score {d['score']}",
                                 f"{target} / capped correctly",
                                 "If the components do not add up to the "
                                 "score, the breakdown is decoration and the "
                                 "breakdown is what we sell."))
    print(f"   {checked} score(s) checked — components reconstruct the "
          f"uncapped figure, weights sum to 1")
    print(f"   {capped} of them were capped, and the ceiling arithmetic was "
          f"checked too")

    # ---- C. orderings -----------------------------------------------------
    print("\nC. ORDERINGS THAT MUST HOLD\n")
    for field, hi_ref, lo_ref, why in ORDERINGS:
        hi, lo = data.get(hi_ref), data.get(lo_ref)
        a = hi.get(field) if hi else None
        b = lo.get(field) if lo else None
        if a is None or b is None:
            # A blocked parcel on either side makes the ordering meaningless,
            # not failed. Say which, so a NULL is never read as a zero.
            why_null = []
            for ref, v in ((hi_ref, a), (lo_ref, b)):
                if v is None:
                    blk = (data.get(ref) or {}).get("bd", {}).get("blocked")
                    why_null.append(f"{ref.replace('TEST-','')}="
                                    + (f"blocked/{blk['rule']}" if blk
                                       else "not scored"))
            print(f"   SKIP  {field:20} {', '.join(why_null)}")
            continue
        a, b = float(a), float(b)
        if a > b:
            npass += 1
            print(f"   PASS  {field:20} {hi_ref.replace('TEST-','')} {a:g} > "
                  f"{lo_ref.replace('TEST-','')} {b:g}")
        else:
            nfail += 1
            print(f"   FAIL  {field:20} {hi_ref.replace('TEST-','')} {a:g} is "
                  f"NOT > {lo_ref.replace('TEST-','')} {b:g}  <- INVERTED")
            failures.append((f"{hi_ref} vs {lo_ref}", field, a, f"> {b}", why))

    # ---- D. no score outruns its evidence ---------------------------------
    print("\nD. NO SCORE OUTRUNS ITS EVIDENCE\n")
    issues = 0
    for ref, r in sorted(data.items()):
        for kind, d in (r["bd"].get("scores") or {}).items():
            c, s, miss = d.get("confidence"), d.get("score"), d.get("missing")
            if s is not None and c == 0:
                issues += 1
                nfail += 1
                print(f"   FAIL  {ref:20} {kind:13} has a score with "
                      f"confidence 0")
                failures.append((ref, kind, s, "NULL at confidence 0",
                                 "Confidence 0 means the inputs were not "
                                 "there."))
            if s is not None and miss and c is not None and c >= 4:
                issues += 1
                nfail += 1
                print(f"   FAIL  {ref:20} {kind:13} claims confidence {c} "
                      f"while missing {len(miss)} component(s)")
                failures.append((ref, kind, f"confidence {c}", "<= 3",
                                 "Missing inputs must cost confidence."))
            if c is not None and c >= 5:
                issues += 1
                nfail += 1
                print(f"   FAIL  {ref:20} {kind:13} claims confidence 5 — "
                      f"nothing here is fitted to sale prices")
                failures.append((ref, kind, f"confidence {c}", "<= 4",
                                 "Confidence 5 would claim calibration we do "
                                 "not have."))
    if not issues:
        print("   None. Every score is within the confidence its inputs "
              "support.")

    # ---- verdict ----------------------------------------------------------
    print("\n" + "=" * 76)
    print(f"{npass} passed, {nfail} FAILED")
    if nfail:
        print("\nFAILURES:")
        for ref, field, got, want, why in failures:
            print(f"  {ref} / {field}: got {got}, expected {want}")
            print(f"    WHY IT MATTERS: {why}")
        print("\nBefore changing the model, CHECK THE TEST. More than one")
        print("failure in this project has been in the verification.")
    else:
        print("\nAll suitability checks hold.")
    print("=" * 76)
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
