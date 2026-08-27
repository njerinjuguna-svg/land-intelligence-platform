-- ============================================================================
-- SCHEMA UPDATE v1.3
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
-- Date: 2026-07-18
--
-- Purpose: allow 'other' as a water point type.
--
-- Why: real-world water point datasets (WPDx) carry more source types than
-- our original five (borehole, spring, water_kiosk, treatment_plant,
-- storage_tank), e.g. hand-dug wells, surface water, rainwater harvesting.
-- Rather than discard genuine water points that do not fit those five, we
-- add a neutral 'other' bucket. Better a catalogued point typed 'other'
-- than a silently dropped one.
-- ============================================================================

ALTER TABLE utilities.water_points
    DROP CONSTRAINT IF EXISTS water_points_point_type_check;

ALTER TABLE utilities.water_points
    ADD CONSTRAINT water_points_point_type_check
    CHECK (point_type IN ('borehole', 'spring', 'water_kiosk',
                          'treatment_plant', 'storage_tank', 'well', 'other'));

-- Verify:
-- SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
-- WHERE conname = 'water_points_point_type_check';
