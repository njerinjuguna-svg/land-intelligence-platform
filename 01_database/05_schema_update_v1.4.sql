-- ============================================================================
-- SCHEMA UPDATE v1.4 - connectivity.coverage carries PERCENTAGES, not contours
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- WHY THIS CHANGE
--   connectivity.coverage was designed for signal PROPAGATION polygons: an
--   operator, a technology, and a signal_class of strong/fair/weak, with the
--   geometry being the contour itself. That is what a coverage map normally
--   looks like and it is what the catalogue assumed.
--
--   The Communications Authority of Kenya does not publish that. Its ICT
--   Services Coverage Geo-Portal publishes the 7,134 SUBLOCATION boundaries
--   with a coverage PERCENTAGE attached to each one, per technology:
--
--       ABAKAILE,  Garissa,  64.89% 4G
--       ABALATIRO, Garissa,  99.02% 4G
--       ABDI WAKO, Wajir,   100.00% 4G
--
--   That is a genuinely different statement. It answers "how much of the
--   sublocation containing this parcel has 4G", not "does this parcel have
--   4G". Bucketing a percentage into strong/fair/weak would throw away the
--   number and imply a signal strength that was never measured, so the
--   columns below record what the source actually says.
--
-- WHAT THIS MEANS FOR ENRICHMENT, and it must be honoured
--   A parcel inherits the coverage percentage of its sublocation. In a
--   sublocation at 64.89% the honest statement is "this area is about
--   two-thirds covered", NEVER "this parcel has 4G". Pair it with distance to
--   the nearest tower from connectivity.towers, which IS point-specific, and
--   present the two together.
--
-- Run once:  psql -d land_intelligence_kenya -f 05_schema_update_v1.4.sql
-- ============================================================================

BEGIN;

-- The share of the admin unit that the CA reports as covered. This is the
-- load-bearing number; signal_class stays for any future propagation source.
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS coverage_pct numeric
        CHECK (coverage_pct IS NULL OR (coverage_pct >= 0 AND coverage_pct <= 100));

-- WHICH admin unit the percentage refers to. Recorded explicitly because a
-- percentage is meaningless without knowing what it is a percentage OF, and
-- because the CA may publish at ward or constituency level in future.
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS admin_level text
        CHECK (admin_level IS NULL OR admin_level IN
               ('sublocation','location','ward','constituency','county'));
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS admin_name text;
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS admin_code text;

-- Ward linkage, so coverage can be joined to the 1,425 wards we already hold.
-- NOT a foreign key: admin.wards currently carries provisional LIP-W codes
-- (see PROGRESS.md), and a FK here would fail or, worse, silently constrain
-- us to whichever codes happen to match today.
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS ward_name text;
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS ward_code_src text;

-- WHICH CA SERVICE EACH ROW CAME FROM. Not decoration: the CA's layers were
-- published piecemeal between 2022 and 2023 and are not equally trustworthy.
-- The only 3G layer carrying a coverage percentage is literally named
-- "Airtel_Safaricom_Telkom_3G_2022test". A row sourced from a layer with
-- "test" in its name must stay identifiable after loading, so that a later
-- reader can weigh it, and so it can be swapped the moment the CA publishes
-- a production 3G layer.
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS source_layer text;
COMMENT ON COLUMN connectivity.coverage.source_layer IS
    'CA FeatureServer service name this row was loaded from. Check it before '
    'trusting a row: some CA layers are dated or marked test.';

-- The CA ships population and area per sublocation. Kept because population
-- coverage is the figure the regulator itself reports against, and because
-- area lets us recompute the percentage and check it rather than trust it.
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS population numeric;
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS area_sqkm numeric;
ALTER TABLE connectivity.coverage
    ADD COLUMN IF NOT EXISTS covered_area_sqkm numeric;

-- The CA publishes per-technology layers that COMBINE all three operators
-- ("airtel_safaricom_telkom_4G"). operator is NOT NULL on this table, so
-- those rows are loaded as 'all'. Per-operator layers keep their own name.
COMMENT ON COLUMN connectivity.coverage.operator IS
    'Safaricom / Airtel / Telkom, or ''all'' where the CA publishes the three combined';
COMMENT ON COLUMN connectivity.coverage.coverage_pct IS
    'Share of the admin unit reported as covered. NOT a point-level guarantee.';
COMMENT ON COLUMN connectivity.coverage.signal_class IS
    'Reserved for true propagation sources. NULL for CA admin-unit percentages.';

CREATE INDEX IF NOT EXISTS idx_coverage_tech_operator
    ON connectivity.coverage (technology, operator);
CREATE INDEX IF NOT EXISTS idx_coverage_admin_code
    ON connectivity.coverage (admin_code);

COMMIT;
