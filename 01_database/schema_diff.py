r"""
============================================================================
CAN THE NUMBERED FILES REBUILD THE LIVE DATABASE?  (RULE E10, BLOCKING)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS EXISTS

  DEPLOY.md says the database is created by running the numbered SQL files in
  order. That claim has already failed once: the files were found SHORT of
  the live database. Nobody knows by how much, because nobody has compared
  them since.

  This matters the moment a second machine exists. Everything works today
  because the laptop's database has been accumulating for twelve sessions -
  migrations, hand-fixes, and whatever the thirty ETL scripts created along
  the way. A server built from 01_database will have only what those files
  say. Anything else silently does not exist, and the failure surfaces as a
  missing column in a query on a live client's widget.

  Reading the files cannot answer this. Files are not a schema; a schema is
  what a database ends up with after running them. So this compares two
  DATABASES: the live one, and a scratch one replayed from the files alone.

WHAT IT REPORTS

  MISSING FROM REBUILT   - live has it, the files do not create it. This is
                           the deploy blocker. Every entry is something a new
                           server will not have.
  EXTRA IN REBUILT       - the files create something live does not have.
                           Usually a migration applied to the files but never
                           run on the laptop.
  DIFFERENT              - same name, different type, nullability or default.
                           The quietest and most dangerous class.

  It compares tables, columns, primary and foreign keys, unique and check
  constraints, indexes, views and sequences.

WHAT IT DOES NOT DO

  It does not fix anything and it does not touch either database. It reads
  catalogues. Deciding what to do about a gap - add a migration, or accept
  that an ETL creates it - is a person's call, and the two answers are very
  different: an ETL-created table is fine if the ETL runs on the server, and
  fatal if it does not.

USAGE
  python schema_diff.py --live land_intelligence_kenya \
                        --rebuilt land_intelligence_rebuild_check
============================================================================
"""
import os
import sys
import argparse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
ENV_DIR = BASE.parent / "03_etl"

# Schemas PostGIS and the extensions own. Not ours, never compared.
SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast", "tiger",
                  "tiger_data", "topology")

# WORKBENCH ONLY - NEVER SHIPS.
#
# The first version of this script counted every difference as a deploy
# blocker and printed "125 DEPLOY BLOCKERS". Nineteen of those tables were
# staging.*_raw - the landing tables ogr2ogr writes shapefiles into before an
# ETL normalises them. They exist on the laptop because thirty ETL scripts ran
# there. They have no business on a server that never runs an ETL, and calling
# them blockers buried the two entries that genuinely are.
#
# A number that counts everything measures nothing. So the comparison is split:
# what must exist on a serving machine, and what belongs to the workbench.
WORKBENCH_SCHEMAS = ("staging",)


def is_workbench(key):
    return key[0] in WORKBENCH_SCHEMAS

Q_TABLES = """
    SELECT table_schema, table_name, table_type
      FROM information_schema.tables
     WHERE table_schema NOT IN :sys AND table_schema NOT LIKE 'pg_%%'
"""

Q_COLUMNS = """
    SELECT table_schema, table_name, column_name, data_type,
           is_nullable, column_default, character_maximum_length,
           numeric_precision, numeric_scale
      FROM information_schema.columns
     WHERE table_schema NOT IN :sys AND table_schema NOT LIKE 'pg_%%'
"""

Q_CONSTRAINTS = """
    SELECT n.nspname, t.relname, c.conname, pg_get_constraintdef(c.oid)
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
     WHERE n.nspname NOT IN :sys AND n.nspname NOT LIKE 'pg_%%'
"""

Q_INDEXES = """
    SELECT schemaname, tablename, indexname, indexdef
      FROM pg_indexes
     WHERE schemaname NOT IN :sys AND schemaname NOT LIKE 'pg_%%'
"""

Q_SEQUENCES = """
    SELECT sequence_schema, sequence_name
      FROM information_schema.sequences
     WHERE sequence_schema NOT IN :sys
"""


def connect(dbname):
    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{dbname}")


def fetch(engine, q, label=""):
    try:
        with engine.connect() as conn:
            return conn.execute(text(q), {"sys": SYSTEM_SCHEMAS}).all()
    except Exception as e:
        # A three-hundred-line SQLAlchemy traceback for "the database does not
        # exist" tells a reader nothing they can act on.
        msg = str(e.__cause__ or e).strip().splitlines()[-1]
        sys.exit(f"\nCANNOT READ {label or 'database'}: {msg}\n\n"
                 f"If the scratch database has not been built yet, run:\n"
                 f"  powershell -ExecutionPolicy Bypass -File .\\rebuild_check.ps1\n")


def key_and_detail(rows, nkey):
    """-> {identity tuple: detail tuple}. nkey columns form the identity."""
    return {tuple(str(x) for x in r[:nkey]): tuple(
        "" if x is None else str(x) for x in r[nkey:]) for r in rows}


def compare(name, live_rows, reb_rows, nkey):
    live = key_and_detail(live_rows, nkey)
    reb = key_and_detail(reb_rows, nkey)

    missing = sorted(set(live) - set(reb))
    extra = sorted(set(reb) - set(live))
    differ = sorted(k for k in set(live) & set(reb) if live[k] != reb[k])

    ship_missing = [k for k in missing if not is_workbench(k)]
    work_missing = [k for k in missing if is_workbench(k)]
    ship_differ = [k for k in differ if not is_workbench(k)]
    ship_extra = [k for k in extra if not is_workbench(k)]

    print(f"\n{'-' * 74}\n{name.upper()}   "
          f"live {len(live)}   rebuilt {len(reb)}\n{'-' * 74}")

    if not (missing or extra or differ):
        print("   identical")
        return 0

    if ship_missing:
        print(f"\n   *** MISSING FROM REBUILT ({len(ship_missing)}) - a "
              f"SERVING machine will NOT have these:")
        for k in ship_missing:
            print(f"         {'.'.join(k)}   live: {' | '.join(live[k])}")
    if ship_differ:
        print(f"\n   *** DIFFERENT ({len(ship_differ)}):")
        for k in ship_differ:
            print(f"         {'.'.join(k)}")
            print(f"            live    : {' | '.join(live[k])}")
            print(f"            rebuilt : {' | '.join(reb[k])}")
    if ship_extra:
        print(f"\n   EXTRA IN REBUILT ({len(ship_extra)}) - the files create "
              f"these but the laptop does not have them:")
        for k in ship_extra:
            print(f"         {'.'.join(k)}")

    if work_missing:
        tables = sorted({k[1] if nkey > 1 else k[0] for k in work_missing})
        print(f"\n   workbench only, not a deploy concern: "
              f"{len(work_missing)} in {', '.join(WORKBENCH_SCHEMAS)} "
              f"({len(tables)} table(s))")
        print(f"      these are ETL landing tables. A serving machine never "
              f"runs an ETL,\n      so it does not need them - but the "
              f"WORKBENCH does, and nothing in\n      01_database recreates "
              f"them either. See the note at the end.")

    return len(ship_missing) + len(ship_differ)


def row_counts(engine, label):
    """Exact count(*) for every table. Slow on purpose.

    reltuples would be instant and would report zero on a freshly restored
    database, because nothing has been ANALYZEd yet - an estimate that says
    'empty' about a full table is worse than no check at all. This is a drill
    that runs occasionally; correctness beats speed.
    """
    with engine.connect() as conn:
        tables = conn.execute(text("""
            SELECT table_schema, table_name
              FROM information_schema.tables
             WHERE table_type = 'BASE TABLE'
               AND table_schema NOT IN :sys AND table_schema NOT LIKE 'pg_%%'
             ORDER BY 1, 2"""), {"sys": SYSTEM_SCHEMAS}).all()
        out = {}
        for sch, tbl in tables:
            try:
                n = conn.execute(text(
                    f'SELECT count(*) FROM "{sch}"."{tbl}"')).scalar()
            except Exception:                                 # noqa: BLE001
                n = None
            out[(sch, tbl)] = n
    print(f"   counted {len(out)} table(s) in {label}")
    return out


def compare_rows(live_counts, reb_counts, dump_age_hours=None):
    """Did the restore work, and what would restoring it cost you today?

    THE FIRST VERSION OF THIS WAS WRONG, and wrong in a way worth keeping
    written down. It failed the drill because clients.api_keys held 3 rows
    live and 1 in the restore - and that was CORRECT: the dump was six days
    old and two keys had been minted since. A backup containing fewer rows
    than a database that has grown is a backup behaving exactly as intended.

    Treating any shortfall as failure means the check can only ever pass for
    a dump taken this instant, which is not a thing anyone has. Worse, it
    cries wolf, and a drill that cries wolf is a drill that stops being run.

    So the two questions are separated, because they are different questions:

      DID THE RESTORE WORK?     a table absent, or present with zero rows
                                where live has many. Nothing legitimate
                                produces that. This fails the drill.

      WHAT IS THE RECOVERY POINT? tables with fewer rows than live, all
                                non-zero. This is drift since the dump, it is
                                expected, it grows with the dump's age - and
                                it is the genuinely useful output, because it
                                says what you would lose by restoring today.
    """
    print(f"\n{'-' * 74}\nROW COUNTS\n{'-' * 74}")
    missing, empty, drift, over, empty_live = [], [], [], [], 0

    for key, live_n in sorted(live_counts.items()):
        name = ".".join(key)
        if key not in reb_counts:
            missing.append((name, live_n))
            continue
        reb_n = reb_counts[key]
        if live_n is None or reb_n is None:
            continue
        if live_n == 0:
            empty_live += 1
            continue
        if reb_n == 0:
            empty.append((name, live_n))
        elif reb_n < live_n:
            drift.append((name, live_n, reb_n))
        elif reb_n > live_n:
            over.append((name, live_n, reb_n))

    bad = 0
    if missing:
        bad += len(missing)
        print(f"\n   *** {len(missing)} TABLE(S) ABSENT FROM THE RESTORE:")
        for name, n in missing:
            print(f"         {name}  ({n:,} rows live)")
    if empty:
        bad += len(empty)
        print(f"\n   *** {len(empty)} TABLE(S) RESTORED COMPLETELY EMPTY:")
        for name, n in empty:
            print(f"         {name}  live {n:,}  restored 0")
        print("\n   Nothing legitimate produces an empty table where live has")
        print("   rows. This is the failure the drill exists to find.")

    if drift:
        age = (f" (dump is {dump_age_hours:.0f} hours old)"
               if dump_age_hours else "")
        print(f"\n   RECOVERY POINT{age} - restoring this dump today would "
              f"lose:")
        for name, ln, rn in drift:
            print(f"         {name:<44} {ln - rn:,} row(s)  "
                  f"({rn:,} of {ln:,})")
        print("\n   This is drift since the dump was taken, not damage. It")
        print("   grows with the dump's age, and it is the number to weigh")
        print("   when deciding how often to run a backup.")

    if over:
        print(f"\n   {len(over)} table(s) have MORE rows in the restore than "
              f"live.\n   The live database LOST rows since the dump. Worth "
              f"understanding\n   before dismissing:")
        for name, ln, rn in over[:10]:
            print(f"         {name}  live {ln:,}  restored {rn:,}")

    if not bad:
        n_ok = sum(1 for k, v in live_counts.items() if v)
        intact = n_ok - len(drift)
        print(f"\n   {intact} of {n_ok} non-empty table(s) restored complete; "
              f"{len(drift)} carry drift.")
        if empty_live:
            print(f"   ({empty_live} table(s) are empty in live too - not "
                  f"checked)")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", default="land_intelligence_kenya")
    ap.add_argument("--rebuilt", required=True)
    ap.add_argument("--rows", action="store_true",
                    help="also compare row counts (for a restore drill)")
    ap.add_argument("--dump-age-hours", type=float, default=None,
                    help="age of the dump, so drift can be read in context")
    a = ap.parse_args()

    if a.live == a.rebuilt:
        sys.exit("ERROR: --live and --rebuilt are the same database.")

    live, reb = connect(a.live), connect(a.rebuilt)

    print("=" * 74)
    print("E10 SCHEMA DIFF - CAN 01_database REBUILD THE LIVE DATABASE?")
    print(f"   live    : {a.live}")
    print(f"   rebuilt : {a.rebuilt}")
    print("=" * 74)

    blockers = 0
    for label, q, nkey in (("tables and views", Q_TABLES, 2),
                           ("columns", Q_COLUMNS, 3),
                           ("constraints", Q_CONSTRAINTS, 3),
                           ("indexes", Q_INDEXES, 3),
                           ("sequences", Q_SEQUENCES, 2)):
        blockers += compare(label,
                            fetch(live, q, f"live '{a.live}'"),
                            fetch(reb, q, f"rebuilt '{a.rebuilt}'"), nkey)

    row_problems = 0
    if a.rows:
        print(f"\n{'-' * 74}\ncounting rows (exact, so this takes a moment)"
              f"\n{'-' * 74}")
        row_problems = compare_rows(row_counts(live, a.live),
                                    row_counts(reb, a.rebuilt),
                                    a.dump_age_hours)

    print("\n" + "=" * 74)
    if a.rows:
        if row_problems:
            print(f"RESTORE BROKEN: {row_problems} table(s) absent or empty.")
            print()
            print("This backup would not have brought the workbench back.")
            print("Do not treat it as a backup until this is understood.")
        elif not blockers:
            print("RESTORE VERIFIED.")
            print()
            print("Schema identical. No table absent, none restored empty.")
            print("A backup has now actually been restored into a working")
            print("database and compared against the original, which is the")
            print("difference between a backup and a belief.")
            print()
            print("Any drift listed above is the RECOVERY POINT, not damage:")
            print("what restoring this particular dump would cost you today.")
        print("=" * 74)
        sys.exit(1 if (row_problems or blockers) else 0)

    if blockers:
        print(f"{blockers} DEPLOY BLOCKER(S) ON SHIPPED SCHEMAS.")
        print()
        print("Each is something the live database has that a serving machine")
        print("built from 01_database would not. Each needs a migration.")
    else:
        print("NO DEPLOY BLOCKERS.")
        print()
        print("Every schema that ships is reproduced exactly by the numbered")
        print("files. DEPLOY.md's claim is true for a serving machine.")
    print()
    print("SEPARATELY, AND NOT A DEPLOY BLOCKER: nothing in 01_database")
    print("recreates the staging schema. It is written by ogr2ogr and the ETL")
    print("scripts, from source files. That is fine for a server, which never")
    print("runs an ETL - but it means THE WORKBENCH CANNOT BE REBUILT FROM")
    print("THIS FOLDER EITHER. If the laptop dies, the schema survives and")
    print("twelve sessions of loaded data do not. That is a backup question,")
    print("not a deploy question, and it is the more urgent of the two.")
    print("=" * 74)
    sys.exit(1 if blockers else 0)


if __name__ == "__main__":
    main()
