-- ===========================================================================
-- SCHEMA UPDATE v1.11 - THE TWO COLUMNS THAT EXISTED ONLY ON THE LAPTOP
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- WHY THIS EXISTS
--   Rule E10 records that the numbered files were once found SHORT of the
--   live database, without saying by how much. Nobody had measured it.
--   rebuild_check.ps1 now replays every file in this folder into an empty
--   database and compares catalogues against the live one, and the answer is:
--
--       land.parcels.listed_date
--       land.parcels.test_expectation
--
--   Two columns. Everything else in the diff was either the `staging` schema
--   (ETL landing tables, which no serving machine needs) or PostGIS raster
--   views created in error by the check script itself. Constraints came back
--   393 to 393, identical. The files were far closer to the truth than the
--   rule's history suggested - but a serving machine built from them would
--   have failed, because land.parcels is a table the widget reads on every
--   page load.
--
--   Both columns were added to the laptop by hand and written into no
--   migration. This is that migration.
--
-- ON test_expectation
--   This is a TEST FIXTURE COLUMN IN A PRODUCTION TABLE, and that is worth
--   stating rather than quietly canonising. It holds the prose expectation a
--   landmark parcel was created to satisfy - written before the enrichment
--   engine existed - and verify_01_enrichment.py depends on it.
--
--   It stays a column on land.parcels rather than moving to a test-only
--   table, because the alternative is two different shapes for land.parcels
--   depending on which machine you are on, and that is a worse problem than
--   an unused nullable column. ON A SERVING MACHINE IT IS NULL ON EVERY ROW,
--   BY DESIGN. Nothing buyer-facing reads it and nothing should start.
--
-- ON listed_date
--   Added by hand, in no migration, and READ BY NO CODE I could find in
--   05_enrichment or 06_delivery. It is reproduced here because it exists on
--   the live database and the point of this folder is to reproduce the live
--   database - not because its purpose is established.
--
--   IT NEEDS A DECISION, and it is not this file's to make. Either it is the
--   "listed on" date the availability panel will want at go-live (D24 already
--   ties that panel to the client maintaining listing_status, and a date
--   beside the status is the obvious next thing a seller asks for), or it is
--   dead and should be dropped deliberately. Adding it is the reversible
--   choice; dropping a column on a table carrying client data is not, and
--   `supersede, never delete` is this build's rule everywhere else.
--
-- Run from 01_database with psql:
--   psql -U postgres -d land_intelligence_kenya -f 14_schema_update_v1.11.sql
--
-- Then re-run the check, which should come back with zero deploy blockers:
--   powershell -ExecutionPolicy Bypass -File .\rebuild_check.ps1
-- ===========================================================================

BEGIN;

ALTER TABLE land.parcels
    ADD COLUMN IF NOT EXISTS listed_date      date,
    ADD COLUMN IF NOT EXISTS test_expectation text;

COMMENT ON COLUMN land.parcels.listed_date IS
  'Date the parcel was listed for sale by the client. Nullable. Present on '
  'the live database since before v1.11 and reproduced here so the numbered '
  'files can rebuild it. NOT CURRENTLY READ BY ANY CODE - if the availability '
  'panel (D24) is to show a listing date, this is the column; if not, it '
  'should be dropped deliberately rather than left ambiguous.';

COMMENT ON COLUMN land.parcels.test_expectation IS
  'TEST FIXTURE, NOT PRODUCT DATA. The prose expectation a landmark test '
  'parcel was created to satisfy, written before the enrichment engine '
  'existed; verify_01_enrichment.py reads it. NULL on every row of a serving '
  'machine by design. Never render it, never let a client file populate it.';

COMMIT;

-- What this file deliberately does NOT do -------------------------------
--
-- It does not create the `staging` schema. Nothing in 01_database does, and
-- that is correct for a server: staging holds ogr2ogr landing tables and a
-- serving machine never runs an ETL.
--
-- But it means THIS FOLDER CANNOT REBUILD THE WORKBENCH EITHER. If the
-- laptop is lost, these files restore the schema and none of the twelve
-- sessions of loaded data - 14,221 landmark rows, the coverage polygons, the
-- OSM extracts, the raster corpus. That is a BACKUP problem, not a deploy
-- problem, and it is the more urgent of the two. It is not solved here and
-- must not be mistaken for solved because this file made the diff go green.
