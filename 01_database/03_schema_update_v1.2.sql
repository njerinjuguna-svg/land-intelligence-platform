-- ============================================================================
-- SCHEMA UPDATE v1.2
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
-- Date: 2026-07-17
--
-- Purpose: add waterway_type to environment.rivers.
--
-- Why: river_class is reserved for hydrological regime (perennial/seasonal),
-- which OSM shapefiles do not provide. OSM DOES provide the physical type
-- (river, stream, canal, drain), which matters for flood-risk context:
-- a parcel 30 m from a river is a different proposition to a parcel 30 m
-- from a drainage ditch. Two facts, two columns. river_class stays NULL
-- until a hydrological source (e.g. WRA) fills it.
-- ============================================================================

ALTER TABLE environment.rivers
    ADD COLUMN IF NOT EXISTS waterway_type text
    CHECK (waterway_type IN ('river', 'stream', 'canal', 'drain'));

COMMENT ON COLUMN environment.rivers.waterway_type IS
    'Physical channel type from OSM: river, stream, canal, drain. '
    'Distinct from river_class (perennial/seasonal), which awaits a hydrological source.';

-- Verify:
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_schema = 'environment' AND table_name = 'rivers';
