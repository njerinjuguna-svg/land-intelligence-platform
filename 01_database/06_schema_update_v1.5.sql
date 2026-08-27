-- ============================================================================
-- SCHEMA UPDATE v1.5 - nightlights carries an ABSOLUTE development trend
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- WHY THIS CHANGE
--   demographics.nightlights_stats had one trend column, trend_pct_yr, and
--   the catalogue says the trend is the development signal. Calibration
--   showed a percentage rate cannot carry that signal:
--
--     median ward   33 %/yr  -> an 11x brightening over nine years
--     fastest ten   214-252 %/yr
--     and they were rural wards in Homa Bay, Migori, Kisii and Kakamega
--
--   Percentage growth from a near-zero base is unbounded, and 417 of 1,422
--   wards had a 2015 baseline under 1.0, with 335 at exactly zero. The
--   metric was measuring how dark a ward used to be.
--
--   Three candidates were compared on whether their top-ranked wards are
--   places where Kenyan land value actually moves:
--
--     A  log growth  %/yr        -> Tembelio, Dedan Kimathi, Kochia...
--                                   rural electrification, not land value
--     C  lit-area points/yr      -> all saturate at 100% lit and tie; worse,
--                                   it scores ZERO for Ruai, Karen, Gitothua
--                                   and Mihang'o, which were already fully
--                                   lit in 2015 and are exactly the market
--     B  absolute radiance/yr    -> Ruai, Kitengela, Mihang'o, Gatongora,
--                                   Murera, Kalimoni, Gitothua, Muthwani,
--                                   Kinanie, Kaputei North, Karen, and Hindi
--                                   on the LAPSSET corridor
--
--   B is the Nairobi peri-urban land market, which is the product's
--   audience. It also needs no baseline floor: absolute change is
--   well-defined at zero and cannot explode, so there is no threshold to
--   argue about.
--
--   Top-50 rank overlap between A and B was 0/50. They are not variants of
--   one measure; they answer different questions.
-- ============================================================================

BEGIN;

-- The development signal. Change in summed radiance per year, in
-- nW/cm2/sr summed over the unit's cells. Absolute, not a rate.
ALTER TABLE demographics.nightlights_stats
    ADD COLUMN IF NOT EXISTS trend_radiance_yr numeric;

COMMENT ON COLUMN demographics.nightlights_stats.trend_radiance_yr IS
    'Development signal: change in radiance_sum per year (absolute). '
    'Ranks intensification within already-lit areas, which is what '
    'peri-urban land development looks like. Use THIS for "is the area '
    'developing". Not comparable between units of different size: pair '
    'with area or use radiance_mean for like-for-like.';

COMMENT ON COLUMN demographics.nightlights_stats.trend_pct_yr IS
    'DELIBERATELY NULL as of v1.5. A percentage rate from a near-zero base '
    'is unbounded: it gave a median of 33%/yr and ranked rural '
    'electrification above peri-urban development. Revisit only as an '
    'explicit ELECTRIFICATION indicator with a baseline floor, never as the '
    'development signal.';

CREATE INDEX IF NOT EXISTS idx_nightlights_trend
    ON demographics.nightlights_stats (admin_level, trend_radiance_yr DESC);

COMMIT;
