-- ===========================================================================
-- SCHEMA UPDATE v1.10 - "NONE" IS NOT A CLEARANCE
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- WHY THIS EXISTS
--   black_cotton_risk returns 'none' on ground the check cannot actually
--   clear. field_sources has said so on every parcel since C16 was written:
--
--     "Where this reads 'none' on flat peri-urban land around Nairobi, the
--      report must say the check is inconclusive - NOT that the ground is
--      safe."
--
--   That sentence is prose sitting in a JSON column. Nothing enforces it.
--   What actually enforced it was a bare literal - `slope < 3.5` - written
--   TWICE in report_content.py, and NOT ONCE in the engine that knows why
--   the rule exists. Section 6: a rule you have to remember is a reminder.
--   The engine now decides, once, and every renderer asks the row.
--
-- WHAT IT FIRES ON
--   black_cotton_risk = 'none' AND (slope < 3.5 deg OR slope unknown), and
--   also whenever no soil data returned at all. It FAILS TOWARD
--   INCONCLUSIVE: if we cannot see the landform we certainly cannot clear
--   the soil.
--
--   It fires on Karen, which is Nitisols and genuinely stable. That is not a
--   bug. SoilGrids cannot separate Karen from the Athi-Kapiti plains on any
--   signal this database holds - measured, both discriminators point the
--   wrong way - so on flat ground the honest statement is that the check
--   does not settle it. Over-flagging costs a seller one line of caution.
--   Under-flagging puts a house on ground that moves.
--
--   Geography is deliberately NOT part of the test. "Peri-urban Nairobi" has
--   no boundary in this database and inventing one would be a claim we
--   cannot source (D20).
--
-- WHAT IT DOES NOT DO
--   It does not change black_cotton_risk. The taxonomy arm of D7 is still
--   the only arm implemented and C16 is still an open, documented gap. This
--   column does not close the gap - it makes the gap impossible to render
--   as an absence of one.
--
-- Run from 01_database with psql:
--   psql -U postgres -d land_intelligence_kenya -f 13_schema_update_v1.10.sql
-- ===========================================================================

BEGIN;

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS black_cotton_inconclusive boolean;

COMMENT ON COLUMN analytics.parcel_intelligence.black_cotton_inconclusive IS
  'TRUE when black_cotton_risk = ''none'' cannot be trusted as a clearance: '
  'flat ground (< 3.5 deg), unknown slope, or no soil data at all. Set by '
  'the enrichment engine, not by a renderer. Where this is TRUE the page '
  'must say a soil test is needed and must NOT present ''none'' as safe '
  'ground. Checklist C16. Fires on Karen as well as Athi - that is intended, '
  'because no signal we hold separates them.';

COMMIT;
