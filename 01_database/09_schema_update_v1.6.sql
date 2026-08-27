-- ============================================================================
-- SCHEMA UPDATE v1.6 - analytics.parcel_intelligence meets the actual data
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- ---------------------------------------------------------------------------
-- WHY THIS EXISTS
--   parcel_intelligence was designed in session 1, before a single dataset
--   had been built. Six sessions of findings now contradict it. The
--   enrichment engine is the next thing to write, and writing it against this
--   table would do one of two things, both bad:
--
--     1. CRASH. flood_risk_class permits four values; the flood layer has
--        six. 'very_low' is 67.82% of Kenya and is not in the constraint.
--     2. WORSE - QUIETLY ENCODE THE ERRORS THE PRODUCT RULES EXIST TO STOP.
--        coverage_4g is a boolean, which is exactly the claim rule D4
--        forbids. nightlights_trend_pct names the metric rule D11 says must
--        stay NULL forever.
--
--   A schema that disagrees with its data is not a schema, it is a trap with
--   a CREATE TABLE statement in front of it. This settles it BEFORE the
--   engine is written, so the engine gets written once.
--
-- ---------------------------------------------------------------------------
-- DESIGN DECISION (Njeri, session 7): the table STAYS WIDE.
--   One row per parcel, fixed in place, rather than moving to a long/EAV
--   form. Fast to query, matches the rest of the schema, and keeps CHECK
--   constraints doing real work. The cost - per-field provenance - is paid
--   with two jsonb columns at the end rather than 50 more numeric ones.
--
-- ---------------------------------------------------------------------------
-- SAFETY
--   Some changes DROP columns. That is only safe while the table is empty,
--   which it is: land.parcels is client data loaded at onboarding and no
--   client has onboarded. The script REFUSES TO RUN if either table has rows,
--   rather than trusting that assumption.
--
--   Everything else is ADD COLUMN IF NOT EXISTS or a guarded rename, so a
--   second run is a no-op.
--
-- Run once:  psql -U postgres -d land_intelligence_kenya -f 01_database/09_schema_update_v1.6.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. REFUSE TO RUN ON POPULATED TABLES
-- ---------------------------------------------------------------------------
DO $$
DECLARE n_intel bigint; n_parcels bigint;
BEGIN
    SELECT count(*) INTO n_intel   FROM analytics.parcel_intelligence;
    SELECT count(*) INTO n_parcels FROM land.parcels;
    IF n_intel > 0 OR n_parcels > 0 THEN
        RAISE EXCEPTION
            'REFUSING TO RUN: parcel_intelligence has % row(s), land.parcels '
            'has % row(s). This script drops columns and was written for an '
            'empty table. Migrate the data deliberately instead.',
            n_intel, n_parcels;
    END IF;
    RAISE NOTICE 'Both tables empty. Safe to proceed.';
END $$;


-- ===========================================================================
-- 1. FLOOD - four classes become six, and the radius becomes explicit
-- ===========================================================================
-- The layer ships SIX classes: 1 Very low, 2 Low, 3 Moderate, 4 High,
-- 5 Very high, 6 Permanent water. The constraint permitted four and omitted
-- the two that matter most in opposite directions: 'very_low' is 67.82% of
-- the country, and 'permanent_water' is the land-cover fact that rule D3
-- says must never render as "beyond very high".

DO $$
DECLARE c record;
BEGIN
    FOR c IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace ns ON ns.oid = rel.relnamespace
        WHERE ns.nspname = 'analytics'
          AND rel.relname = 'parcel_intelligence'
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) ILIKE '%flood_risk_class%'
    LOOP
        EXECUTE format(
            'ALTER TABLE analytics.parcel_intelligence DROP CONSTRAINT %I',
            c.conname);
        RAISE NOTICE 'dropped old flood constraint %', c.conname;
    END LOOP;
END $$;

ALTER TABLE analytics.parcel_intelligence
    ADD CONSTRAINT parcel_intelligence_flood_risk_class_check
    CHECK (flood_risk_class IS NULL OR flood_risk_class IN
           ('very_low','low','moderate','high','very_high','permanent_water'));

COMMENT ON COLUMN analytics.parcel_intelligence.flood_risk_class IS
    'RULE D2: this is the WORST class within flood_search_radius_m, NOT the '
    'parcel''s own cell. Garissa town centre reads Very low on its own pixel '
    'with Very high a few hundred metres away, because the town sits on a '
    'terrace. A buyer needs to know what is next door. '
    'RULE D1: MODELLED, not measured - every buyer-facing use must say so. '
    'RULE D3: permanent_water is a LAND-COVER FACT, never "beyond very high", '
    'and is not benign - see dist_permanent_water_m.';

-- The parcel's own cell, kept alongside so the two can be compared and a
-- report can say "the plot itself reads Low, but Very high begins 300 m away".
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS flood_risk_class_cell text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace ns ON ns.oid = rel.relnamespace
        WHERE ns.nspname='analytics' AND rel.relname='parcel_intelligence'
          AND con.conname='parcel_intelligence_flood_cell_check')
    THEN
        ALTER TABLE analytics.parcel_intelligence
            ADD CONSTRAINT parcel_intelligence_flood_cell_check
            CHECK (flood_risk_class_cell IS NULL OR flood_risk_class_cell IN
                   ('very_low','low','moderate','high','very_high',
                    'permanent_water'));
    END IF;
END $$;

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS flood_search_radius_m numeric DEFAULT 1000;
COMMENT ON COLUMN analytics.parcel_intelligence.flood_search_radius_m IS
    'Radius used for flood_risk_class. Recorded rather than assumed: a class '
    'without its radius is not reproducible, and the calibration proved a '
    'single-cell read tests the coordinate rather than the layer.';

-- RULE D3. This is what carries Budalangi's warning: it reads Moderate on
-- HAND because it floods by DIKE FAILURE, which HAND structurally cannot
-- see, but it sits beside permanent water.
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS dist_permanent_water_m numeric;
COMMENT ON COLUMN analytics.parcel_intelligence.dist_permanent_water_m IS
    'RULE D3: proximity to permanent water is its own risk signal and must be '
    'surfaced independently of flood_risk_class. Budalangi is the worked '
    'example - HAND cannot see dike failure, so the hazard class understates '
    'it and this column is what warns.';

-- Susceptibility x forcing, kept as TWO explainable numbers.
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS flood_forcing_max5day_mm numeric;
COMMENT ON COLUMN analytics.parcel_intelligence.flood_forcing_max5day_mm IS
    'From rainfall_max5day_mean. HAND says where water goes; this says how '
    'much arrives. Present as susceptibility x forcing, two numbers a buyer '
    'can follow - NEVER merged into one score with invented weights.';


-- ===========================================================================
-- 2. CONNECTIVITY - booleans become percentages (RULE D4)
-- ===========================================================================
-- The CA publishes SUBLOCATION polygons carrying a coverage PERCENTAGE, not
-- propagation contours. A boolean is a point-level guarantee the source never
-- made. And of the four boolean columns:
--     coverage_2g  - real data exists, but as a percentage
--     coverage_3g  - THERE IS NO 3G. The CA published one dataset under two
--                    technology names, 99.9% identical to six decimals; the
--                    duplicate was deleted. Unfillable.
--     coverage_4g  - real data, as a percentage
--     coverage_5g  - never collected. Unfillable.

DO $$
DECLARE n bigint;
BEGIN
    SELECT count(*) INTO n FROM analytics.parcel_intelligence;
    IF n > 0 THEN
        RAISE EXCEPTION 'Table not empty; refusing to drop coverage columns.';
    END IF;
END $$;

ALTER TABLE analytics.parcel_intelligence DROP COLUMN IF EXISTS coverage_2g;
ALTER TABLE analytics.parcel_intelligence DROP COLUMN IF EXISTS coverage_3g;
ALTER TABLE analytics.parcel_intelligence DROP COLUMN IF EXISTS coverage_4g;
ALTER TABLE analytics.parcel_intelligence DROP COLUMN IF EXISTS coverage_5g;

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS coverage_2g_pct numeric
        CHECK (coverage_2g_pct IS NULL OR coverage_2g_pct BETWEEN 0 AND 100);
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS coverage_4g_pct numeric
        CHECK (coverage_4g_pct IS NULL OR coverage_4g_pct BETWEEN 0 AND 100);
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS coverage_4g_pct_safaricom numeric
        CHECK (coverage_4g_pct_safaricom IS NULL
               OR coverage_4g_pct_safaricom BETWEEN 0 AND 100);
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS coverage_4g_pct_telkom numeric
        CHECK (coverage_4g_pct_telkom IS NULL
               OR coverage_4g_pct_telkom BETWEEN 0 AND 100);

-- A percentage is meaningless without knowing what it is a percentage OF.
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS coverage_admin_level text
        CHECK (coverage_admin_level IS NULL OR coverage_admin_level IN
               ('sublocation','location','ward','constituency','county'));
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS coverage_admin_name text;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS coverage_vintage date;

COMMENT ON COLUMN analytics.parcel_intelligence.coverage_4g_pct IS
    'RULE D4: the share of the SUBLOCATION containing this parcel that the CA '
    'reports as 4G-covered. Say "the area around this parcel is about 65% '
    '4G-covered". NEVER "this parcel has 4G". Pair with dist_tower_m, which '
    'IS point-specific. '
    'UNRESOLVED (checklist B1): the CA published 3G and 4G as one dataset '
    'under two names. If we kept the mislabelled survivor, what this column '
    'calls 4G may be 3G.';
COMMENT ON COLUMN analytics.parcel_intelligence.coverage_4g_pct_safaricom IS
    'RULE D5: AIRTEL IS ABSENT FROM THIS TABLE BECAUSE THE CA DID NOT PUBLISH '
    'AN AIRTEL PERCENTAGE - absence of DATA, not absence of coverage. Any '
    'per-operator display must say so explicitly.';
COMMENT ON COLUMN analytics.parcel_intelligence.coverage_vintage IS
    'RULE D12: CA vintages run Jan 2022 to Aug 2023 and are NOT comparable '
    'across technologies (2G covers 9,274 polygons, 4G covers 7,134). '
    'Per-parcel lookup is fine; national cross-technology comparison is not.';

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS dist_tower_m numeric;
COMMENT ON COLUMN analytics.parcel_intelligence.dist_tower_m IS
    'Nearest cell tower, connectivity.towers (OpenCellID, confidence 2 - '
    'crowdsourced positions). The point-level half of the D4 pairing.';


-- ===========================================================================
-- 3. NIGHTLIGHTS - off the metric that was disproved (RULE D11)
-- ===========================================================================
-- nightlights_trend_pct enshrines the percentage rate that ranked rural
-- electrification above the peri-urban land market: median ward 33%/yr, an
-- 11x brightening over nine years, because 335 of 1,422 wards had a 2015
-- baseline of exactly zero. Top-50 rank overlap with the metric that won was
-- 0/50. The column is renamed, not kept alongside, so it cannot be populated
-- by habit.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='analytics'
                 AND table_name='parcel_intelligence'
                 AND column_name='nightlights_trend_pct')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='analytics'
                 AND table_name='parcel_intelligence'
                 AND column_name='nightlights_trend_radiance_yr')
    THEN
        ALTER TABLE analytics.parcel_intelligence
            RENAME COLUMN nightlights_trend_pct TO nightlights_trend_radiance_yr;
        RAISE NOTICE 'renamed nightlights_trend_pct -> nightlights_trend_radiance_yr';
    END IF;
END $$;

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS nightlights_trend_radiance_yr numeric;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS nightlights_admin_unit text;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS nightlights_radiance_mean numeric;

COMMENT ON COLUMN analytics.parcel_intelligence.nightlights_trend_radiance_yr IS
    'The development signal: ABSOLUTE change in summed radiance per year. '
    'RULE D10: this is a SUM and scales with unit area - never compare a large '
    'ward to a small one on it directly; use nightlights_radiance_mean for '
    'like-for-like. RULE D11: the percentage version is deliberately dead. '
    'RULE D13: radiance is not linear in economic activity - VIIRS compresses '
    'bright cores, and SNPP''s sensor degraded across the series.';
COMMENT ON COLUMN analytics.parcel_intelligence.nightlights_admin_unit IS
    'Which ward this parcel inherited its nightlights figures from. Required '
    'by D10: without the unit, the SUM cannot be interpreted. NOTE 3 of 1,425 '
    'wards return no data in any year (checklist C7) and will be NULL here.';


-- ===========================================================================
-- 4. RAINFALL - one column becomes six
-- ===========================================================================
-- climate.rainfall now holds a 30-year normal, a recent mean, an anomaly, a
-- driest-year, and two extremes. One numeric column cannot carry that, and
-- the missing one is the drought signal: 2021-2025 averages 107% of normal
-- while 68.9% of Kenya had a year under 75% of normal.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='analytics' AND table_name='parcel_intelligence'
                 AND column_name='rainfall_mm_yr')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='analytics' AND table_name='parcel_intelligence'
                 AND column_name='rainfall_normal_mm_yr')
    THEN
        ALTER TABLE analytics.parcel_intelligence
            RENAME COLUMN rainfall_mm_yr TO rainfall_normal_mm_yr;
        RAISE NOTICE 'renamed rainfall_mm_yr -> rainfall_normal_mm_yr';
    END IF;
END $$;

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS rainfall_normal_mm_yr    numeric;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS rainfall_recent_mm_yr    numeric;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS rainfall_anomaly_pct     numeric;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS rainfall_driest_year_pct numeric;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS rainfall_max5day_mean_mm numeric;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS rainfall_max5day_p90_mm  numeric;

COMMENT ON COLUMN analytics.parcel_intelligence.rainfall_normal_mm_yr IS
    'CHIRPS v3.0 1991-2020 WMO normal. The CLIMATOLOGY, and the right input '
    'for "can I farm here". RULE C5: THIS LAYER RUNS WET, about +145 mm across '
    '16 reference towns - partly CHIRPS over steep terrain with thin gauge '
    'density, partly our reference figures being approximate. Do not treat as '
    'calibrated.';
COMMENT ON COLUMN analytics.parcel_intelligence.rainfall_driest_year_pct IS
    'The driest single year of 2021-2025 as a percentage of normal. THIS IS '
    'THE COLUMN THAT STOPS A MEAN HIDING A DROUGHT: the window averages 107% '
    'of normal while 68.9% of Kenya had a year under 75% and 8.6% under 50%. '
    'Use for "how bad does it get here"; use the anomaly for "what has it '
    'been like lately".';
COMMENT ON COLUMN analytics.parcel_intelligence.rainfall_max5day_mean_mm IS
    'CHIRPS v2.0 (v3.0 publishes no pentad product - checklist C11). From '
    'FIXED pentads, so a storm straddling a boundary is split: this '
    'UNDER-ESTIMATES a true rolling 5-day maximum by roughly 10-20%, '
    'consistently nationally, so the spatial pattern is sound. '
    'NEVER quote as design rainfall for engineering (C12).';


-- ===========================================================================
-- 5. LAND COVER - reference and recency are different questions
-- ===========================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='analytics' AND table_name='parcel_intelligence'
                 AND column_name='landcover_class')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='analytics' AND table_name='parcel_intelligence'
                 AND column_name='landcover_class_worldcover')
    THEN
        ALTER TABLE analytics.parcel_intelligence
            RENAME COLUMN landcover_class TO landcover_class_worldcover;
        RAISE NOTICE 'renamed landcover_class -> landcover_class_worldcover';
    END IF;
END $$;

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS landcover_class_worldcover text;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS landcover_class_io text;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS landcover_io_year integer;

COMMENT ON COLUMN analytics.parcel_intelligence.landcover_class_worldcover IS
    'ESA WorldCover 2021 v200, 10 m, 11 classes. THE CLASSIFICATION REFERENCE '
    'for "what is this exact spot". RULE D6: NEVER tell a buyer "this is not '
    'farmland" from land cover alone - WorldCover under-detects smallholder '
    'mosaic farming, and NDVI showed up to 4.2x the mapped cropland area is as '
    'green as cropland. Use NDVI + rainfall + soil together.';
COMMENT ON COLUMN analytics.parcel_intelligence.landcover_class_io IS
    'Impact Observatory, 9 classes, ~93 m. The RECENCY layer (ESA published '
    'nothing after 2021). IO "Rangeland" absorbs BOTH WorldCover Shrubland AND '
    'Grassland, so the two CANNOT be compared class by class. IO "Built area" '
    'is definitionally broader than WorldCover Built-up - about 7x at the 2017 '
    'baseline, before any drift - so never present them as one quantity. '
    'THE IO CHANGE LAYER IS QUARANTINED (pending_review) and must not be used: '
    'the series is not temporally consistent. Checklist C13.';


-- ===========================================================================
-- 6. SOILS - black cotton needs BOTH layers (RULE D7)
-- ===========================================================================
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS black_cotton_risk text
        CHECK (black_cotton_risk IS NULL OR black_cotton_risk IN
               ('none','possible','likely'));
COMMENT ON COLUMN analytics.parcel_intelligence.black_cotton_risk IS
    'RULE D7: derived from SoilGrids Vertisols OR iSDA clay texture, NEVER '
    'either alone. SoilGrids maps the Athi-Kapiti plains as Luvisols when they '
    'are classic black cotton - and that is exactly where Nairobi peri-urban '
    'selling is most active. iSDA reads Clay Loam there. '
    'likely = both agree; possible = one of the two; none = neither.';


-- ===========================================================================
-- 7. BUILT-UP, NDVI, POPULATION - rules that change what may be said
-- ===========================================================================
COMMENT ON COLUMN analytics.parcel_intelligence.built_up_pct_1km IS
    'RULE D8: a FULL CELL IS 8,606 m2, not 8,548, and the fraction MUST be '
    'capped at 1.0. GHSL is computed on an equal-area Mollweide grid and '
    'regridded to lat/lon, so its cell does not match a naive WGS84 '
    'calculation. Divide by the wrong constant and a parcel reads "101% '
    'built". Sum square metres over the neighbourhood, then divide by that '
    'neighbourhood''s true area - percentages do not add.';

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS ndvi_year integer;
COMMENT ON COLUMN analytics.parcel_intelligence.ndvi_mean IS
    'Sentinel-2 geomedian NDVI. CHECKLIST C6: this is a SINGLE YEAR, not a '
    'normal, and 2024 was wet after the 2020-23 drought. The enrichment engine '
    'must NOT treat it as a stable baseline. ndvi_year records which year, so '
    'a report can say so.';

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS pop_is_census_calibrated boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN analytics.parcel_intelligence.pop_density_km2 IS
    'WorldPop 2020 constrained. RULE D9: PREFER RELATIVE COMPARISONS ("more '
    'people near A than B") over absolute counts until the KNBS census is '
    'loaded. WorldPop reads +16% against the 2019 census nationally and +209% '
    'in Mandera. Do NOT rescale the grid to the census - that buries a real '
    'disagreement inside an authoritative-looking number.';
COMMENT ON COLUMN analytics.parcel_intelligence.pop_is_census_calibrated IS
    'FALSE until KNBS county/ward census is loaded (checklist C3, B3). While '
    'false, the API and PDF layers must suppress absolute population claims. '
    'This makes rule D9 enforceable in code instead of remembered.';


-- ===========================================================================
-- 8. PER-FIELD PROVENANCE - the cost of staying wide, paid in jsonb
-- ===========================================================================
-- Every other table in this database carries source_id, source_date and
-- confidence. parcel_intelligence carried only engine_version, so a number
-- could not name where it came from or how well it is known. Two jsonb maps
-- keep that without 50 more columns.
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS field_confidence jsonb;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS field_sources jsonb;

COMMENT ON COLUMN analytics.parcel_intelligence.field_confidence IS
    'Per-field confidence 1-5, e.g. {"soil_ph": 3, "flood_risk_class": 3, '
    '"dist_any_road_m": 4}. Confidence is not uniform across a row: roads are '
    '4, health facilities are 2 because they sit at ward centroids, flood is '
    '3 because it is modelled. A report that prints one confidence for the '
    'whole parcel is lying about most of it.';
COMMENT ON COLUMN analytics.parcel_intelligence.field_sources IS
    'Per-field lineage, e.g. {"soil_ph": {"raster_id": 12, "checksum": "..."}}. '
    'Rasters are versioned and re-run; without this, a number computed today '
    'cannot be reproduced after the next re-run. The raster catalogue is the '
    'truth about a file - this records WHICH truth was used.';


-- ===========================================================================
-- 9. COLUMNS AWAITING DATA - marked so nobody mistakes unbuilt for broken
-- ===========================================================================
COMMENT ON COLUMN analytics.parcel_intelligence.dist_power_line_m IS
    'AWAITING DATA: utilities.power_distribution (P1, one of only two P1 '
    'datasets not built). BLOCKED EXTERNALLY on a Kenya Power derived-use '
    'licence - permission to store "nearest MV line: 340 m" without '
    'redistributing the network. Checklist A5. Interim proxy: OSM power lines '
    'plus nightlights.';
COMMENT ON COLUMN analytics.parcel_intelligence.dist_transformer_m IS
    'AWAITING DATA: utilities.power_facilities (P2, Kenya Power). Transformer '
    'distance approximates connection COST, which is the buyer question.';
COMMENT ON COLUMN analytics.parcel_intelligence.zoning_class IS
    'AWAITING DATA: land.zoning (P2). County physical plans, often hard copy, '
    'digitised per pilot county.';
COMMENT ON COLUMN analytics.parcel_intelligence.landslide_risk_class IS
    'AWAITING DATA: hazards.landslide (P2, Geocode-derived from slope + '
    'rainfall + soil). All three inputs are now built.';
COMMENT ON COLUMN analytics.parcel_intelligence.in_wetland IS
    'AWAITING DATA: environment.wetlands (P2). Building on wetland is a top '
    'buyer risk. NOTE 3,383 OSM wetland/riverbank polygons were deliberately '
    'skipped in session 2 pending a better source.';
COMMENT ON COLUMN analytics.parcel_intelligence.aspect_dominant IS
    'AWAITING DATA: terrain.aspect (P2). Derivable from the DEM we hold.';
COMMENT ON COLUMN analytics.parcel_intelligence.soil_drainage IS
    'AWAITING DATA: soils.drainage (P2, Geocode-derived from texture + TWI). '
    'Both inputs are built.';
COMMENT ON COLUMN analytics.parcel_intelligence.soil_depth_class IS
    'AWAITING DATA: soils.depth (P2, iSDA/SoilGrids).';
COMMENT ON COLUMN analytics.parcel_intelligence.soil_fertility IS
    'AWAITING DATA: soils.fertility (P2, Geocode composite of pH, carbon, '
    'nutrients).';
COMMENT ON COLUMN analytics.parcel_intelligence.temp_mean_c IS
    'AWAITING DATA: climate.temperature (P2, ERA5 / NASA POWER).';
COMMENT ON COLUMN analytics.parcel_intelligence.solar_kwh_m2_day IS
    'AWAITING DATA: climate.solar (P3, Global Solar Atlas). Off-grid potential.';
COMMENT ON COLUMN analytics.parcel_intelligence.dist_sewer_m IS
    'AWAITING DATA: utilities.sewer_lines (P3, county governments). Urban '
    'parcels only.';
COMMENT ON COLUMN analytics.parcel_intelligence.dist_water_line_m IS
    'AWAITING DATA: utilities.water_lines (P3, county governments / WASREB).';
COMMENT ON COLUMN analytics.parcel_intelligence.dist_bus_stop_m IS
    'AWAITING DATA: transport.bus_stops (P2, OSM). Matatu stage proximity '
    'matters to buyers.';
COMMENT ON COLUMN analytics.parcel_intelligence.dist_market_m IS
    'AWAITING DATA: social.markets (P2, county governments). Key for '
    'agricultural buyers.';
COMMENT ON COLUMN analytics.parcel_intelligence.dist_police_m IS
    'AWAITING DATA: social.public_services (P2, OSM).';
COMMENT ON COLUMN analytics.parcel_intelligence.dist_fiber_m IS
    'AWAITING DATA: connectivity.fiber (P3, CA NOFBI backbone, by request).';

-- Built and ready to populate, but with a caveat the engine must carry.
COMMENT ON COLUMN analytics.parcel_intelligence.dist_hospital_m IS
    'social.health, 12,403 facilities. CHECKLIST C8: located to WARD CENTROID, '
    'not true GPS (confidence 2) - the openAFRICA export carries no '
    'coordinates. 82% matched a ward; only 9 pharmacies loaded. Attributes '
    '(KEPH level, ownership, MFL code) are exact; the POSITION is not. Do not '
    'quote this distance to the metre.';
COMMENT ON COLUMN analytics.parcel_intelligence.in_riparian_buffer IS
    'environment.riparian_buffers, Geocode-derived under EMCA 2009 (6 m min, '
    '30 m max from the high-water mark), Water (Resources) Regs 2025, Survey '
    'Regs Cap 299. Buffered from the river CENTRE LINE because OSM gives no '
    'channel width, so very wide rivers are slightly under-measured. '
    'Confidence 3: a rules-based estimate, NOT a surveyed boundary. This is '
    'high-value and under-served - a parcel overlapping a riparian reserve is '
    'partly unbuildable by law - so state the basis, never assert the line.';


-- ===========================================================================
-- 10. INDEXES the enrichment engine and the API will actually use
-- ===========================================================================
CREATE INDEX IF NOT EXISTS idx_parcel_intel_parcel_active
    ON analytics.parcel_intelligence (parcel_id)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_parcel_intel_run
    ON analytics.parcel_intelligence (run_id);
CREATE INDEX IF NOT EXISTS idx_parcel_intel_flood
    ON analytics.parcel_intelligence (flood_risk_class)
    WHERE status = 'active';

COMMIT;

\echo ''
\echo '=== v1.6 APPLIED ============================================='
\echo 'Flood classes now permitted:'

SELECT pg_get_constraintdef(con.oid) AS flood_constraint
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
WHERE ns.nspname='analytics' AND rel.relname='parcel_intelligence'
  AND con.conname='parcel_intelligence_flood_risk_class_check';

\echo ''
\echo 'Coverage columns (expect percentages, no booleans, no 3g/5g):'

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='analytics' AND table_name='parcel_intelligence'
  AND column_name LIKE 'coverage%'
ORDER BY column_name;

\echo ''
\echo 'Rainfall columns (expect six):'

SELECT column_name
FROM information_schema.columns
WHERE table_schema='analytics' AND table_name='parcel_intelligence'
  AND column_name LIKE 'rainfall%'
ORDER BY column_name;

\echo ''
\echo 'Total columns on parcel_intelligence, and how many carry a comment:'

SELECT count(*) AS columns,
       count(col_description(
           ('analytics.parcel_intelligence')::regclass::oid, ordinal_position
       )) AS documented
FROM information_schema.columns
WHERE table_schema='analytics' AND table_name='parcel_intelligence';

\echo ''
\echo 'NEXT: the enrichment engine. It reads this table''s COMMENTS as its'
\echo 'specification - every product rule that constrains a value now lives'
\echo 'on the column that holds it, not only in a checklist.'
\echo ''
