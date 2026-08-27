-- ============================================================================
-- DATA FIX 07 - quarantine landcover_change, close the orphan etl_29 run
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- This is NOT a schema change. Nothing here alters a table definition; it
-- corrects two rows that etl_29 left in a state the catalogue should not be
-- serving.
--
-- ---------------------------------------------------------------------------
-- 1. WHY landcover_change IS BEING QUARANTINED
--
--   etl_29 catalogues a change layer on success at confidence 3, so it is
--   LIVE in metadata.raster_catalog right now and the enrichment engine could
--   pick it up. It must not.
--
--   Impact Observatory reports, over 2017 to 2024:
--       tree cover     13.58%  ->  25.58%     nearly doubled in seven years
--       changed class           23.05%
--       IO built area   1.72%  ->   2.59%     vs WorldCover's 0.32%
--
--   Kenya's tree cover did not nearly double in seven years. IO built area at
--   5-8x WorldCover is far outside the GHSL-vs-WorldCover gap (0.52 vs 0.32)
--   that session 5 established as the expected disagreement between two
--   producers measuring different things.
--
--   Cause: classifier drift between IO model versions. IO retrains and
--   republishes the full back series, so a boundary that moves in the model
--   moves in every year at once. Differencing two epochs measures the model
--   revision, not the landscape.
--
--   The YEARLY SNAPSHOTS are unaffected and stay active. They are internally
--   consistent within a year and they deliver the recency ESA WorldCover
--   cannot (ESA published nothing after 2021 v200). What is lost is the
--   comparison BETWEEN years - which was the main reason the dataset was
--   chosen. That is recorded in PROGRESS.md, lesson 29.
--
--   pending_review, NOT rejected or deleted. The row is kept so the reasoning
--   stays traceable, consistent with the project's supersede-never-delete
--   discipline. If you decide the layer is unrecoverable rather than
--   unverified, change 'pending_review' to 'rejected' below - both are
--   permitted by the CHECK constraint.
--
-- ---------------------------------------------------------------------------
-- 2. VERIFIED AGAINST THE SCHEMA BEFORE WRITING (rule E2)
--
--   metadata.raster_catalog.status  CHECK IN ('active','superseded',
--                                             'pending_review','rejected')
--   metadata.etl_runs.run_status    CHECK IN ('running','success','failed',
--                                             'partial')
--   metadata.raster_catalog has NO notes column, so the reason is prepended
--   to name, which is the field the ETLs already use as the description and
--   the field a human reading the catalogue will actually see.
--
--   Both tables carry an updated_at trigger, so updated_at maintains itself.
--
-- ---------------------------------------------------------------------------
-- 3. SAFE TO RUN TWICE. Every statement is guarded so a second run is a
--    no-op rather than a double-edit.
--
-- How to run:
--   psql -d land_intelligence_kenya -f 01_database/07_data_fix_landcover_change.sql
-- ============================================================================

\echo ''
\echo '=== BEFORE ==================================================='

SELECT raster_id, variable, status, confidence,
       left(name, 60) AS name_starts
FROM metadata.raster_catalog
WHERE dataset_id = (SELECT dataset_id FROM metadata.datasets
                    WHERE code = 'satellite.landcover')
ORDER BY variable;

SELECT run_id, pipeline, run_status, started_at, finished_at
FROM metadata.etl_runs
WHERE run_status = 'running'
ORDER BY run_id;

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Quarantine the change layer.
-- ---------------------------------------------------------------------------
UPDATE metadata.raster_catalog
SET status = 'pending_review'
WHERE variable = 'landcover_change'
  AND status <> 'pending_review';

-- Put the reason where a reader will hit it first. Guarded on the marker so
-- rerunning does not stack the prefix.
UPDATE metadata.raster_catalog
SET name = 'PENDING REVIEW - DO NOT USE. Impact Observatory is not '
        || 'temporally consistent: it reports Kenyan tree cover rising '
        || '13.58% to 25.58% over 2017-2024 and built area 5-8x ESA '
        || 'WorldCover. This is classifier drift between IO model versions '
        || '(IO retrains and republishes the whole back series), not ground '
        || 'change. Differencing two epochs measures the model revision. '
        || 'Yearly snapshots are unaffected and remain active. See '
        || 'PROGRESS.md lesson 29. || ' || name
WHERE variable = 'landcover_change'
  AND name NOT LIKE 'PENDING REVIEW%';

-- ---------------------------------------------------------------------------
-- 2. Close the orphan run row.
--
--    A Ctrl+C during etl_29 left a row at 'running'. Recorded as 'failed',
--    not 'success': it did not finish, and an audit trail that rounds an
--    interruption up to a success is worse than no audit trail.
--
--    GUARDED three ways so this cannot close a job that is genuinely running:
--    the pipeline name must match, the row must have no finished_at, and it
--    must have started more than a day ago.
-- ---------------------------------------------------------------------------
UPDATE metadata.etl_runs
SET run_status    = 'failed',
    finished_at   = now(),
    error_message = 'Interrupted (Ctrl+C) during the session 6 run. Closed '
                 || 'manually by 07_data_fix_landcover_change.sql. No '
                 || 'partial data was left behind: etl_29 catalogues only '
                 || 'inside its final transaction.'
WHERE pipeline    = 'etl_29_io_landcover'
  AND run_status  = 'running'
  AND finished_at IS NULL
  AND started_at  < now() - interval '1 day';

COMMIT;

\echo ''
\echo '=== AFTER ===================================================='

SELECT raster_id, variable, status, confidence,
       left(name, 60) AS name_starts
FROM metadata.raster_catalog
WHERE dataset_id = (SELECT dataset_id FROM metadata.datasets
                    WHERE code = 'satellite.landcover')
ORDER BY variable;

-- Expect: landcover_change = pending_review, every landcover_io_<year> still
-- active. If a yearly snapshot flipped, something matched too broadly - roll
-- back and check the WHERE clauses.

SELECT run_id, pipeline, run_status, finished_at
FROM metadata.etl_runs
WHERE pipeline = 'etl_29_io_landcover'
ORDER BY run_id;

\echo ''
\echo 'Any row still at run_status = running (should be none, or only a job'
\echo 'you started yourself in the last 24 hours):'

SELECT run_id, pipeline, started_at
FROM metadata.etl_runs
WHERE run_status = 'running'
ORDER BY run_id;

\echo ''
\echo 'BOTH ITEMS THIS SCRIPT ORIGINALLY FLAGGED ARE NOW CLOSED (session 7):'
\echo '  - etl_29 country clip: ADDED and re-run as run 82. Kenya-clipped'
\echo '    figures are in PROGRESS.md lesson 29a.'
\echo '  - sources.csv: Impact Observatory and Digital Earth Africa rows'
\echo '    added, VIIRS Nightlights row corrected to note it is superseded'
\echo '    by NASA Black Marble.'
\echo ''
\echo 'THIS SCRIPT IS NOW A BACKSTOP, NOT THE CONTROL. etl_29 writes the'
\echo 'change layer at pending_review directly, so a successful run no'
\echo 'longer resurrects it. Run this only to verify, or on a database'
\echo 'catalogued before that fix.'
\echo ''
