"""
============================================================================
ETL 30 - LANDMARKS (six tables, one Geofabrik extract)
Land Intelligence Platform - Geocode Spatial Solutions Ltd

What this script does:
  Fills six empty tables from OSM layers ALREADY ON DISK - the same Kenya
  extract etl_02 and etl_06 read. Nothing is downloaded.

      admin.places            <- places        city / town / suburb / village
      transport.airports      <- transport     airport / airfield
      transport.bus_stops     <- transport     bus + rail stops (see below)
      transport.railways      <- railways      rail lines
      social.markets          <- pois          marketplace
      social.public_services  <- pois          police / fire / court / hall

WHY ONE SCRIPT AND NOT SIX
  Every one of these is the same three steps against the same file set:
  read a Geofabrik layer, filter on fclass, write points with a county.
  Six scripts would be six copies of one bug. The SPECS table below is the
  only thing that differs between them, so it is the only thing written
  six times.

WHY THIS DOES NOT NEED A LICENCE LETTER
  The catalogue lists KCAA for airports and county governments for markets,
  both "by request". Those are the right PRIMARY sources and this is not
  them. What we publish from this layer is a DISTANCE and a NAME - values,
  not geometry - so ODbL share-alike is not engaged on distribution, and no
  by-request licence is either. Confidence is set accordingly: these are
  honest interim rows to be superseded, exactly like OSM protected areas.

POLYGONS BECOME POINTS, AND WHICH POINT MATTERS
  Several of these layers carry both a point file and a polygon file for the
  same features. Polygons are reduced with ST_PointOnSurface, NOT ST_Centroid:
  a centroid can fall outside a concave shape - an L-shaped market, a curved
  airport apron - and put the feature somewhere it is not. PointOnSurface is
  guaranteed to land inside.

How to run (from 03_etl with venv active):
  python 11_schema_update_v1.8.sql must be applied FIRST (admin.places)
  python etl_30_osm_landmarks.py
============================================================================
"""

import os
import re
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
RAW = BASE / "data" / "raw"
SOURCE_NAME = "OpenStreetMap via Geofabrik (Kenya extract)"
SOURCE_DATE = date(2026, 7, 16)
PIPELINE = "etl_30_osm_landmarks"

# ---------------------------------------------------------------------------
# FACILITIES THAT ARE NOT IN SERVICE, DROPPED BY NAME.
#
# The first landmarks run gave TEST-TANADELTA-01 a nearest airport of
# "Shekiko Airport (disused)". Nothing was broken: the geometry was right,
# the join was right, the distance was right. The ANSWER was still wrong,
# because a disused airstrip is not somewhere a buyer can fly into, and a
# listing page saying "your nearest airport is 7 km away" would be a false
# promise made in the source's own words.
#
# Geometry cannot tell a live facility from a dead one. OSM often says so in
# the name and nowhere else, so the name is what we read. Deliberately narrow:
# these words are matched only where they appear in parentheses or as whole
# words, so a genuine "Former Presidents Road" or a place called Closeburn is
# not swept up with them.
# ---------------------------------------------------------------------------
DEFUNCT = re.compile(
    r"\((?:[^)]*\b(?:disused|abandoned|former|closed|derelict|ruins?|ruined|"
    r"proposed|under\s+construction)\b[^)]*)\)"
    r"|\b(?:disused|abandoned|derelict|ruined)\b", re.I)

# ---------------------------------------------------------------------------
# THE SPECS. Everything that differs between the six loads lives here.
#
#   layers      Geofabrik files to read and union. Point and polygon files
#               for the same theme are both listed; polygons are reduced.
#   keep        fclass values to keep, mapped to the type value we store.
#               An fclass NOT in this dict is dropped - deliberately, so a
#               new OSM class appears as a missing row rather than as a
#               silently mislabelled one.
#   table       destination, with the column its type goes into.
#   conf        confidence, per the catalogue's view of this source.
# ---------------------------------------------------------------------------
SPECS = [
    dict(
        key="places", table="admin.places", type_col="place_type", conf=3,
        layers=["gis_osm_places_free_1.shp", "gis_osm_places_a_free_1.shp"],
        geom="point", extra=["population"],
        keep={"national_capital": "national_capital", "city": "city",
              "town": "town", "suburb": "suburb", "village": "village"},
    ),
    dict(
        # transport.airports.facility_type is CHECK-constrained to
        # international / domestic / airstrip. OSM's aeroway tagging does not
        # carry that distinction at all - everything is `airport` or
        # `airfield`. So `airport` is classified FROM THE NAME, the same way
        # etl_06 classifies protected areas: in Kenya an international
        # airport says so in its name (JKIA, Moi International, Kisumu
        # International), and nothing else does. Anything unmatched falls to
        # `domestic`, which is why this whole table sits at confidence 2.
        key="airports", table="transport.airports", type_col="facility_type",
        conf=2,
        layers=["gis_osm_transport_free_1.shp",
                "gis_osm_transport_a_free_1.shp"],
        geom="point", extra=[],
        # `n` is coerced with isinstance and NOT with `n or ""`. A missing
        # name arrives from pandas as NaN, NaN is a float, and a float is
        # TRUTHY - so `n or ""` hands NaN straight through to .lower().
        keep={"airport": lambda n: ("international"
                                    if isinstance(n, str)
                                    and "international" in n.lower()
                                    else "domestic"),
              "airfield": "airstrip"},
    ),
    dict(
        # NOTE THE TABLE NAME IS NARROWER THAN WHAT GOES IN IT.
        # Railway stations belong with transport stops, and there is no
        # stations table. stop_type carries the real distinction. Logged as
        # a rename to do properly rather than done quietly here - see the
        # tail of 11_schema_update_v1.8.sql.
        key="stops", table="transport.bus_stops", type_col="stop_type", conf=3,
        layers=["gis_osm_transport_free_1.shp",
                "gis_osm_transport_a_free_1.shp"],
        geom="point", extra=[],
        keep={"bus_stop": "bus_stop", "bus_station": "bus_station",
              "railway_station": "railway_station",
              "railway_halt": "railway_halt",
              "ferry_terminal": "ferry_terminal", "taxi": "taxi_stage"},
    ),
    dict(
        key="railways", table="transport.railways", type_col="rail_type",
        conf=3,
        layers=["gis_osm_railways_free_1.shp"],
        geom="multilinestring", extra=[],
        keep={"rail": "rail", "narrow_gauge": "narrow_gauge",
              "light_rail": "light_rail"},
    ),
    dict(
        # confidence 2: county market registers are the primary source and
        # OSM's coverage of rural markets is thin. An honest interim.
        key="markets", table="social.markets", type_col="market_type", conf=2,
        layers=["gis_osm_pois_free_1.shp", "gis_osm_pois_a_free_1.shp"],
        geom="point", extra=[],
        keep={"marketplace": "open_air"},
    ),
    dict(
        key="services", table="social.public_services",
        type_col="service_type", conf=3,
        layers=["gis_osm_pois_free_1.shp", "gis_osm_pois_a_free_1.shp"],
        geom="point", extra=[],
        # service_type is CHECK-constrained: police / fire_station /
        # huduma_centre / court / chiefs_office / government_office.
        # `town_hall` maps to government_office and NOT to chiefs_office -
        # a chief's office is a specific administrative post in Kenya and
        # OSM's town_hall is not it.
        keep={"police": "police", "fire_station": "fire_station",
              "courthouse": "court", "town_hall": "government_office"},
    ),
]


def allowed_values(conn, table, column):
    """-> set of values a CHECK constraint permits, or None if unconstrained.

    THIS IS THE CONTROL THAT SHOULD HAVE EXISTED FIRST.

    The first run of this script loaded 9,323 places, then died on row one
    of the next table because transport.airports.facility_type is CHECK-
    constrained to international/domestic/airstrip and the SPECS above said
    'airport'. The vocabulary was invented from what OSM calls things
    instead of read from the schema that has to accept them.

    That is Rule E2 - query it, don't recall it - and the repair is not to
    be more careful next time. It is to make the script unable to start a
    load it cannot finish. Every mapped value is checked against the real
    constraint BEFORE any table is touched, and every offending value is
    reported at once rather than one per run.
    """
    defn = conn.execute(text("""
        SELECT pg_get_constraintdef(c.oid)
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
         WHERE c.contype = 'c'
           AND n.nspname || '.' || t.relname = :t
           AND pg_get_constraintdef(c.oid) LIKE '%' || :col || '%'
           AND pg_get_constraintdef(c.oid) LIKE '%ARRAY[%'"""),
        {"t": table, "col": column}).scalar()
    if not defn:
        return None
    body = defn[defn.index("ARRAY[") + 6:]
    body = body[:body.index("]")]
    # Quoted literals only. Splitting on commas and stripping quotes looks
    # equivalent and is not: each element arrives as 'domestic'::text, whose
    # trailing character is `t`, so strip("'") leaves "domestic'::text" and
    # the check then rejects every value including the correct ones.
    return set(re.findall(r"'([^']*)'", body))


def find_layer(fname):
    """The extract may be unpacked on disk or still zipped. Try both."""
    for shp in RAW.rglob(fname):
        return str(shp)
    for z in RAW.rglob("kenya-*-free.shp.zip"):
        return f"zip://{z}!{fname}"
    return None


def read_spec(spec):
    """-> one GeoDataFrame with name / kind / population / geometry, or None.

    Reads every layer in the spec, keeps only the fclass values we asked
    for, and reports what it dropped. Columns are detected case-insensitively
    because publishers differ and this project has been bitten by assuming.
    """
    frames = []
    for fname in spec["layers"]:
        src = find_layer(fname)
        if src is None:
            print(f"      {fname}: NOT FOUND, skipping")
            continue
        gdf = gpd.read_file(src)
        lower = {c.lower(): c for c in gdf.columns}
        fcol = lower.get("fclass") or lower.get("code")
        ncol = lower.get("name")
        if fcol is None:
            print(f"      {fname}: no fclass column, skipping")
            continue
        gdf = gdf.rename(columns={fcol: "fclass"})
        gdf["name"] = gdf[ncol] if ncol else None
        gdf["population"] = (gdf[lower["population"]]
                             if "population" in lower else None)

        before = len(gdf)
        gdf = gdf[gdf["fclass"].isin(spec["keep"].keys())].copy()
        print(f"      {fname}: {len(gdf):,} kept of {before:,}")
        if len(gdf):
            frames.append(gdf[["name", "fclass", "population", "geometry"]])

    if not frames:
        return None
    gdf = pd.concat(frames, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=frames[0].crs)

    # UNNAMED ROWS GO FIRST, BEFORE CLASSIFICATION, and the order is the fix
    # for a real failure rather than tidiness. The classifier for airports
    # reads the NAME to tell an international from a domestic one, so
    # classifying rows we are about to discard fed a missing name into it.
    #
    # Schema requires a name on all six tables, and unnamed rows would be
    # useless anyway: the whole point of a landmark is that a buyer
    # recognises it. "Airport, 12 km" tells nobody anything.
    before = len(gdf)
    gdf = gdf[gdf["name"].notna()
              & (gdf["name"].astype(str).str.strip() != "")].copy()
    if before - len(gdf):
        print(f"      dropped {before - len(gdf):,} unnamed "
              "(a landmark nobody can name is not a landmark)")

    before = len(gdf)
    gdf = gdf[~gdf["name"].astype(str).str.contains(DEFUNCT, na=False)].copy()
    if before - len(gdf):
        print(f"      dropped {before - len(gdf):,} not in service "
              "(the name says so - see DEFUNCT)")

    # A `keep` value is either a fixed string or a callable(name).
    def _kind(row):
        v = spec["keep"][row["fclass"]]
        return v(row["name"]) if callable(v) else v
    gdf["kind"] = gdf.apply(_kind, axis=1)

    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    return gdf.reset_index(drop=True)


load_dotenv(BASE / ".env")
pw = os.getenv("DB_PASSWORD")
if not pw or pw == "put_your_password_here":
    sys.exit("ERROR: edit the .env file and set DB_PASSWORD first.")

engine = create_engine(
    f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
    f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
    f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
print("Connected to database:", os.getenv("DB_NAME", "land_intelligence_kenya"))

with engine.begin() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))
    source_id = conn.execute(
        text("SELECT source_id FROM metadata.sources WHERE name = :n"),
        {"n": SOURCE_NAME}).scalar()
if source_id is None:
    sys.exit("ERROR: Geofabrik source missing. Run etl_02_osm_roads.py first.")
print(f"Source reused: {SOURCE_NAME} (source_id={source_id})")

# admin.places must exist before we start, or five loads succeed and one
# fails halfway through - a worse state than refusing up front.
with engine.connect() as conn:
    if not conn.execute(text("SELECT to_regclass('admin.places')")).scalar():
        sys.exit("ERROR: admin.places is missing. Apply "
                 "01_database/11_schema_update_v1.8.sql first.")

with engine.begin() as conn:
    run_id = conn.execute(text("""
        INSERT INTO metadata.etl_runs (pipeline, started_at, run_status)
        VALUES (:p, now(), 'running') RETURNING run_id"""),
        {"p": PIPELINE}).scalar()
print(f"ETL run opened (run_id={run_id})\n")

try:
    # County tiles once, reused by all six. ST_Subdivide because a whole
    # county polygon makes the index useless on a point-in-polygon join.
    print("Building county tiles for the point-in-county joins...")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS staging.county_tiles"))
        conn.execute(text("""
            CREATE TABLE staging.county_tiles AS
            SELECT county_code, ST_Subdivide(geom, 128) AS geom
              FROM admin.counties"""))
        conn.execute(text(
            "CREATE INDEX ON staging.county_tiles USING gist (geom)"))
        conn.execute(text("ANALYZE staging.county_tiles"))

    # -----------------------------------------------------------------
    # PASS 1 - read and classify everything, then VALIDATE EVERY VALUE
    # against the real CHECK constraints before a single table is touched.
    #
    # Two passes and not one, because of what one pass actually did: it
    # loaded 9,323 places, then hit a constraint on the next table and left
    # the database in a state no single run had produced. Reading is cheap
    # here (these are the 2-8 MB POI and places files, not the 1.2 GB
    # buildings layer) and a load that cannot finish should not start.
    # -----------------------------------------------------------------
    print("\nPASS 1 - reading layers and checking vocabularies")
    frames, problems = {}, []
    with engine.connect() as conn:
        for spec in SPECS:
            print(f"\n{spec['table']}")
            gdf = read_spec(spec)
            frames[spec["key"]] = gdf
            if gdf is None or gdf.empty:
                print("      nothing to load")
                continue
            print("      counts by type:")
            for t, c in gdf["kind"].value_counts().items():
                print(f"         {t}: {c:,}")

            ok = allowed_values(conn, spec["table"], spec["type_col"])
            if ok is None:
                print(f"      {spec['type_col']}: no CHECK constraint")
                continue
            bad = set(gdf["kind"].unique()) - ok
            if bad:
                problems.append(
                    f"{spec['table']}.{spec['type_col']} rejects "
                    f"{sorted(bad)} — it allows only {sorted(ok)}")
                print(f"      {spec['type_col']}: REJECTED {sorted(bad)}")
            else:
                print(f"      {spec['type_col']}: all values allowed")

    if problems:
        raise RuntimeError(
            "Vocabulary mismatch, nothing loaded:\n   "
            + "\n   ".join(problems))

    print("\nPASS 2 - loading")
    totals = {}
    for spec in SPECS:
        gdf = frames[spec["key"]]
        print(f"\n{spec['table']}")
        if gdf is None or gdf.empty:
            print("      nothing to load")
            totals[spec["table"]] = 0
            continue

        stage = f"lm_{spec['key']}_raw"
        cols = ["name", "kind", "geometry"]
        if "population" in spec["extra"]:
            cols.insert(2, "population")
        gdf[cols].to_postgis(stage, engine, schema="staging",
                             if_exists="replace", chunksize=5000)

        # ST_PointOnSurface, not ST_Centroid - a centroid can land outside a
        # concave shape and put the feature somewhere it is not.
        if spec["geom"] == "point":
            geom_sql = ("CASE WHEN GeometryType(r.geometry) = 'POINT' "
                        "THEN r.geometry "
                        "ELSE ST_PointOnSurface(ST_MakeValid(r.geometry)) END")
        else:
            geom_sql = ("ST_Multi(ST_CollectionExtract("
                        "ST_MakeValid(r.geometry), 2))")

        pop_col = ", population" if "population" in spec["extra"] else ""
        pop_val = ", r.population::integer" if "population" in spec["extra"] else ""

        with engine.begin() as conn:
            conn.execute(text(
                f"CREATE INDEX ON staging.{stage} USING gist (geometry)"))
            conn.execute(text(f"ANALYZE staging.{stage}"))
            conn.execute(text(
                f"DELETE FROM {spec['table']} WHERE source_id = :sid"),
                {"sid": source_id})
            # DISTINCT ON (r.ctid): a feature sitting on a county line
            # intersects two tiles and would otherwise be inserted twice -
            # which would quietly halve every "how many markets" answer and
            # never once look wrong.
            n = conn.execute(text(f"""
                INSERT INTO {spec['table']}
                    (name, {spec['type_col']}{pop_col}, county_code, geom,
                     source_id, source_date, confidence)
                SELECT DISTINCT ON (r.ctid)
                       r.name, r.kind{pop_val}, t.county_code,
                       {geom_sql},
                       :sid, :sd, :cf
                  FROM staging.{stage} r
                  LEFT JOIN staging.county_tiles t
                         ON ST_Intersects(r.geometry, t.geom)
                 ORDER BY r.ctid, t.county_code"""),
                {"sid": source_id, "sd": SOURCE_DATE,
                 "cf": spec["conf"]}).rowcount
        totals[spec["table"]] = n
        print(f"      loaded {n:,} rows")

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
               SET finished_at = now(), run_status = 'success', rows_out = :r
             WHERE run_id = :id"""),
            {"r": sum(totals.values()), "id": run_id})
        for code in ("transport.airports", "transport.bus_stops",
                     "transport.railways", "social.markets",
                     "social.public_services"):
            conn.execute(text("""
                UPDATE metadata.datasets
                   SET etl_status = 'ingested', updated_at = now()
                 WHERE code = :c"""), {"c": code})

    print("\n" + "=" * 70)
    for t, n in totals.items():
        print(f"   {t:28} {n:>8,}")
    print("=" * 70)
    print(f"DONE. {sum(totals.values()):,} rows. Run {run_id} logged as success.")
    print("\nVerify:")
    print("  SELECT place_type, count(*) FROM admin.places GROUP BY 1 ORDER BY 2 DESC;")
    print("  SELECT stop_type, count(*) FROM transport.bus_stops GROUP BY 1 ORDER BY 2 DESC;")
    print("  SELECT name FROM transport.airports ORDER BY name LIMIT 20;")

# BaseException, NOT Exception. This script's own guards raise SystemExit
# and Ctrl+C raises KeyboardInterrupt; both inherit from BaseException, so
# catching Exception would leave the etl_runs row saying 'running' forever
# and the next person would be debugging a lie.
except BaseException as exc:
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE metadata.etl_runs
               SET finished_at = now(), run_status = 'failed',
                   error_message = :e
             WHERE run_id = :id"""),
            {"e": f"{type(exc).__name__}: {exc}"[:2000], "id": run_id})
    print(f"\nFAILED: {type(exc).__name__}: {exc}")
    raise
