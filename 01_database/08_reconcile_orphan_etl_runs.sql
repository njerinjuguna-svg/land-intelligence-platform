-- ============================================================================
-- DATA FIX 08 - reconcile the 12 orphan etl_runs rows
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- ---------------------------------------------------------------------------
-- WHAT IS WRONG
--   metadata.etl_runs has 12 rows still at run_status = 'running', the oldest
--   from 14 July. None of them is actually running. The audit trail has been
--   silently disagreeing with PROGRESS.md for a month.
--
-- ---------------------------------------------------------------------------
-- ROOT CAUSE (confirmed in the code, not guessed)
--   Every ETL wraps its work in `except Exception as exc:` and writes
--   run_status = 'failed' from that handler. But the scripts' own guards use
--   `raise SystemExit(...)` -- 96 occurrences across 10 files -- and
--   SystemExit inherits from BaseException, NOT Exception. So it goes
--   straight past the handler and the row is never closed. KeyboardInterrupt
--   (Ctrl+C) does exactly the same thing.
--
--   The deliberate safety guards are precisely the paths that fail to record
--   their own failure.
--
--   Proof: run 52 is documented in PROGRESS.md as "RUN 52 FAILED AND THE
--   FAILURE WAS THE POINT". The empty-window guard at etl_22:262 fired as
--   designed. The row still reads 'running'.
--
--   FIXED FORWARD by 03_etl/patch_etl_failure_logging.py, which changes the
--   handler to `except BaseException`. Run that too, or this recurs.
--
-- ---------------------------------------------------------------------------
-- WHY EACH ROW GETS ITS OWN REASON
--   A blanket UPDATE ... SET run_status='failed' would make the audit trail
--   tidy and no more truthful than it is now. Each run below is closed with
--   what PROGRESS.md actually records about it. Runs 58 and 60 appear in NO
--   session note, so they are marked as undocumented rather than given an
--   invented cause -- an audit trail that guesses is worse than one that
--   admits a gap.
--
--   All are 'failed' rather than 'partial': none produced a catalogued
--   artefact that survived. Run 57 DID catalogue and was withdrawn, but it is
--   not in this list because it closed itself correctly.
--
-- ---------------------------------------------------------------------------
-- SAFE TO RUN TWICE. Every statement is guarded on run_status = 'running'
-- and on finished_at IS NULL, so a second run is a no-op.
--
-- How to run:
--   psql -U postgres -d land_intelligence_kenya -f 01_database/08_reconcile_orphan_etl_runs.sql
-- ============================================================================

\echo ''
\echo '=== BEFORE: rows stuck at running ============================'

SELECT run_id, pipeline, started_at::date AS started
FROM metadata.etl_runs
WHERE run_status = 'running'
ORDER BY run_id;

BEGIN;

-- --- run 1 : etl_01, predates failure logging entirely ----------------------
-- Session 1 recorded this as "manually closed as failed". It never was.
UPDATE metadata.etl_runs SET
    run_status = 'failed', finished_at = started_at,
    error_message = 'Predates failure logging. Session 1 recorded this run '
                 || 'as manually closed as failed; the UPDATE was never '
                 || 'applied. Superseded by run 6, which loaded 47 counties, '
                 || '290 subcounties and 1,425 wards successfully. '
                 || 'finished_at set to started_at: the true end time is not '
                 || 'recoverable and now() would assert a month-long run.'
WHERE run_id = 1 AND run_status = 'running' AND finished_at IS NULL;

-- --- runs 39, 42, 43, 44 : etl_17 iSDA soils --------------------------------
-- The streaming problem. Session 4 documents three separate faults: the
-- LOCAL_CS CRS that returned a 0x0 window, the PROJ_LIB hijack by
-- PostgreSQL's own copy, and truncated remote tile reads on a flaky link.
UPDATE metadata.etl_runs SET
    run_status = 'failed', finished_at = started_at,
    error_message = 'Failed during the iSDA streaming problem (sessions 4-5): '
                 || 'WarpedVRT reprojection across the network turned each '
                 || 'read into thousands of scattered range requests, causing '
                 || 'truncated tiles and stalls. Also hit the LOCAL_CS CRS '
                 || 'issue and the PROJ_LIB hijack. Resolved in session 5 by '
                 || 'separating FETCH from REPROJECT; soils.ph reingested '
                 || 'cleanly in runs 46 and 47. Closed retrospectively.'
WHERE run_id IN (39, 42, 43, 44)
  AND run_status = 'running' AND finished_at IS NULL;

-- --- run 52 : etl_22 SoilGrids ----------------------------------------------
-- The documented lesson-10 failure. The guard worked; the logging did not.
UPDATE metadata.etl_runs SET
    run_status = 'failed', finished_at = started_at,
    error_message = 'Empty Kenya window in the native grid (guard at '
                 || 'etl_22:262). Cause: the docstring asserted SoilGrids is '
                 || 'served in Interrupted Goode Homolosine and converted '
                 || 'Kenya bounds to metres; the endpoint actually reports '
                 || 'EPSG:4326, so metre coordinates near 1,500,000 fell '
                 || 'outside a raster whose axes run to 180. Succeeded as run '
                 || '53. NOTE: the guard raised SystemExit, which bypassed '
                 || 'the except Exception handler - this row is why the bug '
                 || 'was found. Closed retrospectively.'
WHERE run_id = 52 AND run_status = 'running' AND finished_at IS NULL;

-- --- runs 55, 56, 59, 61 : etl_24 flood, documented in the session 6 table --
UPDATE metadata.etl_runs SET
    run_status = 'failed', finished_at = started_at,
    error_message = 'Flood calibration attempt, documented in the PROGRESS.md '
                 || 'session 6 table. All classified on ABSOLUTE HAND, which '
                 || 'cannot distinguish two metres above the Tana from two '
                 || 'metres above a 5 km2 sand gully: run 55 Euclidean HAND '
                 || '40.8% Very high; 56 negatives clipped 39.2%; 59 flow '
                 || 'routing 29.2%; 61 plus fill exclusion 25.7%. Resolved in '
                 || 'run 62 by catchment-scaled hazard. Closed '
                 || 'retrospectively.'
WHERE run_id IN (55, 56, 59, 61)
  AND run_status = 'running' AND finished_at IS NULL;

-- --- runs 58, 60 : etl_24, NOT in any session note --------------------------
-- Do not invent a cause. They sit between documented attempts and are
-- almost certainly more of the same, but "almost certainly" is not provenance.
UPDATE metadata.etl_runs SET
    run_status = 'failed', finished_at = started_at,
    error_message = 'UNDOCUMENTED RUN. Sits between the flood attempts '
                 || 'recorded in the PROGRESS.md session 6 table (55, 56, 57, '
                 || '59, 61, 62) but appears in no session note, so the '
                 || 'specific cause is not recoverable. Closed as failed '
                 || 'because it produced no catalogued artefact. The reason '
                 || 'is deliberately NOT guessed.'
WHERE run_id IN (58, 60)
  AND run_status = 'running' AND finished_at IS NULL;

COMMIT;

\echo ''
\echo '=== AFTER ===================================================='
\echo 'Rows still at running (expect NONE, or only a job you started'
\echo 'yourself in the last few minutes):'

SELECT run_id, pipeline, started_at::date AS started
FROM metadata.etl_runs
WHERE run_status = 'running'
ORDER BY run_id;

\echo ''
\echo 'Full run-status tally:'

SELECT run_status, count(*) AS runs
FROM metadata.etl_runs
GROUP BY run_status
ORDER BY run_status;

\echo ''
\echo 'NOW RUN THE FORWARD FIX, or this recurs on the next interrupted run:'
\echo '  cd 03_etl'
\echo '  python patch_etl_failure_logging.py'
\echo ''
