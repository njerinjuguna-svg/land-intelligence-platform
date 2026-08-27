-- ===========================================================================
-- SCHEMA UPDATE v1.8 - LANDMARKS
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- WHY THIS EXISTS
--   The buyer page asks "what famous things are near this land" - the
--   highway, the airport, the town, the railway station. Those are the
--   references a Kenyan buyer actually orients by, and none of them are
--   answerable today.
--
--   Four distance columns for this already exist and are empty
--   (dist_town_centre_m, dist_bus_stop_m, dist_market_m, dist_police_m).
--   Their source tables exist and are empty too. So most of this work is
--   an ETL, not a migration. This file adds only the two things that are
--   genuinely missing.
--
-- 1. admin.places - there is no table anywhere for a town or city centre,
--    so dist_town_centre_m has never had anywhere to measure FROM.
--
-- 2. NAMES, not just distances. Every other distance in this schema is
--    anonymous on purpose: a buyer does not care WHICH clinic is 1.3 km
--    away, only that one is. Landmarks invert that. "18 km from a city"
--    is nearly useless; "18 km from Nairobi" is the whole point, because
--    the name is what carries the buyer's own knowledge of the place.
--    So these columns come in pairs, and the name is not decoration.
--
-- Run from 01_database with psql:
--   psql -U postgres -d land_intelligence_kenya -f 11_schema_update_v1.8.sql
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. admin.places
--
-- Populated centres from the OSM places layer: cities, towns, suburbs and
-- villages. Stored as POINTS even where OSM has a polygon, because the
-- question is "how far to the centre of town", and a centroid answers it
-- while a boundary would answer "how far to the edge of the built-up area" -
-- a different and much smaller number that would flatter every parcel.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admin.places (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL,
    place_type  text NOT NULL,
    population  integer,
    county_code text,
    geom        public.geometry(Point, 4326) NOT NULL,
    source_id   integer,
    source_date date,
    confidence  smallint,
    version     integer   NOT NULL DEFAULT 1,
    status      text      NOT NULL DEFAULT 'active',
    created_at  timestamp with time zone NOT NULL DEFAULT now(),
    updated_at  timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT places_confidence_check CHECK (confidence BETWEEN 1 AND 5),
    CONSTRAINT places_status_check CHECK (status = ANY (ARRAY[
        'active'::text, 'superseded'::text, 'pending_review'::text,
        'rejected'::text])),
    CONSTRAINT places_type_check CHECK (place_type = ANY (ARRAY[
        'national_capital'::text, 'city'::text, 'town'::text,
        'suburb'::text, 'village'::text]))
);

CREATE INDEX IF NOT EXISTS places_geom_idx   ON admin.places USING gist (geom);
CREATE INDEX IF NOT EXISTS places_type_idx   ON admin.places (place_type);
CREATE INDEX IF NOT EXISTS places_status_idx ON admin.places (status);

COMMENT ON TABLE admin.places IS
  'Populated centres (city/town/suburb/village) as points. The measure-from '
  'geometry for dist_town_centre_m. Points not polygons: the question is '
  'distance to the CENTRE, and an edge would flatter every parcel.';

-- ---------------------------------------------------------------------------
-- 2. Named-landmark columns on analytics.parcel_intelligence
--
-- Paired name + distance. A NULL name with a non-NULL distance is a bug,
-- not a partial answer: if we cannot say which airport it is, the number
-- means nothing to a buyer and should not be shown.
-- ---------------------------------------------------------------------------
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS nearest_town_name              text,
    ADD COLUMN IF NOT EXISTS nearest_town_type              text,
    ADD COLUMN IF NOT EXISTS dist_airport_m                 double precision,
    ADD COLUMN IF NOT EXISTS nearest_airport_name           text,
    ADD COLUMN IF NOT EXISTS dist_major_road_m              double precision,
    ADD COLUMN IF NOT EXISTS nearest_major_road_name        text,
    ADD COLUMN IF NOT EXISTS dist_railway_station_m         double precision,
    ADD COLUMN IF NOT EXISTS nearest_railway_station_name   text;

COMMENT ON COLUMN analytics.parcel_intelligence.nearest_major_road_name IS
  'The NAME or ref of the nearest motorway/trunk/primary road - "Thika '
  'Superhighway", "A104". Distinct from dist_paved_road_m, which is the '
  'nearest surfaced road of ANY class and is anonymous on purpose.';

COMMENT ON COLUMN analytics.parcel_intelligence.dist_airport_m IS
  'Nearest airport or airstrip. Sourced from OSM, not KCAA: we publish a '
  'DISTANCE, which is a value and not a conveyance, so the by-request KCAA '
  'licence is not engaged. Swap the source, not the column, if KCAA lands.';

COMMIT;

-- ---------------------------------------------------------------------------
-- WHAT THIS FILE DELIBERATELY DOES NOT DO
--
-- It does not rename transport.bus_stops, which after etl_30 will hold every
-- public-transport stop - bus stops, bus stations, matatu stages, railway
-- stations and halts - distinguished by stop_type. The table's name is
-- narrower than its contents and that is a real (if small) trap for the next
-- person. Renaming it would break etl_ and engine references for a cosmetic
-- gain, so it is logged as a checklist item instead of done quietly here.
-- ---------------------------------------------------------------------------
