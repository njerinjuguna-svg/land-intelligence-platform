-- ============================================================================
-- SCHEMA UPDATE v1.7 - flood_nearby_pct
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- WHY, and it comes from a bug the test parcels caught on the first run
--   The enrichment engine returned flood_risk_class = 'very_high' for 11 of
--   12 test parcels, INCLUDING Karen - whose own footprint is 100% very_low,
--   and which is prime Nairobi residential land.
--
--   Cause: "worst class within 1 km" was taking the maximum over ANY class
--   present in the buffer, and a single cell was enough. Channel cells are
--   set to HAND = 0 and therefore classify Very high (checklist C10: over
--   half the top class is the watercourse itself), and there is a channel
--   within 1 km of almost anywhere in Kenya.
--
--   So rule D2 was being obeyed literally and defeated in substance: a
--   warning that fires everywhere distinguishes nothing, and would have
--   devalued prime land on a stray pixel.
--
--   The fix requires a class to occupy a meaningful SHARE of the surroundings
--   before it may set flood_risk_class. This column carries that share, so
--   the number travels with the word it justifies.
--
-- Run once:  psql -U postgres -d land_intelligence_kenya -f 01_database/10_schema_update_v1.7.sql
-- ============================================================================

BEGIN;

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS flood_nearby_pct numeric
        CHECK (flood_nearby_pct IS NULL
               OR flood_nearby_pct BETWEEN 0 AND 100);

COMMENT ON COLUMN analytics.parcel_intelligence.flood_nearby_pct IS
    'What share of the area within flood_search_radius_m actually carries the '
    'class named in flood_risk_class. REQUIRED CONTEXT, not decoration: '
    '"Very high across 28% of the surroundings" and "Very high on 0.2% of '
    'the surroundings" are different statements and must never collapse to '
    'the same word in a report. 0 means nothing nearby reached the materiality '
    'threshold and flood_risk_class is the parcel''s own reading. '
    'Added after the enrichment engine flagged Karen - 100% very_low on its '
    'own footprint - as very_high from a single channel cell within 1 km.';

COMMIT;

\echo ''
\echo 'v1.7 applied. Verify:'

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'analytics' AND table_name = 'parcel_intelligence'
  AND column_name LIKE 'flood%'
ORDER BY column_name;
