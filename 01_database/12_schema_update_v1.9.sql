-- ===========================================================================
-- SCHEMA UPDATE v1.9 - THE AIRPORT A BUYER CAN ACTUALLY USE
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- WHY THIS EXISTS
--   Every one of the eight OAK GROVE plots came back with
--
--       nearest_airport_name = GSU Airstrip     ~6.9 km
--
--   which is true, correctly measured, in service, and useless. It is the
--   General Service Unit's airstrip. No land buyer will ever fly from it.
--
--   This is the SAME failure as "Shekiko Airport (disused)" one layer
--   deeper, and it is worth naming precisely because the first fix does not
--   catch it. That one was a facility out of service, and OSM said so in the
--   name, so a word filter could see it. This one is fully operational; what
--   it is not is PUBLIC. Nothing in the name, the geometry or the OSM tags
--   says so. A filter cannot find it because the defect is not in the data.
--
--   The defect is in the QUESTION. "Nearest airport" is not what a buyer is
--   asking. They are asking "where would I fly from", and those are the same
--   question only where every airport takes passengers.
--
-- WHY NOT JUST EXCLUDE AIRSTRIPS
--   Because `domestic` is not a fact we hold. etl_30 infers it by NAME - an
--   airport is `international` if it says so and `domestic` otherwise - so
--   `domestic` is a DEFAULT, not a finding, and it contains bush strips
--   indistinguishable from GSU. Filtering on it would trade a visibly wrong
--   answer for an invisibly wrong one, which is worse.
--
--   `international` IS verified: four facilities, each named so by its
--   operator - JKIA, Moi, Kisumu, Eldoret. So that is what gets its own
--   column, and it is the one shown to buyers.
--
--   dist_airport_m stays exactly as it is and keeps answering "the nearest
--   aviation facility of any kind". It is a real number and some buyers want
--   it. It just has to be LABELLED as an airstrip on the page, not as an
--   airport, because the difference is the entire point.
--
-- Run from 01_database with psql:
--   psql -U postgres -d land_intelligence_kenya -f 12_schema_update_v1.9.sql
-- ===========================================================================

BEGIN;

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS dist_intl_airport_m       double precision,
    ADD COLUMN IF NOT EXISTS nearest_intl_airport_name text;

COMMENT ON COLUMN analytics.parcel_intelligence.dist_intl_airport_m IS
  'Nearest airport whose operator calls it international - the only aviation '
  'class this database can verify rather than infer. THIS is the airport a '
  'buyer is asked to picture. Distinct from dist_airport_m, which is the '
  'nearest aviation facility of ANY kind and is frequently a private or '
  'military airstrip nobody can fly from.';

COMMENT ON COLUMN analytics.parcel_intelligence.dist_airport_m IS
  'Nearest aviation facility of any kind, including private and military '
  'airstrips. NEVER label this "nearest airport" on a buyer-facing page: on '
  'all eight OAK GROVE plots it resolves to the GSU (police) airstrip. Use '
  'dist_intl_airport_m for that, and call this one an airstrip.';

COMMIT;
