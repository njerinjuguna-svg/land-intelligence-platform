-- ===========================================================================
-- THE WIDGET'S DATABASE USER - AND A PROOF THAT IT IS CONFINED
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- WHY THIS EXISTS, AND WHY NOW
--   api_01_embed.py reads 03_etl/.env and connects as `postgres` - the same
--   superuser the ETL runs as, which can rewrite every parcel in the country.
--   On a laptop behind no network that has been harmless.
--
--   Stage 0 ends that. A Cloudflare Tunnel makes the API reachable from the
--   public internet, with deliberately permissive CORS, holding a key that is
--   public by nature because it sits in a client's page source. A superuser
--   connection behind that is the whole database one bug away from a stranger.
--
--   So this runs BEFORE the first `cloudflared tunnel run`. Not after.
--
-- WHAT THE WIDGET ACTUALLY NEEDS
--   Six tables to read, two to write. That is the entire surface, and it is
--   worth noticing how small it is: the reference layers, the rasters, the
--   staging schema and every ETL output are invisible to it, because the
--   widget serves values that were computed hours ago on the workbench.
--
-- WHY IT IS NOT NUMBERED
--   The numbered files in this folder are the schema, and rebuild_check.ps1
--   replays them into a scratch database to prove they reproduce the live one.
--   Roles are CLUSTER-WIDE, not per-database: replaying a CREATE ROLE would
--   reach outside the scratch database it is supposed to be confined to. This
--   file is deliberately outside that sequence and outside that list.
--
-- RUN:
--   psql -U postgres -d land_intelligence_kenya -f grants_landiq_api.sql
--
--   It prompts for the password with psql's \password, which does NOT echo,
--   never writes the password into shell history, and sends an already-hashed
--   ALTER ROLE so the plaintext does not reach the server log either.
--
--   The first version of this file used \prompt, which echoes. That put a
--   password on screen and into terminal scrollback. If you ran that version,
--   the password it set is compromised - change it with \password.
--
--   Generate something long and random. The widget is the only thing that
--   ever types it, so it never has to be memorable, and it is reachable from
--   the public internet the moment the tunnel starts.
-- ===========================================================================

BEGIN;

-- Idempotent. Running this twice must not fail, because it will be run twice
-- the first time somebody mistypes the password.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'landiq_api') THEN
        CREATE ROLE landiq_api LOGIN;
        RAISE NOTICE 'created role landiq_api';
    ELSE
        RAISE NOTICE 'role landiq_api already exists - updating its grants';
    END IF;
END $$;

-- No database creation, no role creation, no replication, no bypassing RLS.
ALTER ROLE landiq_api NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

COMMIT;

-- Set the password OUTSIDE the transaction, with the meta-command built for
-- it. \password prompts without echoing and hashes client-side, so the
-- plaintext never appears on screen, in shell history, or in the server log.
\password landiq_api

BEGIN;

-- START FROM NOTHING. If this file is re-run after someone widened a grant by
-- hand, the widening must not survive. Additive-only grants would mean this
-- file describes a floor rather than the actual privileges.
REVOKE ALL ON ALL TABLES IN SCHEMA land, analytics, clients, logs FROM landiq_api;
REVOKE ALL ON SCHEMA land, analytics, clients, logs FROM landiq_api;

GRANT USAGE ON SCHEMA land, analytics, clients, logs TO landiq_api;

-- READ. Exactly the tables api_01_embed.py queries, named one by one. Never
-- `ALL TABLES IN SCHEMA` - that grant silently includes every table added in
-- future, which is how a confined user stops being confined without anyone
-- deciding to widen it.
GRANT SELECT ON
    land.parcels,
    analytics.parcel_intelligence,
    analytics.suitability_scores,
    clients.api_keys,
    clients.companies,
    clients.branding
TO landiq_api;

-- WRITE. Its own footprints, and nothing else.
GRANT INSERT ON logs.api_logs TO landiq_api;
GRANT INSERT, UPDATE ON clients.api_usage TO landiq_api;

-- Identity and serial columns draw from sequences; an INSERT without USAGE on
-- them fails at runtime rather than here. Sequences carry no information
-- worth protecting, so this is safe to grant broadly within these two schemas.
GRANT USAGE ON ALL SEQUENCES IN SCHEMA clients, logs TO landiq_api;

COMMIT;


-- ===========================================================================
-- THE PROOF
--
-- A GRANT statement is a claim about what was intended. What follows tests
-- what is TRUE, by becoming the user and trying things that must fail. A
-- least-privilege user nobody has attacked is a least-privilege user in
-- principle only.
--
-- Each check raises an exception if the wrong thing happens, so a broken
-- confinement stops this script instead of printing quietly among the NOTICEs.
-- ===========================================================================

DO $$
DECLARE
    n integer;
BEGIN
    SET LOCAL ROLE landiq_api;

    -- 1. It must be able to do its job.
    SELECT count(*) INTO n FROM land.parcels WHERE status = 'active';
    RAISE NOTICE 'OK   can SELECT land.parcels (% active)', n;

    SELECT count(*) INTO n FROM analytics.parcel_intelligence WHERE status = 'active';
    RAISE NOTICE 'OK   can SELECT parcel_intelligence (% active)', n;

    -- 2. It must NOT be able to change a parcel. This is the one that matters:
    --    a compromised widget rewriting listing_status or geometry would be
    --    changing what a buyer is told about land that is for sale.
    BEGIN
        UPDATE land.parcels SET listing_status = listing_status WHERE false;
        RAISE EXCEPTION 'CONTROL FAILED: landiq_api can UPDATE land.parcels';
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK   cannot UPDATE land.parcels';
    END;

    -- 3. It must not be able to rewrite the analysis it serves.
    BEGIN
        UPDATE analytics.parcel_intelligence SET status = status WHERE false;
        RAISE EXCEPTION 'CONTROL FAILED: landiq_api can UPDATE parcel_intelligence';
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK   cannot UPDATE parcel_intelligence';
    END;

    -- 4. It must not be able to delete a client's parcels.
    BEGIN
        DELETE FROM land.parcels WHERE false;
        RAISE EXCEPTION 'CONTROL FAILED: landiq_api can DELETE from land.parcels';
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK   cannot DELETE from land.parcels';
    END;

    -- 5. It must not be able to see the workbench. staging holds the raw
    --    imports; nothing the widget does has any business there.
    BEGIN
        SELECT count(*) INTO n FROM staging.roads_raw;
        RAISE EXCEPTION 'CONTROL FAILED: landiq_api can read staging.roads_raw';
    EXCEPTION
        WHEN insufficient_privilege THEN
            RAISE NOTICE 'OK   cannot read the staging schema';
        WHEN undefined_table THEN
            RAISE NOTICE 'OK   cannot even see staging.roads_raw';
    END;

    RESET ROLE;
    RAISE NOTICE '---';
    RAISE NOTICE 'All confinement checks passed.';
END $$;


-- What the user can actually touch, read back from the catalogue rather than
-- assumed from the statements above. Read it. It should be six SELECTs, one
-- INSERT, and one INSERT+UPDATE - nothing else, in any schema.
SELECT table_schema, table_name,
       string_agg(privilege_type, ', ' ORDER BY privilege_type) AS granted
  FROM information_schema.table_privileges
 WHERE grantee = 'landiq_api'
 GROUP BY table_schema, table_name
 ORDER BY table_schema, table_name;
