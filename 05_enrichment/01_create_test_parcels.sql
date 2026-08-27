-- ============================================================================
-- TEST PARCELS - synthetic land for building and verifying the enrichment engine
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- ---------------------------------------------------------------------------
-- WHY THIS EXISTS
--   land.parcels is client data loaded at onboarding, and no client has
--   onboarded. So there is nothing to enrich, and an enrichment engine cannot
--   be built - let alone verified - against an empty table.
--
--   These are synthetic parcels at places SIX SESSIONS OF LANDMARK TESTING
--   HAVE ALREADY VALIDATED. Every one carries its expected reading, written
--   down BEFORE the engine has run.
--
--   That is checklist rule E4 satisfied by construction: "a verification that
--   prints the model's own output is not a test - name the expected answers
--   before choosing the metric." Here the expected answers are in the
--   database, in a column, dated earlier than the engine that will be judged
--   against them.
--
-- ---------------------------------------------------------------------------
-- WHY REAL POLYGONS AND NOT POINTS
--   Lesson 18, and lesson 21 which repeated it: "a test that probes one cell
--   tests the coordinate." Budalangi read 11.4 m HAND on a single cell and
--   0.0 m read properly across a neighbourhood. Both numbers were correct;
--   only one was about the place.
--
--   So these are polygons at plausible Kenyan subdivision sizes - an eighth
--   of an acre in peri-urban Nairobi, fifty acres in the Tana delta - because
--   the enrichment engine samples a FOOTPRINT, and a test that hands it a
--   point tests something the product never does.
--
-- ---------------------------------------------------------------------------
-- SAFE AND REMOVABLE
--   Everything is owned by one company whose slug is 'geocode-test'. To
--   remove all of it:
--
--       DELETE FROM analytics.parcel_intelligence WHERE parcel_id IN
--           (SELECT parcel_id FROM land.parcels WHERE company_id =
--            (SELECT company_id FROM clients.companies WHERE slug='geocode-test'));
--       DELETE FROM land.parcels WHERE company_id =
--           (SELECT company_id FROM clients.companies WHERE slug='geocode-test');
--       DELETE FROM clients.companies WHERE slug='geocode-test';
--
--   Idempotent: re-running replaces the parcels rather than duplicating them.
--
-- Run:  psql -U postgres -d land_intelligence_kenya -f 05_enrichment/01_create_test_parcels.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. A test client. NOT a real company - the name says so, loudly, because a
--    test row that looks like a customer eventually gets treated as one.
-- ---------------------------------------------------------------------------
INSERT INTO clients.companies (name, slug, contact_email, is_active, notes)
VALUES ('ZZ TEST - Geocode Internal Verification',
        'geocode-test',
        'njerinjuguna943@gmail.com',
        false,
        'SYNTHETIC TEST DATA - NOT A CLIENT. Owns the landmark parcels used '
     || 'to build and verify the enrichment engine. is_active = false so it '
     || 'cannot appear in client-facing queries. Delete with its parcels '
     || 'before any production launch.')
ON CONFLICT (slug) DO UPDATE
    SET notes = EXCLUDED.notes, is_active = false;

-- ---------------------------------------------------------------------------
-- 2. Expected-answer column. The whole point of this exercise.
-- ---------------------------------------------------------------------------
ALTER TABLE land.parcels
    ADD COLUMN IF NOT EXISTS test_expectation text;
COMMENT ON COLUMN land.parcels.test_expectation IS
    'SYNTHETIC TEST PARCELS ONLY - NULL on every real parcel. What six '
    'sessions of landmark verification say this parcel SHOULD read. Written '
    'before the enrichment engine existed, so the engine can be judged '
    'against it rather than against its own output (rule E4).';

-- ---------------------------------------------------------------------------
-- 3. The parcels.
--
--    Geometry is a rectangle around the landmark coordinate, sized by
--    ST_Buffer on geography so the metres are real metres rather than
--    degrees, then enveloped to a plausible rectangular plot.
--
--    COORDINATES ARE THE ONES ALREADY USED IN test/calibration scripts, so
--    the readings are comparable with the flood calibration landmark table.
-- ---------------------------------------------------------------------------
DELETE FROM land.parcels
WHERE company_id = (SELECT company_id FROM clients.companies
                    WHERE slug = 'geocode-test');

INSERT INTO land.parcels
    (company_id, parcel_ref, project_name, area_sqm, price_kes,
     listing_status, geom, confidence, test_expectation)
SELECT
    (SELECT company_id FROM clients.companies WHERE slug = 'geocode-test'),
    t.ref, t.project, NULL, t.price, 'available',
    ST_Multi(ST_Envelope(
        ST_Buffer(ST_SetSRID(ST_MakePoint(t.lon, t.lat), 4326)::geography,
                  t.half_m)::geometry
    ))::geometry(MultiPolygon, 4326),
    5,
    t.expectation
FROM (VALUES

-- ---- FLOOD: the four that must warn ---------------------------------------
 ('TEST-BUDALANGI-01', 'Flood validation', 34.150,  0.150, 160.0, 900000::numeric,
  'FLOOD: the hardest case in the database. Majority class reads Moderate '
  'and worst-nearby reads Permanent water. Budalangi floods almost every '
  'year BY DIKE FAILURE, which HAND structurally cannot see - the village '
  'genuinely sits several metres above the channel. EXPECT: flood_risk_class '
  'at least Moderate, dist_permanent_water_m SMALL. Rule D3 - the permanent '
  'water proximity is what carries the real warning here, not the hazard '
  'class. If dist_permanent_water_m comes back large, the engine is wrong.'),

 ('TEST-TANADELTA-01', 'Flood validation', 40.300, -2.500, 450.0, 2500000,
  'FLOOD: EXPECT Very high on worst-within-1km. Large parcel (~50 acres), so '
  'flood_risk_breakdown should show a MIX of classes, not one value. If the '
  'breakdown is a single class across 450 m, the footprint sampling is not '
  'working.'),

 ('TEST-GARISSA-01', 'Flood validation', 39.650, -0.450, 120.0, 1800000,
  'FLOOD: the landmark that has driven this layer since run 57 was withdrawn. '
  'Town sits on a terrace above an incised Tana. EXPECT worst-within-1km at '
  'Very high, but the parcel CELL likely Very low. Rule D2 exists for exactly '
  'this: flood_risk_class and flood_risk_class_cell SHOULD DISAGREE here. If '
  'they agree, the radius logic is not running.'),

 ('TEST-KANO-01', 'Flood validation', 34.950, -0.200, 200.0, 700000,
  'FLOOD: Kano plains. EXPECT High or Very high. Straightforward floodplain, '
  'no terrace complication - this is the control that should be easy.'),

-- ---- FLOOD: the ones that must NOT warn ------------------------------------
 ('TEST-KAREN-01', 'Flood validation', 36.700, -1.330, 45.0, 25000000,
  'FLOOD: EXPECT Very low. Nairobi Karen, high-value residential. A false '
  'flood warning here is the most commercially damaging error the platform '
  'can make - it would devalue prime land on a modelled number. Also expect '
  'high built_up_pct_1km and, from nightlights, an already-lit area.'),

 ('TEST-ABERDARES-01', 'Flood validation', 36.700, -0.450, 300.0, 400000,
  'FLOOD: EXPECT Very low. Steep slopes - water leaves, it does not collect. '
  'Cross-check: slope_mean_pct should be HIGH here. If slope is low, the '
  'coordinate is wrong, not the flood layer.'),

-- ---- DEVELOPMENT SIGNAL: the peri-urban land market ------------------------
 ('TEST-RUAI-01', 'Development signal', 37.020, -1.270, 30.0, 3500000,
  'NIGHTLIGHTS: Ruai ranked TOP of the absolute-radiance trend and 99.9th '
  'percentile in verify_26. EXPECT strongly positive nightlights_trend_'
  'radiance_yr. Rule D10 - the value is a SUM inherited from the ward, so '
  'nightlights_admin_unit MUST be populated or the number cannot be read.'),

 ('TEST-KITENGELA-01', 'Development signal', 36.850, -1.480, 30.0, 4000000,
  'NIGHTLIGHTS: second in the calibrated trend ranking. EXPECT positive '
  'trend. ALSO the black cotton cross-check - Kitengela sits on the Athi '
  'plains fringe.'),

-- ---- SOIL: the known miss -------------------------------------------------
 ('TEST-ATHIPLAINS-01', 'Soil validation', 36.980, -1.520, 100.0, 2000000,
  'BLACK COTTON: THE DOCUMENTED FAILURE CASE. SoilGrids maps the Athi-Kapiti '
  'plains as Luvisols, NOT Vertisols, on two separate probes - while iSDA '
  'texture reads Clay Loam. Rule D7 exists because of this exact spot. '
  'EXPECT black_cotton_risk = ''possible'' (one layer agrees, not both). If '
  'it returns ''none'', the engine is reading only SoilGrids and D7 is not '
  'implemented.'),

-- ---- LAND COVER / VEGETATION ----------------------------------------------
 ('TEST-KAKAMEGA-01', 'Land cover validation', 34.870,  0.350, 250.0, 600000,
  'LAND COVER: Kakamega Forest read 96%% Tree cover in verify_19. EXPECT '
  'landcover_class_worldcover = Tree cover and a HIGH ndvi_mean. '
  'landcover_composition should be dominated by one class - this is the '
  'cleanest composition test in the set.'),

-- ---- RAINFALL: the range test ---------------------------------------------
 ('TEST-KERICHO-01', 'Rainfall validation', 35.280, -0.370, 400.0, 800000,
  'RAINFALL: wet highland, ~1,900 mm. EXPECT high rainfall_normal_mm_yr. '
  'NOTE C5 - the layer RUNS WET by about +145 mm, so do not treat the '
  'absolute figure as calibrated. At 5 km CHIRPS resolution a 400 m parcel '
  'sits inside ONE cell, so rainfall_min and rainfall_max SHOULD EQUAL the '
  'mean. If they differ, the range logic is inventing a spread.'),

 ('TEST-LODWAR-01', 'Rainfall validation', 35.600,  3.120, 500.0, 150000,
  'RAINFALL: arid, ~200 mm. EXPECT low rainfall_normal_mm_yr and a driest-'
  'year percentage that shows real drought exposure. CONTRAST with Kericho: '
  'if these two do not separate strongly, the rainfall sampling is broken. '
  'ALSO a scope-rule note: this is low-transaction land and must never be '
  'allowed to drive calibration (session 7 scope decision).')

) AS t(ref, project, lon, lat, half_m, price, expectation);

COMMIT;

\echo ''
\echo '=== TEST PARCELS CREATED ====================================='

SELECT parcel_ref,
       round((ST_Area(geom::geography)/4046.86)::numeric, 2) AS acres,
       round((ST_Area(geom::geography))::numeric, 0) AS sqm,
       ST_GeometryType(geom) AS geom_type
FROM land.parcels
WHERE company_id = (SELECT company_id FROM clients.companies
                    WHERE slug = 'geocode-test')
ORDER BY parcel_ref;

\echo ''
\echo 'Sanity check - every parcel must fall inside Kenya:'

SELECT p.parcel_ref,
       CASE WHEN ST_Within(p.geom, c.geom) THEN 'inside Kenya'
            WHEN ST_Intersects(p.geom, c.geom) THEN 'ON THE BORDER - check'
            ELSE '*** OUTSIDE KENYA - FIX THE COORDINATE ***' END AS location
FROM land.parcels p, admin.country c
WHERE p.company_id = (SELECT company_id FROM clients.companies
                      WHERE slug = 'geocode-test')
ORDER BY p.parcel_ref;

\echo ''
\echo 'County assignment (should look right for each landmark):'

SELECT p.parcel_ref, co.name AS county
FROM land.parcels p
LEFT JOIN admin.counties co ON ST_Intersects(p.geom, co.geom)
WHERE p.company_id = (SELECT company_id FROM clients.companies
                      WHERE slug = 'geocode-test')
ORDER BY p.parcel_ref;

\echo ''
\echo 'NEXT: run the enrichment engine against these, then compare its output'
\echo 'against land.parcels.test_expectation. The expectations were written'
\echo 'BEFORE the engine existed - that is the point.'
\echo ''
