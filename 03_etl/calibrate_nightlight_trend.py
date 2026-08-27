r"""
============================================================================
CALIBRATION - choosing a development metric for demographics.nightlights
Land Intelligence Platform - Geocode Spatial Solutions Ltd

READ-ONLY. Writes nothing. Reads demographics.nightlights_stats only, so it
needs no raster and no download.

THE PROBLEM
  verify_26 passed every check and the trend was still unusable:

      median ward trend   33.19 %/yr   -> 11x brightening over 9 years
      fastest ten wards   214-252 %/yr -> 3.5x per year
      and they were Homa Bay, Migori, Kisii, Kakamega -- not the peri-urban
      corridors the product is about

  The cause is the metric, not the data. trend_pct_yr is a log-linear fit on
  radiance_sum with a 0.01 floor, so a ward moving from 0.002 to 0.05
  nW/cm2/sr -- still dark, an absolutely trivial change -- reads as enormous
  compound growth. PERCENTAGE GROWTH FROM A NEAR-ZERO BASE IS UNBOUNDED.

  The direction is probably real: that western belt is where Kenya's Last
  Mile Connectivity Project reached rural households. But a number that
  ranks a hamlet's first streetlights above Kiambu adding an estate is the
  wrong answer to "is this area developing" for a land buyer.

THREE CANDIDATES, COMPARED HONESTLY
  A. LOG GROWTH (current): % per year in radiance_sum.
     Scale-free, standard in the literature, explodes from a dark base.
  B. ABSOLUTE CHANGE: radiance_sum per year, in raw units.
     Cannot explode. Biased toward already-bright places, which for "where
     is value moving" is arguably correct rather than a flaw.
  C. LIT-AREA POINTS: change in lit_area_pct, in PERCENTAGE POINTS per year.
     Bounded 0-100 by construction, directly interpretable ("this ward went
     from 12% lit to 34% lit"), and immune to the near-zero problem because
     the denominator is ward area, not radiance.

  Each is also tested with a BASELINE FLOOR: units too dark in the first
  year are excluded, because a rate of change needs something to change from.

HOW TO READ THE OUTPUT
  The decisive panel is the top-ten ward list for each metric. A credible
  development ranking for this product contains peri-urban wards around
  Nairobi, Kiambu, Nakuru, Eldoret, Kisumu, Mombasa, or SGR/highway
  corridors. If a metric's top ten is rural wards that started dark, it is
  measuring electrification, not land-value movement. Both are real; only
  one answers the question the catalogue asks.

  IF NO VARIANT PRODUCES A CREDIBLE RANKING, the honest outcome is to NULL
  trend_pct_yr and ship the levels alone. The levels are verified sound
  (lit area rises 1.8% -> 97.3% across density quintiles, Nairobi brightest,
  ASAL darkest). A missing column is better than a confident wrong one.

How to run (from 03_etl with venv active):
  python calibrate_nightlight_trend.py
============================================================================
"""

import os
import sys
from pathlib import Path

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
TOP_N = 12


def main():
    load_dotenv(BASE / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit("ERROR: set DB_PASSWORD in .env first.")
    url = (f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
           f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
           f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")
    engine = create_engine(url)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT n.admin_code, n.period, n.radiance_sum, n.lit_area_pct,
                   w.name AS ward, k.name AS county
            FROM demographics.nightlights_stats n
            LEFT JOIN admin.wards w
              ON COALESCE(w.ward_code, 'LIP-W' || w.id::text) = n.admin_code
            LEFT JOIN admin.counties k ON k.county_code = w.county_code
            WHERE n.admin_level = 'ward'
            ORDER BY n.admin_code, n.period
        """)).fetchall()
    if not rows:
        sys.exit("No ward rows in demographics.nightlights_stats.")

    units = {}
    for code, period, rsum, lit, ward, county in rows:
        u = units.setdefault(code, {"ward": ward, "county": county, "s": {}})
        u["s"][int(period)] = (float(rsum or 0.0), float(lit or 0.0))
    years = sorted({y for u in units.values() for y in u["s"]})
    y0, y1 = years[0], years[-1]
    span = y1 - y0
    print(f"{len(units):,} wards, years {years}, span {span} yr")

    # ---------------------------------------------------------------- 1.
    # PRINT THE BACKGROUND DISTRIBUTION BEFORE SETTING ANY THRESHOLD.
    # Rule from session 5, and the reason the current metric was never
    # sanity-checked: nobody looked at how dark the dark end actually is.
    base = np.array([u["s"].get(y0, (0.0, 0.0))[0] for u in units.values()])
    print("\nBASELINE radiance_sum in the first year, across wards")
    ps = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    print("  percentile " + "".join(f"{p:>10}%" for p in ps))
    print("  value      " + "".join(f"{v:>11.2f}"
                                    for v in np.percentile(base, ps)))
    print(f"  wards at exactly 0.00 : {int((base <= 0).sum()):,}")
    print(f"  wards under 1.00      : {int((base < 1).sum()):,}")
    print(f"  wards under 10.00     : {int((base < 10).sum()):,}")

    # ---------------------------------------------------------------- 2.
    def metrics(code, u, floor):
        a = u["s"].get(y0)
        b = u["s"].get(y1)
        if a is None or b is None:
            return None
        r0, l0 = a
        r1, l1 = b
        if r0 < floor:
            return None
        out = {"ward": u["ward"], "county": u["county"],
               "r0": r0, "r1": r1, "l0": l0, "l1": l1}
        out["B"] = (r1 - r0) / span
        out["C"] = (l1 - l0) / span
        out["A"] = (((r1 / r0) ** (1.0 / span) - 1.0) * 100.0
                    if r0 > 0 else None)
        return out

    FLOORS = [0.0, 1.0, 10.0, 50.0]
    NAMES = {"A": "log growth %/yr", "B": "absolute rad/yr",
             "C": "lit-area points/yr"}

    print("\n" + "=" * 76)
    print("HOW MANY WARDS SURVIVE EACH BASELINE FLOOR, and what the "
          "distribution looks like")
    print(f"{'floor':>8}{'wards':>8}"
          + "".join(f"{'med ' + k:>20}" for k in ("A", "B", "C")))
    for f in FLOORS:
        m = [metrics(c, u, f) for c, u in units.items()]
        m = [x for x in m if x]
        if not m:
            continue
        med = {}
        for k in ("A", "B", "C"):
            vals = [x[k] for x in m if x[k] is not None]
            med[k] = float(np.median(vals)) if vals else float("nan")
        print(f"{f:>8.1f}{len(m):>8,}"
              + f"{med['A']:>20.1f}{med['B']:>20.2f}{med['C']:>20.2f}")

    # ---------------------------------------------------------------- 3.
    # THE DECIDING PANEL. Names, not numbers.
    print("\n" + "=" * 76)
    print("TOP WARDS BY EACH METRIC (floor 1.0). Judge these by whether you")
    print("recognise them as places where land value is moving.")
    m = [x for x in (metrics(c, u, 1.0) for c, u in units.items()) if x]
    for key in ("A", "B", "C"):
        vals = [x for x in m if x[key] is not None]
        vals.sort(key=lambda x: x[key], reverse=True)
        print(f"\n  --- {NAMES[key]} " + "-" * (58 - len(NAMES[key])))
        print(f"  {'ward':24}{'county':16}{'value':>10}"
              f"{'lit ' + str(y0):>10}{'lit ' + str(y1):>10}")
        for x in vals[:TOP_N]:
            print(f"  {str(x['ward'])[:22]:24}{str(x['county'] or '-')[:14]:16}"
                  f"{x[key]:>10.1f}{x['l0']:>10.1f}{x['l1']:>10.1f}")

    # ---------------------------------------------------------------- 4.
    # Do the metrics even agree? If A and C rank completely different places,
    # they are answering different questions and the choice is substantive.
    print("\n" + "=" * 76)
    ranks = {}
    for key in ("A", "B", "C"):
        vals = [x for x in m if x[key] is not None]
        vals.sort(key=lambda x: x[key], reverse=True)
        ranks[key] = [id(x) for x in vals]
    for k1, k2 in (("A", "B"), ("A", "C"), ("B", "C")):
        s1 = set(ranks[k1][:50])
        s2 = set(ranks[k2][:50])
        print(f"  top-50 overlap, {NAMES[k1]} vs {NAMES[k2]}: "
              f"{len(s1 & s2)}/50")
    print("  Low overlap is not a bug. It means the metrics answer different")
    print("  questions, and the choice below is a product decision.")

    print("\nWHAT TO DECIDE")
    print("  1. Which metric's top list looks like Kenyan land-value movement?")
    print("  2. What floor removes the near-zero explosion without discarding")
    print("     real peri-urban growth?")
    print("  3. If none of them look right, NULL trend_pct_yr and ship the")
    print("     levels alone. They are verified; a wrong trend is worse than")
    print("     an absent one.")


if __name__ == "__main__":
    main()
