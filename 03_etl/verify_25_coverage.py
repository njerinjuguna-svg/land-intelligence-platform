r"""
============================================================================
VERIFY 25 - connectivity.coverage against an independent producer
Land Intelligence Platform - Geocode Spatial Solutions Ltd

READ-ONLY. Writes nothing, changes nothing.

THE TEST THAT MATTERS: TWO PRODUCERS, ONE REALITY
  The strongest verification this project has run was SoilGrids Vertisols
  against iSDA texture: two organisations, different methods, neither aware
  of the other, forced to agree by physics. This is the same move.

  The CA says what share of each sublocation has coverage. OpenCellID holds
  142,279 crowdsourced cell observations that people's phones actually saw.
  Neither knows the other exists. A cell tower is observed BECAUSE a handset
  had signal there, so:

      sublocations the CA calls well covered should contain more towers
      per square kilometre than sublocations it calls poorly covered

  That relationship is not something we control and not something a
  misaligned or stale coverage layer would reproduce by accident. If it
  fails, the coverage polygons are in the wrong place, the wrong vintage, or
  the wrong thing entirely.

WHAT THIS CANNOT TELL US, stated so no one over-reads a pass
  - OpenCellID is crowdsourced, so it is dense where PEOPLE are, not where
    coverage is. Nairobi will look tower-rich for reasons of population as
    well as coverage. That biases the test TOWARD passing, which is why the
    gradient across coverage bands matters more than any single number.
  - Agreement does not establish that 4g is 4g. etl_25 found the CA's 3G and
    4G layers 99.9% identical and deleted the weaker one; if the survivor is
    the mislabelled one, this test cannot see that. Only the CA can answer it.
  - Coverage is a SUBLOCATION percentage. Nothing here validates any
    point-level claim, because the source never made one.

How to run (from 03_etl with venv active):
  python verify_25_coverage.py
============================================================================
"""

import os
import sys
from pathlib import Path

for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent

# URBAN LANDMARKS ONLY, AND HERE IS WHY THE REMOTE ONES WERE REMOVED.
# The first version of this test expected LOW coverage at Lodwar, North Horr
# and the Chalbi. Lodwar came back 75.6% and the Chalbi point resolved to a
# sublocation called KALACHA at 77.4%, and both were marked as failures.
# Both were the TEST being wrong.
#
# Sublocations are drawn around HABITATION. At this unit size there is no
# such thing as a remote polygon: any coordinate in an "empty" area falls
# inside a unit named for the nearest settlement, and settlements are exactly
# where masts go. Lodwar is Turkana's county capital with ~80,000 people.
# Expecting it to read low was asking the data to describe a geography it
# does not use, which is lesson 19 for the fourth time.
#
# So remoteness is now tested distributionally instead (see the arid-county
# check below), where it cannot be gamed by my choice of coordinate.
LANDMARKS = [
    ("Nairobi CBD",    36.8172, -1.2864),
    ("Mombasa Island", 39.6682, -4.0435),
    ("Kisumu town",    34.7617, -0.0917),
    ("Nakuru town",    36.0800, -0.3031),
    ("Eldoret town",   35.2698,  0.5143),
    ("Nyeri town",     36.9476, -0.4169),
]

# The ASAL counties. Kenya's arid and semi-arid lands, where sparse
# population and distance from the backbone make thin coverage expected.
ARID_COUNTIES = {"Turkana", "Marsabit", "Mandera", "Wajir", "Garissa",
                 "Isiolo", "Samburu", "Tana River", "West Pokot"}

failures = []


def check(name, ok, detail):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    if not ok:
        failures.append(name)


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
        print("WHAT IS ACTUALLY IN THE TABLE")
        rows = conn.execute(text("""
            SELECT technology, operator, count(*), min(confidence),
                   round(avg(coverage_pct)::numeric, 1),
                   round((percentile_cont(0.5) WITHIN GROUP
                          (ORDER BY coverage_pct))::numeric, 1),
                   min(source_date), max(source_date)
            FROM connectivity.coverage
            GROUP BY 1, 2 ORDER BY 1, 2
        """)).fetchall()
        print(f"  {'tech':6}{'operator':12}{'rows':>9}{'conf':>6}"
              f"{'mean%':>8}{'median%':>9}   vintage")
        for t, o, n, c, mean, med, d0, d1 in rows:
            span = str(d0) if d0 == d1 else f"{d0}..{d1}"
            print(f"  {t:6}{o:12}{n:>9,}{c:>6}{mean:>8}{med:>9}   {span}")
        if not rows:
            sys.exit("connectivity.coverage is empty. Run etl_25 first.")

        # --- 0. 3g must be absent -------------------------------------------
        techs = {r[0] for r in rows}
        check("the duplicated 3g layer is not in the table",
              "3g" not in techs,
              "3g absent" if "3g" not in techs else
              "3g PRESENT - it was 99.9% identical to 4g and must be removed")

        # --- 1. THE MAIN TEST: tower density across coverage bands ----------
        # Towers per 1,000 km2 of sublocation area, by CA coverage band.
        # A monotonic rise is the thing to look for; the absolute numbers are
        # not meaningful because OpenCellID is crowdsourced.
        print("\nTOWER DENSITY BY CA COVERAGE BAND  (4g, all operators)")
        band = conn.execute(text("""
            WITH cov AS (
                SELECT c.id, c.geom, c.coverage_pct,
                       CASE WHEN c.coverage_pct <  20 THEN '1. under 20%'
                            WHEN c.coverage_pct <  50 THEN '2. 20-50%'
                            WHEN c.coverage_pct <  80 THEN '3. 50-80%'
                            WHEN c.coverage_pct < 100 THEN '4. 80-100%'
                            ELSE '5. exactly 100%' END AS band
                FROM connectivity.coverage c
                WHERE c.technology = '4g' AND c.operator = 'all'
                  AND c.coverage_pct IS NOT NULL
            ), j AS (
                SELECT cov.band, cov.id,
                       ST_Area(cov.geom::geography) / 1e6 AS km2,
                       count(t.id) AS towers
                FROM cov LEFT JOIN connectivity.towers t
                       ON t.status = 'active' AND ST_Intersects(cov.geom, t.geom)
                GROUP BY cov.band, cov.id, cov.geom
            )
            SELECT band, count(*) AS units, round(sum(km2)::numeric, 0) AS km2,
                   sum(towers) AS towers,
                   round((1000.0 * sum(towers) / NULLIF(sum(km2), 0))::numeric, 1)
            FROM j GROUP BY band ORDER BY band
        """)).fetchall()
        print(f"  {'band':18}{'units':>8}{'km2':>12}{'towers':>10}"
              f"{'per 1000km2':>14}")
        dens = []
        for b, units, km2, towers, per in band:
            print(f"  {b:18}{units:>8,}{km2:>12,}{towers:>10,}{per:>14}")
            dens.append(float(per or 0))
        if len(dens) >= 3:
            rising = sum(1 for a, b2 in zip(dens, dens[1:]) if b2 >= a)
            check("tower density rises with CA coverage",
                  dens[-1] > dens[0] and rising >= len(dens) - 2,
                  f"{dens[0]} -> {dens[-1]} per 1,000 km2 "
                  f"({rising} of {len(dens)-1} steps non-decreasing)")

        # --- 2. Sublocations with towers but low reported coverage ---------
        # A tower inside a sublocation the CA calls under 20% covered is not
        # necessarily wrong (one mast on the edge of a huge arid unit), but a
        # LOT of them would mean the layer is stale or misplaced.
        odd = conn.execute(text("""
            SELECT count(*) FROM connectivity.coverage c
            WHERE c.technology='4g' AND c.operator='all'
              AND c.coverage_pct < 20
              AND EXISTS (SELECT 1 FROM connectivity.towers t
                          WHERE t.status='active'
                            AND ST_Intersects(c.geom, t.geom))
        """)).scalar()
        low = conn.execute(text("""
            SELECT count(*) FROM connectivity.coverage
            WHERE technology='4g' AND operator='all' AND coverage_pct < 20
        """)).scalar()
        check("most low-coverage sublocations have no tower in them",
              low == 0 or odd / low < 0.5,
              f"{odd:,} of {low:,} sublocations under 20% coverage "
              f"contain a tower ({100.0*odd/max(1,low):.1f}%)")

        # --- 3. Landmarks, read as the containing sublocation ---------------
        print("\nURBAN LANDMARKS (sublocation containing the point)")
        got, high = 0, 0
        for name, lon, lat in LANDMARKS:
            r = conn.execute(text("""
                SELECT admin_name, coverage_pct
                FROM connectivity.coverage
                WHERE technology='4g' AND operator='all'
                  AND ST_Contains(geom, ST_SetSRID(ST_Point(:lon,:lat),4326))
                LIMIT 1
            """), {"lon": lon, "lat": lat}).fetchone()
            if r is None:
                print(f"  {name:22}{'no polygon covers this point':>34}")
                continue
            got += 1
            sub, pct = r
            ok = pct >= 90
            high += 1 if ok else 0
            print(f"  {name:22}{str(sub)[:18]:20}{pct:>8.1f}%   "
                  f"{'ok' if ok else '<-- CHECK'}")
        check("every major town reads well covered", high == got and got,
              f"{high} of {got} town sublocations at 90%+")

        # --- 3b. REMOTENESS, TESTED DISTRIBUTIONALLY -----------------------
        # This replaces the "pick a desert coordinate" test that failed for
        # the wrong reason. Comparing whole counties cannot be gamed by which
        # point I happen to choose, and the direction is not something a
        # misaligned layer would produce: ASAL counties are sparsely settled
        # and far from the fibre backbone, so their sublocations should
        # average clearly lower coverage than the rest of the country.
        arid = conn.execute(text("""
            SELECT k.name IN :arid AS is_arid,
                   count(*)::int,
                   round(avg(c.coverage_pct)::numeric, 1)
            FROM connectivity.coverage c
            JOIN admin.counties k ON k.county_code = c.county_code
            WHERE c.technology='4g' AND c.operator='all'
              AND c.coverage_pct IS NOT NULL
            GROUP BY 1
        """).bindparams(arid=tuple(ARID_COUNTIES))).fetchall()
        d = {bool(a): (n, float(v)) for a, n, v in arid}
        if True in d and False in d:
            print(f"\n  ASAL counties     : {d[True][1]}% mean coverage "
                  f"({d[True][0]:,} sublocations)")
            print(f"  everywhere else   : {d[False][1]}% mean coverage "
                  f"({d[False][0]:,} sublocations)")
            check("arid counties read lower than the rest of Kenya",
                  d[True][1] < d[False][1],
                  f"{d[True][1]}% vs {d[False][1]}% "
                  f"(gap {d[False][1]-d[True][1]:.1f} points)")
        else:
            print("\n  ASAL comparison skipped: county_code not populated. "
                  "Run etl_25 step 4 (geometry backfill) first.")

        # --- 4. Coverage should not exceed 100 or fall below 0 -------------
        bad = conn.execute(text("""
            SELECT count(*) FROM connectivity.coverage
            WHERE coverage_pct < 0 OR coverage_pct > 100
        """)).scalar()
        check("no impossible percentages", bad == 0,
              f"{bad:,} rows outside 0-100")

        # --- 5. Operator ordering: Safaricom should lead Telkom ------------
        # Safaricom holds ~65% of the Kenyan market and the widest network.
        # If Telkom outranked it the layers would be mislabelled.
        pair = conn.execute(text("""
            SELECT operator, round(avg(coverage_pct)::numeric,1)
            FROM connectivity.coverage
            WHERE technology='4g' AND operator IN ('Safaricom','Telkom')
            GROUP BY 1
        """)).fetchall()
        d = {o: float(v) for o, v in pair}
        if {"Safaricom", "Telkom"} <= set(d):
            check("Safaricom 4G exceeds Telkom 4G",
                  d["Safaricom"] > d["Telkom"],
                  f"Safaricom {d['Safaricom']}% vs Telkom {d['Telkom']}%")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        print("Before believing a failure, check the test (lesson 17).")
        sys.exit(1)
    print("All checks passed.")
    print("Reminder: a pass here supports ALIGNMENT and VINTAGE. It cannot")
    print("confirm that the layer labelled 4g is 4g, and it validates no")
    print("point-level claim. Both need the CA.")


if __name__ == "__main__":
    main()
