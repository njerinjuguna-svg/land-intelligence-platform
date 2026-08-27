r"""
============================================================================
IS PER-OPERATOR COVERAGE A MEASUREMENT, OR ONE POLYGON COUNTED TWICE?
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS EXISTS

  On PLOT-365 the enrichment returned

      coverage_4g_pct_safaricom = 88.30089662557684
      coverage_4g_pct_telkom    = 88.30089662557684

  Two different operators agreeing to fourteen decimal places is not two
  measurements. It is one polygon being counted twice, or two layers that
  are copies of each other.

  Nothing is displayed from these columns today - report_content.py never
  reads them, and rule D5 keeps per-operator figures off the page anyway
  because the CA published no Airtel percentage and a blank beside Safaricom
  reads as "no Airtel here". So this is not urgent. It is load-bearing for
  Phase 2, where per-operator coverage is exactly the kind of detail a
  marketplace buyer asks for, and a number that is quietly wrong is worse
  than one that is missing.

  E2: query it, don't recall it. This script does not guess which of the two
  explanations is right - it prints what the database actually holds and
  lets a person read it.

WHAT TO LOOK FOR

  1. If the per-parcel values are identical on EVERY parcel, the operator
     split is not real and those columns should be dropped until the CA
     supplies genuinely separate layers.
  2. If they differ on some parcels and not others, the sublocations where
     they agree may genuinely be served identically - check whether the
     source polygon COUNT and geometry match too, in section B.
  3. If the source polygons are byte-identical between operators, the ETL is
     loading one layer twice under two names.

USAGE
  python check_01_coverage_operators.py
============================================================================
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
ENV_DIR = BASE.parent / "03_etl"


def main():
    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")

    with engine.connect() as conn:
        print("=" * 76)
        print("A. PER-PARCEL VALUES, ACTIVE PARCELS ONLY")
        print("=" * 76)
        rows = conn.execute(text("""
            SELECT p.parcel_ref,
                   i.coverage_4g_pct          AS all_ops,
                   i.coverage_4g_pct_safaricom AS safaricom,
                   i.coverage_4g_pct_telkom    AS telkom,
                   i.coverage_admin_name       AS sublocation
              FROM analytics.parcel_intelligence i
              JOIN land.parcels p ON p.parcel_id = i.parcel_id
             WHERE i.status = 'active' AND p.status = 'active'
             ORDER BY p.parcel_ref
        """)).mappings().all()

        if not rows:
            sys.exit("No active enrichment rows.")

        same = diff = onlyone = neither = 0
        print(f"  {'parcel':<22}{'sublocation':<18}"
              f"{'safaricom':>14}{'telkom':>14}   ")
        for r in rows:
            s, t = r["safaricom"], r["telkom"]
            if s is None and t is None:
                mark, neither = "both NULL", neither + 1
            elif s is None or t is None:
                mark, onlyone = "ONE NULL", onlyone + 1
            elif float(s) == float(t):
                mark, same = "IDENTICAL", same + 1
            else:
                mark, diff = "differ", diff + 1
            print(f"  {r['parcel_ref']:<22}{(r['sublocation'] or '-'):<18}"
                  f"{('-' if s is None else format(float(s), '.6f')):>14}"
                  f"{('-' if t is None else format(float(t), '.6f')):>14}"
                  f"   {mark}")

        print(f"\n  identical {same}   differ {diff}   "
              f"one NULL {onlyone}   both NULL {neither}")
        if diff == 0 and same > 0:
            print("\n  >> NO PARCEL SEPARATES THE TWO OPERATORS. On this "
                  "evidence the\n     per-operator columns carry no operator "
                  "information at all.")

        print("\n" + "=" * 76)
        print("B. THE SOURCE LAYERS THEMSELVES")
        print("=" * 76)
        layers = conn.execute(text("""
            SELECT operator, technology, source_layer, count(*) AS polygons,
                   round(sum(ST_Area(geom::geography))::numeric / 1e6, 1)
                       AS total_km2
              FROM connectivity.coverage
             WHERE status = 'active'
             GROUP BY 1, 2, 3
             ORDER BY 2, 1, 3
        """)).mappings().all()
        print(f"  {'operator':<16}{'tech':<8}{'source_layer':<28}"
              f"{'polygons':>10}{'km2':>12}")
        for l in layers:
            print(f"  {(l['operator'] or '-'):<16}{(l['technology'] or '-'):<8}"
                  f"{(l['source_layer'] or '-'):<28}"
                  f"{l['polygons']:>10}{float(l['total_km2'] or 0):>12,.1f}")
        print("\n  Two operators with the same polygon count AND the same "
              "area are\n  the same layer loaded twice. Different counts mean "
              "the split is real\n  and the identical percentages in A need "
              "another explanation.")
        print("=" * 76)


if __name__ == "__main__":
    main()
