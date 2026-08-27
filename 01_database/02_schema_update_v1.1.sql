-- ============================================================================
-- SCHEMA UPDATE v1.1 - sales status ladder, status audit, composition and
--                      range intelligence fields, marketplace opt-in
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- ---------------------------------------------------------------------------
-- *** THIS FILE WAS RECONSTRUCTED IN SESSION 7 (2026-08-14) ***
--
--   The original was OVERWRITTEN at some point with a three-line scratch
--   query (a SELECT counting roads by county and class - the one session 2
--   used to check road distribution). The migration itself was lost.
--
--   Nobody noticed, because the changes were already applied to the running
--   database and everything worked. The gap only appeared when session 7
--   found seven columns on analytics.parcel_intelligence that no file in this
--   folder creates.
--
--   THIS FILE IS RECONSTRUCTED FROM THE LIVE DATABASE, not from memory, using
--   a pg_dump --schema-only snapshot (01_database/_live_schema_snapshot.sql).
--   Every definition below was copied from what the database actually
--   contains. It is therefore accurate as a description; the ORIGINAL
--   COMMENTS AND REASONING ARE GONE, and what you see here has been rewritten
--   from the column names and the product context. Where the original author's
--   intent is inferred rather than known, it says so.
--
--   WHY THIS MATTERED: the plan is to move to managed Postgres before the
--   pilot client. That means running these files on a blank server. Before
--   this reconstruction, doing so would have produced a database missing
--   seven columns, six sales statuses, two columns on land.parcels, a
--   trigger, a function and an index - and the failure would have surfaced
--   later, on a client's data, with no obvious cause.
--
--   IDEMPOTENT. All of this is already applied to the live database; this
--   file exists so a REBUILD reproduces it. Running it again is a no-op.
--
-- Run once:  psql -U postgres -d land_intelligence_kenya -f 01_database/02_schema_update_v1.1.sql
-- ============================================================================

BEGIN;

-- ===========================================================================
-- 1. THE SALES STATUS LADDER
-- ===========================================================================
-- The base schema allowed four statuses: available, reserved, sold,
-- withdrawn. That is a listing toggle, not how Kenyan off-plan land actually
-- sells. The live ladder has TEN, and the additions each describe a real
-- state a plot sits in for weeks or months:
--
--   deposit_paid   - committed but not completed. Distinct from 'reserved',
--                    which is a hold; money has changed hands here.
--   coming_soon    - marketed before release. Drives the waiting list.
--   under_survey   - boundaries being surveyed; cannot be sold yet.
--   future_phase   - part of the scheme, not yet released.
--   off_market     - withdrawn from sale but still owned and tracked.
--   cancelled      - a sale that fell through. NOT the same as available:
--                    the history matters and the plot may carry a dispute.
--   hidden         - suppressed from client-facing views without changing
--                    the commercial state.
--
-- 'withdrawn' from the base schema does not appear in the live constraint;
-- 'off_market' replaced it.

ALTER TABLE land.parcels
    DROP CONSTRAINT IF EXISTS parcels_listing_status_check;

ALTER TABLE land.parcels
    ADD CONSTRAINT parcels_listing_status_check
    CHECK (listing_status = ANY (ARRAY[
        'available', 'reserved', 'deposit_paid', 'sold', 'off_market',
        'coming_soon', 'under_survey', 'future_phase', 'cancelled', 'hidden'
    ]));

COMMENT ON COLUMN land.parcels.listing_status IS
    'Commercial state of the plot. Ten states, not four: Kenyan off-plan land '
    'sits in deposit_paid, under_survey and future_phase for months at a '
    'time, and cancelled is NOT the same as available - the history matters. '
    'Changes are logged automatically to land.parcel_history by '
    'trg_log_listing_status.';

-- Completion facts, stamped when a plot sells.
ALTER TABLE land.parcels
    ADD COLUMN IF NOT EXISTS sold_date date;
ALTER TABLE land.parcels
    ADD COLUMN IF NOT EXISTS sold_price_kes numeric;

COMMENT ON COLUMN land.parcels.sold_date IS
    'Stamped AUTOMATICALLY by trg_log_listing_status the moment listing_status '
    'becomes sold, so it cannot be forgotten. Set it manually only to correct '
    'a historic record.';
COMMENT ON COLUMN land.parcels.sold_price_kes IS
    'What it ACTUALLY sold for, as opposed to price_kes, which is the asking '
    'price. The gap between the two is the most commercially interesting '
    'number in this table and the only honest basis for a future price model.';


-- ===========================================================================
-- 2. AUTOMATIC STATUS AUDIT
-- ===========================================================================
-- A status change is a commercial event and must not depend on anyone
-- remembering to log it. This writes to land.parcel_history on every change
-- and stamps sold_date on the way past.
--
-- BEFORE UPDATE, not AFTER, precisely so the sold_date assignment to NEW
-- takes effect in the same write.

CREATE OR REPLACE FUNCTION land.log_listing_status_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.listing_status IS DISTINCT FROM OLD.listing_status THEN
        INSERT INTO land.parcel_history (parcel_id, event, detail)
        VALUES (
            NEW.parcel_id,
            'status_change',
            jsonb_build_object(
                'from', OLD.listing_status,
                'to',   NEW.listing_status,
                'price_kes', NEW.price_kes
            )
        );
        -- stamp sold_date automatically the moment a parcel becomes sold
        IF NEW.listing_status = 'sold' AND NEW.sold_date IS NULL THEN
            NEW.sold_date := CURRENT_DATE;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_log_listing_status ON land.parcels;
CREATE TRIGGER trg_log_listing_status
    BEFORE UPDATE ON land.parcels
    FOR EACH ROW EXECUTE FUNCTION land.log_listing_status_change();

-- Partial index: the buyer-facing queries all filter to active rows.
CREATE INDEX IF NOT EXISTS parcels_listing_idx
    ON land.parcels USING btree (listing_status)
    WHERE (status = 'active');


-- ===========================================================================
-- 3. MARKETPLACE OPT-IN
-- ===========================================================================
ALTER TABLE clients.companies
    ADD COLUMN IF NOT EXISTS marketplace_opt_in boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN clients.companies.marketplace_opt_in IS
    'Client chose to display listings on a future Geocode marketplace.
     Opt-in only, set during onboarding. Leads always route to the client.';


-- ===========================================================================
-- 4. COMPOSITION AND RANGE INTELLIGENCE
-- ===========================================================================
-- THE IDEA BEHIND THESE SEVEN COLUMNS, and it is a good one:
--
--   A parcel is not a point. A 50-acre plot spans many raster cells, and a
--   single value under it is a summary that can hide the thing the buyer
--   most needs to know. "Elevation 1,840 m" says nothing about a plot that
--   runs from 1,780 m to 1,910 m across a ravine.
--
--   So each of these pairs with an existing single-value column:
--     the single value  = the DOMINANT class or the MEAN, for fast queries
--                         and for scoring
--     composition/range = the full distribution, for the report
--
--   This matters most for flood. Rule D2 says report the WORST class within
--   about a kilometre rather than the parcel's own cell, because Garissa
--   town reads Very low on its own pixel with Very high a few hundred metres
--   away. flood_risk_breakdown is what lets a report say "62% of this plot is
--   Very low, but 9% is High" instead of picking one word.

ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS soil_composition      jsonb;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS landcover_composition jsonb;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS flood_risk_breakdown  jsonb;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS rainfall_min_mm_yr    numeric;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS rainfall_max_mm_yr    numeric;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS elevation_min_m       numeric;
ALTER TABLE analytics.parcel_intelligence
    ADD COLUMN IF NOT EXISTS elevation_max_m       numeric;

-- This comment is the ONLY one that survived on the original seven. Kept
-- verbatim, including its indentation, because it is the single piece of the
-- original author's reasoning that was not lost.
COMMENT ON COLUMN analytics.parcel_intelligence.soil_composition IS
    'Per-class percentage cover under the parcel footprint. Single-value
     columns (soil_type etc.) hold the dominant class for fast queries;
     composition holds the full breakdown for reports.';

-- The remaining six carried no comment. These were written in session 7 from
-- the column names and the product rules, NOT from the original intent.
COMMENT ON COLUMN analytics.parcel_intelligence.landcover_composition IS
    'RECONSTRUCTED COMMENT (session 7; original lost). Per-class percentage '
    'cover under the parcel footprint, pairing with '
    'landcover_class_worldcover which holds the dominant class. '
    'Load-bearing for rule D6: a plot that is 55% shrubland and 40% cropland '
    'must never be summarised as "not farmland" on the dominant class alone.';

COMMENT ON COLUMN analytics.parcel_intelligence.flood_risk_breakdown IS
    'RECONSTRUCTED COMMENT (session 7; original lost). Per-class percentage of '
    'the parcel footprint in each flood class. THIS IS WHAT MAKES RULE D2 '
    'REPORTABLE: flood_risk_class carries the worst class within the search '
    'radius, and this shows how much of the plot is actually affected. '
    '"9% of this parcel is High" is a statement a buyer can act on; a single '
    'word is not. Must be able to represent all six classes including '
    'permanent_water.';

COMMENT ON COLUMN analytics.parcel_intelligence.rainfall_min_mm_yr IS
    'RECONSTRUCTED COMMENT (session 7; original lost). Minimum annual rainfall '
    'across the parcel footprint, pairing with rainfall_normal_mm_yr (the '
    'mean). At CHIRPS''s 5 km resolution most parcels sit inside one cell, so '
    'min and max will usually equal the mean - they only separate on large '
    'holdings or across a rainfall gradient. Do not present a spread that is '
    'really one cell read three times.';

COMMENT ON COLUMN analytics.parcel_intelligence.rainfall_max_mm_yr IS
    'RECONSTRUCTED COMMENT (session 7; original lost). Maximum annual rainfall '
    'across the parcel footprint. See rainfall_min_mm_yr on the 5 km '
    'resolution caveat.';

COMMENT ON COLUMN analytics.parcel_intelligence.elevation_min_m IS
    'RECONSTRUCTED COMMENT (session 7; original lost). Lowest point on the '
    'parcel, pairing with elevation_mean_m. THE RANGE IS THE BUILDABILITY '
    'SIGNAL: a plot spanning 130 m of relief is a different proposition from '
    'a flat one at the same mean, and the mean alone conceals it entirely. '
    'Reads from a 30 m DSM that includes canopy and buildings, not bare '
    'earth, so a wooded plot''s range is slightly overstated.';

COMMENT ON COLUMN analytics.parcel_intelligence.elevation_max_m IS
    'RECONSTRUCTED COMMENT (session 7; original lost). Highest point on the '
    'parcel. Pair with slope_max_pct: high relief AND high maximum slope is '
    'retaining walls, access problems and erosion, which is real money.';

COMMIT;

\echo ''
\echo '=== v1.1 RECONSTRUCTED AND VERIFIED =========================='
\echo 'Sales statuses (expect TEN):'

SELECT unnest(regexp_matches(pg_get_constraintdef(con.oid),
                             '''([a-z_]+)''', 'g')) AS listing_status
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
WHERE ns.nspname = 'land' AND rel.relname = 'parcels'
  AND con.conname = 'parcels_listing_status_check';

\echo ''
\echo 'Status audit trigger (expect trg_log_listing_status):'

SELECT tgname AS trigger_name
FROM pg_trigger
WHERE tgrelid = 'land.parcels'::regclass AND NOT tgisinternal
ORDER BY tgname;

\echo ''
\echo 'The seven composition/range columns, and their comments:'

SELECT column_name,
       CASE WHEN col_description('analytics.parcel_intelligence'::regclass::oid,
                                 ordinal_position) IS NULL
            THEN 'NO COMMENT' ELSE 'documented' END AS doc
FROM information_schema.columns
WHERE table_schema = 'analytics' AND table_name = 'parcel_intelligence'
  AND column_name IN ('soil_composition','landcover_composition',
                      'flood_risk_breakdown','rainfall_min_mm_yr',
                      'rainfall_max_mm_yr','elevation_min_m','elevation_max_m')
ORDER BY column_name;

\echo ''
\echo 'THE HABIT THAT STOPS THIS RECURRING - run after any schema change:'
\echo '  pg_dump -U postgres -d land_intelligence_kenya --schema-only'
\echo '    --no-owner --no-privileges -f 01_database/_live_schema_snapshot.sql'
\echo 'then diff the snapshot against the last one. Ten seconds, and it is'
\echo 'the only thing that would have caught this.'
\echo ''
