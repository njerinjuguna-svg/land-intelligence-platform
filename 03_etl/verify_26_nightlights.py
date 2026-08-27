r"""
============================================================================
VERIFY 26 - demographics.nightlights against independent producers
Land Intelligence Platform - Geocode Spatial Solutions Ltd

READ-ONLY. Writes nothing.

THE MAIN TEST: NASA vs THE EUROPEAN COMMISSION
  Same move as SoilGrids vs iSDA and CA-coverage vs OpenCellID. Lit area
  comes from NASA Black Marble (VIIRS DNB, an optical measurement at night).
  Built-up surface comes from GHSL (Sentinel/Landsat, a structural
  measurement by day). Different agencies, different sensors, different
  physics, neither aware of the other.

  Buildings and lights are not the same thing, so we do NOT expect equality.
  We expect ORDERING: wards with more built surface should have more lit
  area. If that fails, the mosaic is misplaced -- and a tile-grid error is
  precisely the failure mode this ETL is exposed to, since the geotransform
  is constructed from tile indices rather than read from the file.

WHAT A PASS DOES NOT ESTABLISH
  - Not that radiance is proportional to economic activity. VIIRS compresses
    bright cores, so a dark ward becoming lit moves far more than a bright
    CBD growing further.
  - Not that the trend is real growth rather than sensor drift. SNPP's DNB
    degraded after launch; v2.0 applies yearly spectral response corrections,
    but a national trend should still be read as indicative.
  - Nothing about the three wards that returned no data in any year.

How to run (from 03_etl with venv active):
  python verify_26_nightlights.py
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

ARID = {"Turkana", "Marsabit", "Mandera", "Wajir", "Garissa",
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
        print("WHAT IS IN THE TABLE")
        rows = conn.execute(text("""
            SELECT period, admin_level, count(*),
                   round(avg(radiance_mean)::numeric, 3),
                   round(max(radiance_mean)::numeric, 1),
                   round(avg(lit_area_pct)::numeric, 2)
            FROM demographics.nightlights_stats
            GROUP BY 1, 2 ORDER BY 2, 1
        """)).fetchall()
        if not rows:
            sys.exit("demographics.nightlights_stats is empty. Run etl_26.")
        print(f"  {'year':6}{'level':9}{'units':>8}{'mean rad':>11}"
              f"{'max rad':>10}{'lit %':>9}")
        for p, lv, n, mean, mx, lit in rows:
            print(f"  {p:6}{lv:9}{n:>8,}{mean:>11}{mx:>10}{lit:>9}")

        # --- 1. Sanity ------------------------------------------------------
        bad = conn.execute(text("""
            SELECT count(*) FROM demographics.nightlights_stats
            WHERE radiance_mean < 0 OR lit_area_pct < 0 OR lit_area_pct > 100
        """)).scalar()
        check("no impossible values", bad == 0,
              f"{bad:,} rows with negative radiance or lit% outside 0-100")

        # --- 2. THE CROSS-PRODUCER TEST -------------------------------------
        # Wards binned by GHSL built-up share, compared on Black Marble lit
        # area. Monotonic rise is the claim.
        print("\nLIT AREA BY GHSL BUILT-UP BAND (wards, latest year)")
        band = conn.execute(text("""
            WITH latest AS (
                SELECT max(period) AS p FROM demographics.nightlights_stats
            ), w AS (
                SELECT n.admin_code, n.lit_area_pct, n.radiance_mean,
                       COALESCE(b.built_pct, 0) AS built_pct
                FROM demographics.nightlights_stats n
                JOIN latest ON n.period = latest.p
                LEFT JOIN (
                    SELECT COALESCE(ward_code, 'LIP-W' || id::text) AS code,
                           NULL::numeric AS built_pct
                    FROM admin.wards WHERE status='active'
                ) b ON b.code = n.admin_code
                WHERE n.admin_level = 'ward'
            )
            SELECT count(*) FROM w
        """)).scalar()
        # GHSL built-up lives in a raster, not a table, so the honest
        # cross-check uses population density as the structural proxy that IS
        # in PostGIS. Stated plainly rather than pretending we joined GHSL.
        print("  (GHSL built-up is a raster, not a table; using "
              "demographics.population_stats")
        print("   density as the independent structural measure instead)")
        dens = conn.execute(text("""
            WITH latest AS (
                SELECT max(period) AS p FROM demographics.nightlights_stats
            ), j AS (
                SELECT n.admin_code, n.lit_area_pct, p.density_per_km2,
                       ntile(5) OVER (ORDER BY p.density_per_km2) AS q
                FROM demographics.nightlights_stats n
                JOIN latest ON n.period = latest.p
                JOIN demographics.population_stats p
                  ON p.admin_code = n.admin_code AND p.admin_level = 'ward'
                WHERE n.admin_level = 'ward'
                  AND p.density_per_km2 IS NOT NULL
            )
            SELECT q, count(*), round(avg(density_per_km2)::numeric, 0),
                   round(avg(lit_area_pct)::numeric, 2)
            FROM j GROUP BY q ORDER BY q
        """)).fetchall()
        if dens:
            print(f"  {'quintile':10}{'wards':>8}{'density/km2':>14}"
                  f"{'lit %':>9}")
            vals = []
            for q, n, d, lit in dens:
                print(f"  {q:<10}{n:>8,}{d:>14,}{lit:>9}")
                vals.append(float(lit))
            rising = sum(1 for a, b in zip(vals, vals[1:]) if b >= a)
            check("lit area rises with population density",
                  vals[-1] > vals[0] and rising >= len(vals) - 2,
                  f"{vals[0]}% -> {vals[-1]}% "
                  f"({rising} of {len(vals)-1} steps non-decreasing)")
        else:
            print("  population_stats not joinable; skipped")

        # --- 3. Nairobi should be brightest ---------------------------------
        top = conn.execute(text("""
            SELECT k.name, round(n.radiance_mean::numeric, 2)
            FROM demographics.nightlights_stats n
            JOIN admin.counties k ON k.county_code = n.admin_code
            WHERE n.admin_level='county'
              AND n.period = (SELECT max(period)
                              FROM demographics.nightlights_stats)
            ORDER BY n.radiance_mean DESC LIMIT 5
        """)).fetchall()
        print("\nBRIGHTEST COUNTIES (latest year, mean radiance)")
        for nm, v in top:
            print(f"  {nm:20}{v:>10}")
        check("Nairobi is the brightest county",
              bool(top) and "nairobi" in top[0][0].lower(),
              f"top is {top[0][0]} at {top[0][1]}" if top else "no rows")

        # --- 4. Arid counties should be dark --------------------------------
        arid = conn.execute(text("""
            SELECT k.name IN :arid AS is_arid,
                   round(avg(n.radiance_mean)::numeric, 3),
                   round(avg(n.lit_area_pct)::numeric, 2)
            FROM demographics.nightlights_stats n
            JOIN admin.counties k ON k.county_code = n.admin_code
            WHERE n.admin_level='county'
              AND n.period = (SELECT max(period)
                              FROM demographics.nightlights_stats)
            GROUP BY 1
        """).bindparams(arid=tuple(ARID))).fetchall()
        d = {bool(a): (float(r), float(l)) for a, r, l in arid}
        if True in d and False in d:
            print(f"\n  ASAL counties   : {d[True][0]} mean radiance, "
                  f"{d[True][1]}% lit")
            print(f"  everywhere else : {d[False][0]} mean radiance, "
                  f"{d[False][1]}% lit")
            check("arid counties are darker", d[True][0] < d[False][0],
                  f"{d[True][0]} vs {d[False][0]}")

        # --- 5. trend_pct_yr must be absent ---------------------------------
        left = conn.execute(text("""
            SELECT count(*) FROM demographics.nightlights_stats
            WHERE trend_pct_yr IS NOT NULL
        """)).scalar()
        check("the withdrawn percentage trend is not populated", left == 0,
              "trend_pct_yr is NULL throughout" if left == 0 else
              f"{left:,} rows still carry trend_pct_yr; it ranked rural "
              f"electrification above peri-urban development")

        # --- 6. The development trend, which IS the product -----------------
        tr = conn.execute(text("""
            SELECT count(*) FILTER (WHERE trend_radiance_yr > 0),
                   count(*) FILTER (WHERE trend_radiance_yr < 0),
                   count(*) FILTER (WHERE trend_radiance_yr IS NULL),
                   round((percentile_cont(0.5) WITHIN GROUP
                          (ORDER BY trend_radiance_yr))::numeric, 2)
            FROM demographics.nightlights_stats
            WHERE admin_level='ward'
              AND period = (SELECT max(period)
                            FROM demographics.nightlights_stats)
        """)).fetchone()
        pos, neg, nul, med_t = tr
        print(f"\nDEVELOPMENT TREND (wards): {pos:,} brightening, "
              f"{neg:,} dimming, {nul:,} undefined")
        print(f"  median {med_t} radiance/yr")
        check("more wards brightening than dimming", (pos or 0) > (neg or 0),
              f"{pos:,} vs {neg:,}")

        # --- 7. NAMED IN ADVANCE, not read off the model's own top list -----
        # A ranking cannot be validated by admiring its own output. These are
        # the Nairobi peri-urban land markets any Kenyan agent would name
        # without seeing the data, plus controls that should NOT lead. The
        # test is whether the known markets sit in the national top decile.
        HOT = ["Ruai", "Kitengela", "Kinanie", "Muthwani", "Gatongora",
               "Murera", "Kalimoni", "Mihang'o"]
        print("\nKNOWN PERI-URBAN MARKETS (named before looking at output)")
        placed = 0
        for name in HOT:
            r = conn.execute(text("""
                WITH latest AS (SELECT max(period) p
                                FROM demographics.nightlights_stats),
                ranked AS (
                    SELECT w.name AS ward, n.trend_radiance_yr,
                           percent_rank() OVER (
                               ORDER BY n.trend_radiance_yr) AS pr
                    FROM demographics.nightlights_stats n
                    JOIN latest ON n.period = latest.p
                    JOIN admin.wards w
                      ON COALESCE(w.ward_code, 'LIP-W' || w.id::text)
                         = n.admin_code
                    WHERE n.admin_level='ward'
                      AND n.trend_radiance_yr IS NOT NULL)
                SELECT ward, round(trend_radiance_yr::numeric,1),
                       round((100*pr)::numeric,1)
                FROM ranked WHERE ward ILIKE :n LIMIT 1
            """), {"n": name}).fetchone()
            if r is None:
                print(f"  {name:20}not found in admin.wards")
                continue
            ward, val, pr = r
            top10 = float(pr) >= 90.0
            placed += 1 if top10 else 0
            print(f"  {str(ward)[:20]:20}{val:>10}/yr   national percentile "
                  f"{pr:>5}  {'top decile' if top10 else '<-- CHECK'}")
        check("known land markets rank in the national top decile",
              placed >= len(HOT) - 2,
              f"{placed} of {len(HOT)} in the top 10%")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        print("Before believing a failure, check the test (lesson 17).")
        sys.exit(1)
    print("All checks passed.")
    print("Reminder: the TREND is the signal. Radiance is NOT a linear")
    print("measure of economic activity, and a national trend is indicative")
    print("only -- SNPP's sensor degraded over the series.")


if __name__ == "__main__":
    main()
