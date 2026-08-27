--
-- PostgreSQL database dump
--

\restrict hZLeWWduxsfeU5x6tTPuVItxaJJMlfYNNfiHb0tAXraGz0KNLmgcUwykQzpSlB8

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: admin; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA admin;


--
-- Name: analytics; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA analytics;


--
-- Name: clients; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA clients;


--
-- Name: climate; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA climate;


--
-- Name: connectivity; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA connectivity;


--
-- Name: demographics; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA demographics;


--
-- Name: environment; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA environment;


--
-- Name: imagery; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA imagery;


--
-- Name: land; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA land;


--
-- Name: logs; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA logs;


--
-- Name: metadata; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA metadata;


--
-- Name: reports; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA reports;


--
-- Name: social; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA social;


--
-- Name: soils; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA soils;


--
-- Name: staging; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA staging;


--
-- Name: terrain; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA terrain;


--
-- Name: transport; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA transport;


--
-- Name: users; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA users;


--
-- Name: utilities; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA utilities;


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: postgis; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;


--
-- Name: EXTENSION postgis; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION postgis IS 'PostGIS geometry and geography spatial types and functions';


--
-- Name: log_listing_status_change(); Type: FUNCTION; Schema: land; Owner: -
--

CREATE FUNCTION land.log_listing_status_change() RETURNS trigger
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


--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: constituencies; Type: TABLE; Schema: admin; Owner: -
--

CREATE TABLE admin.constituencies (
    id bigint NOT NULL,
    constituency_code text,
    name text NOT NULL,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT constituencies_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT constituencies_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: constituencies_id_seq; Type: SEQUENCE; Schema: admin; Owner: -
--

ALTER TABLE admin.constituencies ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME admin.constituencies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: counties; Type: TABLE; Schema: admin; Owner: -
--

CREATE TABLE admin.counties (
    id bigint NOT NULL,
    county_code text NOT NULL,
    name text NOT NULL,
    is_pilot boolean DEFAULT false NOT NULL,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT counties_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT counties_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: counties_id_seq; Type: SEQUENCE; Schema: admin; Owner: -
--

ALTER TABLE admin.counties ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME admin.counties_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: country; Type: TABLE; Schema: admin; Owner: -
--

CREATE TABLE admin.country (
    id bigint NOT NULL,
    iso3 text DEFAULT 'KEN'::text NOT NULL,
    name text DEFAULT 'Kenya'::text NOT NULL,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT country_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT country_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: country_id_seq; Type: SEQUENCE; Schema: admin; Owner: -
--

ALTER TABLE admin.country ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME admin.country_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: locations; Type: TABLE; Schema: admin; Owner: -
--

CREATE TABLE admin.locations (
    id bigint NOT NULL,
    name text NOT NULL,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT locations_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT locations_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: locations_id_seq; Type: SEQUENCE; Schema: admin; Owner: -
--

ALTER TABLE admin.locations ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME admin.locations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: subcounties; Type: TABLE; Schema: admin; Owner: -
--

CREATE TABLE admin.subcounties (
    id bigint NOT NULL,
    subcounty_code text,
    name text NOT NULL,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT subcounties_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT subcounties_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: subcounties_id_seq; Type: SEQUENCE; Schema: admin; Owner: -
--

ALTER TABLE admin.subcounties ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME admin.subcounties_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: sublocations; Type: TABLE; Schema: admin; Owner: -
--

CREATE TABLE admin.sublocations (
    id bigint NOT NULL,
    name text NOT NULL,
    location_id bigint,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT sublocations_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT sublocations_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: sublocations_id_seq; Type: SEQUENCE; Schema: admin; Owner: -
--

ALTER TABLE admin.sublocations ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME admin.sublocations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: wards; Type: TABLE; Schema: admin; Owner: -
--

CREATE TABLE admin.wards (
    id bigint NOT NULL,
    ward_code text,
    name text NOT NULL,
    constituency_code text,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT wards_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT wards_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: wards_id_seq; Type: SEQUENCE; Schema: admin; Owner: -
--

ALTER TABLE admin.wards ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME admin.wards_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: accessibility; Type: TABLE; Schema: analytics; Owner: -
--

CREATE TABLE analytics.accessibility (
    id bigint NOT NULL,
    parcel_id uuid NOT NULL,
    destination_type text NOT NULL,
    destination_name text,
    distance_km numeric,
    travel_time_min numeric,
    mode text DEFAULT 'driving'::text NOT NULL,
    computed_at timestamp with time zone DEFAULT now() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT accessibility_mode_check CHECK ((mode = ANY (ARRAY['driving'::text, 'walking'::text, 'matatu'::text]))),
    CONSTRAINT accessibility_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: accessibility_id_seq; Type: SEQUENCE; Schema: analytics; Owner: -
--

ALTER TABLE analytics.accessibility ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME analytics.accessibility_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: enrichment_runs; Type: TABLE; Schema: analytics; Owner: -
--

CREATE TABLE analytics.enrichment_runs (
    run_id uuid DEFAULT gen_random_uuid() NOT NULL,
    company_id uuid,
    engine_version text NOT NULL,
    parcels_processed integer,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    run_status text DEFAULT 'running'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT enrichment_runs_run_status_check CHECK ((run_status = ANY (ARRAY['running'::text, 'success'::text, 'failed'::text, 'partial'::text])))
);


--
-- Name: parcel_intelligence; Type: TABLE; Schema: analytics; Owner: -
--

CREATE TABLE analytics.parcel_intelligence (
    intel_id bigint NOT NULL,
    parcel_id uuid NOT NULL,
    run_id uuid,
    dist_paved_road_m numeric,
    dist_any_road_m numeric,
    dist_bus_stop_m numeric,
    dist_town_centre_m numeric,
    travel_time_town_min numeric,
    dist_primary_school_m numeric,
    dist_secondary_school_m numeric,
    dist_hospital_m numeric,
    dist_clinic_m numeric,
    dist_market_m numeric,
    dist_police_m numeric,
    dist_power_line_m numeric,
    dist_transformer_m numeric,
    dist_water_point_m numeric,
    dist_water_line_m numeric,
    dist_sewer_m numeric,
    dist_river_m numeric,
    in_riparian_buffer boolean,
    in_protected_area boolean,
    dist_protected_area_m numeric,
    in_wetland boolean,
    flood_risk_class text,
    landslide_risk_class text,
    elevation_mean_m numeric,
    slope_mean_pct numeric,
    slope_max_pct numeric,
    aspect_dominant text,
    twi_mean numeric,
    soil_type text,
    soil_ph numeric,
    soil_texture text,
    soil_drainage text,
    soil_depth_class text,
    soil_fertility text,
    rainfall_normal_mm_yr numeric,
    temp_mean_c numeric,
    solar_kwh_m2_day numeric,
    landcover_class_worldcover text,
    ndvi_mean numeric,
    built_up_pct_1km numeric,
    pop_density_km2 numeric,
    nightlights_trend_radiance_yr numeric,
    dist_fiber_m numeric,
    zoning_class text,
    computed_at timestamp with time zone DEFAULT now() NOT NULL,
    engine_version text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    soil_composition jsonb,
    landcover_composition jsonb,
    flood_risk_breakdown jsonb,
    rainfall_min_mm_yr numeric,
    rainfall_max_mm_yr numeric,
    elevation_min_m numeric,
    elevation_max_m numeric,
    flood_risk_class_cell text,
    flood_search_radius_m numeric DEFAULT 1000,
    dist_permanent_water_m numeric,
    flood_forcing_max5day_mm numeric,
    coverage_2g_pct numeric,
    coverage_4g_pct numeric,
    coverage_4g_pct_safaricom numeric,
    coverage_4g_pct_telkom numeric,
    coverage_admin_level text,
    coverage_admin_name text,
    coverage_vintage date,
    dist_tower_m numeric,
    nightlights_admin_unit text,
    nightlights_radiance_mean numeric,
    rainfall_recent_mm_yr numeric,
    rainfall_anomaly_pct numeric,
    rainfall_driest_year_pct numeric,
    rainfall_max5day_mean_mm numeric,
    rainfall_max5day_p90_mm numeric,
    landcover_class_io text,
    landcover_io_year integer,
    black_cotton_risk text,
    ndvi_year integer,
    pop_is_census_calibrated boolean DEFAULT false NOT NULL,
    field_confidence jsonb,
    field_sources jsonb,
    CONSTRAINT parcel_intelligence_black_cotton_risk_check CHECK (((black_cotton_risk IS NULL) OR (black_cotton_risk = ANY (ARRAY['none'::text, 'possible'::text, 'likely'::text])))),
    CONSTRAINT parcel_intelligence_coverage_2g_pct_check CHECK (((coverage_2g_pct IS NULL) OR ((coverage_2g_pct >= (0)::numeric) AND (coverage_2g_pct <= (100)::numeric)))),
    CONSTRAINT parcel_intelligence_coverage_4g_pct_check CHECK (((coverage_4g_pct IS NULL) OR ((coverage_4g_pct >= (0)::numeric) AND (coverage_4g_pct <= (100)::numeric)))),
    CONSTRAINT parcel_intelligence_coverage_4g_pct_safaricom_check CHECK (((coverage_4g_pct_safaricom IS NULL) OR ((coverage_4g_pct_safaricom >= (0)::numeric) AND (coverage_4g_pct_safaricom <= (100)::numeric)))),
    CONSTRAINT parcel_intelligence_coverage_4g_pct_telkom_check CHECK (((coverage_4g_pct_telkom IS NULL) OR ((coverage_4g_pct_telkom >= (0)::numeric) AND (coverage_4g_pct_telkom <= (100)::numeric)))),
    CONSTRAINT parcel_intelligence_coverage_admin_level_check CHECK (((coverage_admin_level IS NULL) OR (coverage_admin_level = ANY (ARRAY['sublocation'::text, 'location'::text, 'ward'::text, 'constituency'::text, 'county'::text])))),
    CONSTRAINT parcel_intelligence_flood_cell_check CHECK (((flood_risk_class_cell IS NULL) OR (flood_risk_class_cell = ANY (ARRAY['very_low'::text, 'low'::text, 'moderate'::text, 'high'::text, 'very_high'::text, 'permanent_water'::text])))),
    CONSTRAINT parcel_intelligence_flood_risk_class_check CHECK (((flood_risk_class IS NULL) OR (flood_risk_class = ANY (ARRAY['very_low'::text, 'low'::text, 'moderate'::text, 'high'::text, 'very_high'::text, 'permanent_water'::text])))),
    CONSTRAINT parcel_intelligence_landslide_risk_class_check CHECK ((landslide_risk_class = ANY (ARRAY['low'::text, 'moderate'::text, 'high'::text]))),
    CONSTRAINT parcel_intelligence_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: COLUMN parcel_intelligence.dist_bus_stop_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_bus_stop_m IS 'AWAITING DATA: transport.bus_stops (P2, OSM). Matatu stage proximity matters to buyers.';


--
-- Name: COLUMN parcel_intelligence.dist_hospital_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_hospital_m IS 'social.health, 12,403 facilities. CHECKLIST C8: located to WARD CENTROID, not true GPS (confidence 2) - the openAFRICA export carries no coordinates. 82% matched a ward; only 9 pharmacies loaded. Attributes (KEPH level, ownership, MFL code) are exact; the POSITION is not. Do not quote this distance to the metre.';


--
-- Name: COLUMN parcel_intelligence.dist_market_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_market_m IS 'AWAITING DATA: social.markets (P2, county governments). Key for agricultural buyers.';


--
-- Name: COLUMN parcel_intelligence.dist_police_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_police_m IS 'AWAITING DATA: social.public_services (P2, OSM).';


--
-- Name: COLUMN parcel_intelligence.dist_power_line_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_power_line_m IS 'AWAITING DATA: utilities.power_distribution (P1, one of only two P1 datasets not built). BLOCKED EXTERNALLY on a Kenya Power derived-use licence - permission to store "nearest MV line: 340 m" without redistributing the network. Checklist A5. Interim proxy: OSM power lines plus nightlights.';


--
-- Name: COLUMN parcel_intelligence.dist_transformer_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_transformer_m IS 'AWAITING DATA: utilities.power_facilities (P2, Kenya Power). Transformer distance approximates connection COST, which is the buyer question.';


--
-- Name: COLUMN parcel_intelligence.dist_water_line_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_water_line_m IS 'AWAITING DATA: utilities.water_lines (P3, county governments / WASREB).';


--
-- Name: COLUMN parcel_intelligence.dist_sewer_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_sewer_m IS 'AWAITING DATA: utilities.sewer_lines (P3, county governments). Urban parcels only.';


--
-- Name: COLUMN parcel_intelligence.in_riparian_buffer; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.in_riparian_buffer IS 'environment.riparian_buffers, Geocode-derived under EMCA 2009 (6 m min, 30 m max from the high-water mark), Water (Resources) Regs 2025, Survey Regs Cap 299. Buffered from the river CENTRE LINE because OSM gives no channel width, so very wide rivers are slightly under-measured. Confidence 3: a rules-based estimate, NOT a surveyed boundary. This is high-value and under-served - a parcel overlapping a riparian reserve is partly unbuildable by law - so state the basis, never assert the line.';


--
-- Name: COLUMN parcel_intelligence.in_wetland; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.in_wetland IS 'AWAITING DATA: environment.wetlands (P2). Building on wetland is a top buyer risk. NOTE 3,383 OSM wetland/riverbank polygons were deliberately skipped in session 2 pending a better source.';


--
-- Name: COLUMN parcel_intelligence.flood_risk_class; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.flood_risk_class IS 'RULE D2: this is the WORST class within flood_search_radius_m, NOT the parcel''s own cell. Garissa town centre reads Very low on its own pixel with Very high a few hundred metres away, because the town sits on a terrace. A buyer needs to know what is next door. RULE D1: MODELLED, not measured - every buyer-facing use must say so. RULE D3: permanent_water is a LAND-COVER FACT, never "beyond very high", and is not benign - see dist_permanent_water_m.';


--
-- Name: COLUMN parcel_intelligence.landslide_risk_class; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.landslide_risk_class IS 'AWAITING DATA: hazards.landslide (P2, Geocode-derived from slope + rainfall + soil). All three inputs are now built.';


--
-- Name: COLUMN parcel_intelligence.aspect_dominant; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.aspect_dominant IS 'AWAITING DATA: terrain.aspect (P2). Derivable from the DEM we hold.';


--
-- Name: COLUMN parcel_intelligence.soil_drainage; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.soil_drainage IS 'AWAITING DATA: soils.drainage (P2, Geocode-derived from texture + TWI). Both inputs are built.';


--
-- Name: COLUMN parcel_intelligence.soil_depth_class; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.soil_depth_class IS 'AWAITING DATA: soils.depth (P2, iSDA/SoilGrids).';


--
-- Name: COLUMN parcel_intelligence.soil_fertility; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.soil_fertility IS 'AWAITING DATA: soils.fertility (P2, Geocode composite of pH, carbon, nutrients).';


--
-- Name: COLUMN parcel_intelligence.rainfall_normal_mm_yr; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.rainfall_normal_mm_yr IS 'CHIRPS v3.0 1991-2020 WMO normal. The CLIMATOLOGY, and the right input for "can I farm here". RULE C5: THIS LAYER RUNS WET, about +145 mm across 16 reference towns - partly CHIRPS over steep terrain with thin gauge density, partly our reference figures being approximate. Do not treat as calibrated.';


--
-- Name: COLUMN parcel_intelligence.temp_mean_c; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.temp_mean_c IS 'AWAITING DATA: climate.temperature (P2, ERA5 / NASA POWER).';


--
-- Name: COLUMN parcel_intelligence.solar_kwh_m2_day; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.solar_kwh_m2_day IS 'AWAITING DATA: climate.solar (P3, Global Solar Atlas). Off-grid potential.';


--
-- Name: COLUMN parcel_intelligence.landcover_class_worldcover; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.landcover_class_worldcover IS 'ESA WorldCover 2021 v200, 10 m, 11 classes. THE CLASSIFICATION REFERENCE for "what is this exact spot". RULE D6: NEVER tell a buyer "this is not farmland" from land cover alone - WorldCover under-detects smallholder mosaic farming, and NDVI showed up to 4.2x the mapped cropland area is as green as cropland. Use NDVI + rainfall + soil together.';


--
-- Name: COLUMN parcel_intelligence.ndvi_mean; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.ndvi_mean IS 'Sentinel-2 geomedian NDVI. CHECKLIST C6: this is a SINGLE YEAR, not a normal, and 2024 was wet after the 2020-23 drought. The enrichment engine must NOT treat it as a stable baseline. ndvi_year records which year, so a report can say so.';


--
-- Name: COLUMN parcel_intelligence.built_up_pct_1km; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.built_up_pct_1km IS 'RULE D8: a FULL CELL IS 8,606 m2, not 8,548, and the fraction MUST be capped at 1.0. GHSL is computed on an equal-area Mollweide grid and regridded to lat/lon, so its cell does not match a naive WGS84 calculation. Divide by the wrong constant and a parcel reads "101% built". Sum square metres over the neighbourhood, then divide by that neighbourhood''s true area - percentages do not add.';


--
-- Name: COLUMN parcel_intelligence.pop_density_km2; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.pop_density_km2 IS 'WorldPop 2020 constrained. RULE D9: PREFER RELATIVE COMPARISONS ("more people near A than B") over absolute counts until the KNBS census is loaded. WorldPop reads +16% against the 2019 census nationally and +209% in Mandera. Do NOT rescale the grid to the census - that buries a real disagreement inside an authoritative-looking number.';


--
-- Name: COLUMN parcel_intelligence.nightlights_trend_radiance_yr; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.nightlights_trend_radiance_yr IS 'The development signal: ABSOLUTE change in summed radiance per year. RULE D10: this is a SUM and scales with unit area - never compare a large ward to a small one on it directly; use nightlights_radiance_mean for like-for-like. RULE D11: the percentage version is deliberately dead. RULE D13: radiance is not linear in economic activity - VIIRS compresses bright cores, and SNPP''s sensor degraded across the series.';


--
-- Name: COLUMN parcel_intelligence.dist_fiber_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_fiber_m IS 'AWAITING DATA: connectivity.fiber (P3, CA NOFBI backbone, by request).';


--
-- Name: COLUMN parcel_intelligence.zoning_class; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.zoning_class IS 'AWAITING DATA: land.zoning (P2). County physical plans, often hard copy, digitised per pilot county.';


--
-- Name: COLUMN parcel_intelligence.soil_composition; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.soil_composition IS 'Per-class percentage cover under the parcel footprint. Single-value
     columns (soil_type etc.) hold the dominant class for fast queries;
     composition holds the full breakdown for reports.';


--
-- Name: COLUMN parcel_intelligence.flood_search_radius_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.flood_search_radius_m IS 'Radius used for flood_risk_class. Recorded rather than assumed: a class without its radius is not reproducible, and the calibration proved a single-cell read tests the coordinate rather than the layer.';


--
-- Name: COLUMN parcel_intelligence.dist_permanent_water_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_permanent_water_m IS 'RULE D3: proximity to permanent water is its own risk signal and must be surfaced independently of flood_risk_class. Budalangi is the worked example - HAND cannot see dike failure, so the hazard class understates it and this column is what warns.';


--
-- Name: COLUMN parcel_intelligence.flood_forcing_max5day_mm; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.flood_forcing_max5day_mm IS 'From rainfall_max5day_mean. HAND says where water goes; this says how much arrives. Present as susceptibility x forcing, two numbers a buyer can follow - NEVER merged into one score with invented weights.';


--
-- Name: COLUMN parcel_intelligence.coverage_4g_pct; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.coverage_4g_pct IS 'RULE D4: the share of the SUBLOCATION containing this parcel that the CA reports as 4G-covered. Say "the area around this parcel is about 65% 4G-covered". NEVER "this parcel has 4G". Pair with dist_tower_m, which IS point-specific. UNRESOLVED (checklist B1): the CA published 3G and 4G as one dataset under two names. If we kept the mislabelled survivor, what this column calls 4G may be 3G.';


--
-- Name: COLUMN parcel_intelligence.coverage_4g_pct_safaricom; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.coverage_4g_pct_safaricom IS 'RULE D5: AIRTEL IS ABSENT FROM THIS TABLE BECAUSE THE CA DID NOT PUBLISH AN AIRTEL PERCENTAGE - absence of DATA, not absence of coverage. Any per-operator display must say so explicitly.';


--
-- Name: COLUMN parcel_intelligence.coverage_vintage; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.coverage_vintage IS 'RULE D12: CA vintages run Jan 2022 to Aug 2023 and are NOT comparable across technologies (2G covers 9,274 polygons, 4G covers 7,134). Per-parcel lookup is fine; national cross-technology comparison is not.';


--
-- Name: COLUMN parcel_intelligence.dist_tower_m; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.dist_tower_m IS 'Nearest cell tower, connectivity.towers (OpenCellID, confidence 2 - crowdsourced positions). The point-level half of the D4 pairing.';


--
-- Name: COLUMN parcel_intelligence.nightlights_admin_unit; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.nightlights_admin_unit IS 'Which ward this parcel inherited its nightlights figures from. Required by D10: without the unit, the SUM cannot be interpreted. NOTE 3 of 1,425 wards return no data in any year (checklist C7) and will be NULL here.';


--
-- Name: COLUMN parcel_intelligence.rainfall_driest_year_pct; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.rainfall_driest_year_pct IS 'The driest single year of 2021-2025 as a percentage of normal. THIS IS THE COLUMN THAT STOPS A MEAN HIDING A DROUGHT: the window averages 107% of normal while 68.9% of Kenya had a year under 75% and 8.6% under 50%. Use for "how bad does it get here"; use the anomaly for "what has it been like lately".';


--
-- Name: COLUMN parcel_intelligence.rainfall_max5day_mean_mm; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.rainfall_max5day_mean_mm IS 'CHIRPS v2.0 (v3.0 publishes no pentad product - checklist C11). From FIXED pentads, so a storm straddling a boundary is split: this UNDER-ESTIMATES a true rolling 5-day maximum by roughly 10-20%, consistently nationally, so the spatial pattern is sound. NEVER quote as design rainfall for engineering (C12).';


--
-- Name: COLUMN parcel_intelligence.landcover_class_io; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.landcover_class_io IS 'Impact Observatory, 9 classes, ~93 m. The RECENCY layer (ESA published nothing after 2021). IO "Rangeland" absorbs BOTH WorldCover Shrubland AND Grassland, so the two CANNOT be compared class by class. IO "Built area" is definitionally broader than WorldCover Built-up - about 7x at the 2017 baseline, before any drift - so never present them as one quantity. THE IO CHANGE LAYER IS QUARANTINED (pending_review) and must not be used: the series is not temporally consistent. Checklist C13.';


--
-- Name: COLUMN parcel_intelligence.black_cotton_risk; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.black_cotton_risk IS 'RULE D7: derived from SoilGrids Vertisols OR iSDA clay texture, NEVER either alone. SoilGrids maps the Athi-Kapiti plains as Luvisols when they are classic black cotton - and that is exactly where Nairobi peri-urban selling is most active. iSDA reads Clay Loam there. likely = both agree; possible = one of the two; none = neither.';


--
-- Name: COLUMN parcel_intelligence.pop_is_census_calibrated; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.pop_is_census_calibrated IS 'FALSE until KNBS county/ward census is loaded (checklist C3, B3). While false, the API and PDF layers must suppress absolute population claims. This makes rule D9 enforceable in code instead of remembered.';


--
-- Name: COLUMN parcel_intelligence.field_confidence; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.field_confidence IS 'Per-field confidence 1-5, e.g. {"soil_ph": 3, "flood_risk_class": 3, "dist_any_road_m": 4}. Confidence is not uniform across a row: roads are 4, health facilities are 2 because they sit at ward centroids, flood is 3 because it is modelled. A report that prints one confidence for the whole parcel is lying about most of it.';


--
-- Name: COLUMN parcel_intelligence.field_sources; Type: COMMENT; Schema: analytics; Owner: -
--

COMMENT ON COLUMN analytics.parcel_intelligence.field_sources IS 'Per-field lineage, e.g. {"soil_ph": {"raster_id": 12, "checksum": "..."}}. Rasters are versioned and re-run; without this, a number computed today cannot be reproduced after the next re-run. The raster catalogue is the truth about a file - this records WHICH truth was used.';


--
-- Name: parcel_intelligence_intel_id_seq; Type: SEQUENCE; Schema: analytics; Owner: -
--

ALTER TABLE analytics.parcel_intelligence ALTER COLUMN intel_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME analytics.parcel_intelligence_intel_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: suitability_scores; Type: TABLE; Schema: analytics; Owner: -
--

CREATE TABLE analytics.suitability_scores (
    score_id bigint NOT NULL,
    parcel_id uuid NOT NULL,
    intel_id bigint,
    residential_score numeric,
    agricultural_score numeric,
    commercial_score numeric,
    investment_score numeric,
    overall_score numeric,
    score_breakdown jsonb,
    model_version text NOT NULL,
    computed_at timestamp with time zone DEFAULT now() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT suitability_scores_agricultural_score_check CHECK (((agricultural_score >= (0)::numeric) AND (agricultural_score <= (100)::numeric))),
    CONSTRAINT suitability_scores_commercial_score_check CHECK (((commercial_score >= (0)::numeric) AND (commercial_score <= (100)::numeric))),
    CONSTRAINT suitability_scores_investment_score_check CHECK (((investment_score >= (0)::numeric) AND (investment_score <= (100)::numeric))),
    CONSTRAINT suitability_scores_overall_score_check CHECK (((overall_score >= (0)::numeric) AND (overall_score <= (100)::numeric))),
    CONSTRAINT suitability_scores_residential_score_check CHECK (((residential_score >= (0)::numeric) AND (residential_score <= (100)::numeric))),
    CONSTRAINT suitability_scores_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: suitability_scores_score_id_seq; Type: SEQUENCE; Schema: analytics; Owner: -
--

ALTER TABLE analytics.suitability_scores ALTER COLUMN score_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME analytics.suitability_scores_score_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: api_keys; Type: TABLE; Schema: clients; Owner: -
--

CREATE TABLE clients.api_keys (
    api_key_id uuid DEFAULT gen_random_uuid() NOT NULL,
    company_id uuid NOT NULL,
    key_hash text NOT NULL,
    label text,
    scopes text[] DEFAULT '{read}'::text[] NOT NULL,
    expires_at timestamp with time zone,
    revoked boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: api_usage; Type: TABLE; Schema: clients; Owner: -
--

CREATE TABLE clients.api_usage (
    usage_id bigint NOT NULL,
    api_key_id uuid,
    period_start date NOT NULL,
    period_end date NOT NULL,
    calls bigint DEFAULT 0 NOT NULL,
    reports_generated integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: api_usage_usage_id_seq; Type: SEQUENCE; Schema: clients; Owner: -
--

ALTER TABLE clients.api_usage ALTER COLUMN usage_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME clients.api_usage_usage_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: branding; Type: TABLE; Schema: clients; Owner: -
--

CREATE TABLE clients.branding (
    branding_id uuid DEFAULT gen_random_uuid() NOT NULL,
    company_id uuid NOT NULL,
    logo_url text,
    primary_color text,
    secondary_color text,
    report_footer text,
    custom_domain text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: companies; Type: TABLE; Schema: clients; Owner: -
--

CREATE TABLE clients.companies (
    company_id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    contact_email text,
    contact_phone text,
    county_code text,
    is_active boolean DEFAULT true NOT NULL,
    onboarded_at date,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    marketplace_opt_in boolean DEFAULT false NOT NULL
);


--
-- Name: COLUMN companies.marketplace_opt_in; Type: COMMENT; Schema: clients; Owner: -
--

COMMENT ON COLUMN clients.companies.marketplace_opt_in IS 'Client chose to display listings on a future Geocode marketplace.
     Opt-in only, set during onboarding. Leads always route to the client.';


--
-- Name: subscriptions; Type: TABLE; Schema: clients; Owner: -
--

CREATE TABLE clients.subscriptions (
    subscription_id uuid DEFAULT gen_random_uuid() NOT NULL,
    company_id uuid NOT NULL,
    plan text NOT NULL,
    monthly_fee_kes numeric,
    parcel_limit integer,
    report_limit integer,
    api_calls_limit bigint,
    starts_on date NOT NULL,
    ends_on date,
    sub_status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT subscriptions_plan_check CHECK ((plan = ANY (ARRAY['starter'::text, 'growth'::text, 'enterprise'::text, 'custom'::text]))),
    CONSTRAINT subscriptions_sub_status_check CHECK ((sub_status = ANY (ARRAY['trial'::text, 'active'::text, 'past_due'::text, 'cancelled'::text])))
);


--
-- Name: stations; Type: TABLE; Schema: climate; Owner: -
--

CREATE TABLE climate.stations (
    id bigint NOT NULL,
    name text NOT NULL,
    station_code text,
    operator text DEFAULT 'Kenya Meteorological Department'::text,
    elevation_m numeric,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT stations_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT stations_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: stations_id_seq; Type: SEQUENCE; Schema: climate; Owner: -
--

ALTER TABLE climate.stations ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME climate.stations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: zonal_stats; Type: TABLE; Schema: climate; Owner: -
--

CREATE TABLE climate.zonal_stats (
    id bigint NOT NULL,
    admin_level text NOT NULL,
    admin_code text NOT NULL,
    variable text NOT NULL,
    period text NOT NULL,
    stat text DEFAULT 'mean'::text NOT NULL,
    value numeric NOT NULL,
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT zonal_stats_admin_level_check CHECK ((admin_level = ANY (ARRAY['county'::text, 'constituency'::text, 'ward'::text]))),
    CONSTRAINT zonal_stats_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT zonal_stats_stat_check CHECK ((stat = ANY (ARRAY['mean'::text, 'min'::text, 'max'::text, 'sum'::text, 'median'::text, 'stddev'::text]))),
    CONSTRAINT zonal_stats_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: zonal_stats_id_seq; Type: SEQUENCE; Schema: climate; Owner: -
--

ALTER TABLE climate.zonal_stats ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME climate.zonal_stats_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: coverage; Type: TABLE; Schema: connectivity; Owner: -
--

CREATE TABLE connectivity.coverage (
    id bigint NOT NULL,
    operator text NOT NULL,
    technology text NOT NULL,
    signal_class text,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    coverage_pct numeric,
    admin_level text,
    admin_name text,
    admin_code text,
    ward_name text,
    ward_code_src text,
    source_layer text,
    population numeric,
    area_sqkm numeric,
    covered_area_sqkm numeric,
    CONSTRAINT coverage_admin_level_check CHECK (((admin_level IS NULL) OR (admin_level = ANY (ARRAY['sublocation'::text, 'location'::text, 'ward'::text, 'constituency'::text, 'county'::text])))),
    CONSTRAINT coverage_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT coverage_coverage_pct_check CHECK (((coverage_pct IS NULL) OR ((coverage_pct >= (0)::numeric) AND (coverage_pct <= (100)::numeric)))),
    CONSTRAINT coverage_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text]))),
    CONSTRAINT coverage_technology_check CHECK ((technology = ANY (ARRAY['2g'::text, '3g'::text, '4g'::text, '5g'::text])))
);


--
-- Name: COLUMN coverage.operator; Type: COMMENT; Schema: connectivity; Owner: -
--

COMMENT ON COLUMN connectivity.coverage.operator IS 'Safaricom / Airtel / Telkom, or ''all'' where the CA publishes the three combined';


--
-- Name: COLUMN coverage.signal_class; Type: COMMENT; Schema: connectivity; Owner: -
--

COMMENT ON COLUMN connectivity.coverage.signal_class IS 'Reserved for true propagation sources. NULL for CA admin-unit percentages.';


--
-- Name: COLUMN coverage.coverage_pct; Type: COMMENT; Schema: connectivity; Owner: -
--

COMMENT ON COLUMN connectivity.coverage.coverage_pct IS 'Share of the admin unit reported as covered. NOT a point-level guarantee.';


--
-- Name: COLUMN coverage.source_layer; Type: COMMENT; Schema: connectivity; Owner: -
--

COMMENT ON COLUMN connectivity.coverage.source_layer IS 'CA FeatureServer service name this row was loaded from. Check it before trusting a row: some CA layers are dated or marked test.';


--
-- Name: coverage_id_seq; Type: SEQUENCE; Schema: connectivity; Owner: -
--

ALTER TABLE connectivity.coverage ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME connectivity.coverage_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: fiber; Type: TABLE; Schema: connectivity; Owner: -
--

CREATE TABLE connectivity.fiber (
    id bigint NOT NULL,
    operator text,
    network_level text,
    county_code text,
    geom public.geometry(MultiLineString,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT fiber_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT fiber_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: fiber_id_seq; Type: SEQUENCE; Schema: connectivity; Owner: -
--

ALTER TABLE connectivity.fiber ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME connectivity.fiber_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: towers; Type: TABLE; Schema: connectivity; Owner: -
--

CREATE TABLE connectivity.towers (
    id bigint NOT NULL,
    operator text,
    radio text,
    cell_id text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT towers_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT towers_radio_check CHECK ((radio = ANY (ARRAY['gsm'::text, 'umts'::text, 'lte'::text, 'nr'::text, 'unknown'::text]))),
    CONSTRAINT towers_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: towers_id_seq; Type: SEQUENCE; Schema: connectivity; Owner: -
--

ALTER TABLE connectivity.towers ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME connectivity.towers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: nightlights_stats; Type: TABLE; Schema: demographics; Owner: -
--

CREATE TABLE demographics.nightlights_stats (
    id bigint NOT NULL,
    admin_level text NOT NULL,
    admin_code text NOT NULL,
    period text NOT NULL,
    radiance_mean numeric,
    radiance_sum numeric,
    lit_area_pct numeric,
    trend_pct_yr numeric,
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    trend_radiance_yr numeric,
    CONSTRAINT nightlights_stats_admin_level_check CHECK ((admin_level = ANY (ARRAY['county'::text, 'constituency'::text, 'ward'::text]))),
    CONSTRAINT nightlights_stats_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT nightlights_stats_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: COLUMN nightlights_stats.trend_pct_yr; Type: COMMENT; Schema: demographics; Owner: -
--

COMMENT ON COLUMN demographics.nightlights_stats.trend_pct_yr IS 'DELIBERATELY NULL as of v1.5. A percentage rate from a near-zero base is unbounded: it gave a median of 33%/yr and ranked rural electrification above peri-urban development. Revisit only as an explicit ELECTRIFICATION indicator with a baseline floor, never as the development signal.';


--
-- Name: COLUMN nightlights_stats.trend_radiance_yr; Type: COMMENT; Schema: demographics; Owner: -
--

COMMENT ON COLUMN demographics.nightlights_stats.trend_radiance_yr IS 'Development signal: change in radiance_sum per year (absolute). Ranks intensification within already-lit areas, which is what peri-urban land development looks like. Use THIS for "is the area developing". Not comparable between units of different size: pair with area or use radiance_mean for like-for-like.';


--
-- Name: nightlights_stats_id_seq; Type: SEQUENCE; Schema: demographics; Owner: -
--

ALTER TABLE demographics.nightlights_stats ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME demographics.nightlights_stats_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: population_stats; Type: TABLE; Schema: demographics; Owner: -
--

CREATE TABLE demographics.population_stats (
    id bigint NOT NULL,
    admin_level text NOT NULL,
    admin_code text NOT NULL,
    year integer NOT NULL,
    population bigint,
    households bigint,
    density_per_km2 numeric,
    growth_rate_pct numeric,
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT population_stats_admin_level_check CHECK ((admin_level = ANY (ARRAY['county'::text, 'constituency'::text, 'ward'::text, 'sublocation'::text]))),
    CONSTRAINT population_stats_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT population_stats_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: population_stats_id_seq; Type: SEQUENCE; Schema: demographics; Owner: -
--

ALTER TABLE demographics.population_stats ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME demographics.population_stats_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: forests; Type: TABLE; Schema: environment; Owner: -
--

CREATE TABLE environment.forests (
    id bigint NOT NULL,
    name text,
    forest_type text,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT forests_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT forests_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: forests_id_seq; Type: SEQUENCE; Schema: environment; Owner: -
--

ALTER TABLE environment.forests ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME environment.forests_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: protected_areas; Type: TABLE; Schema: environment; Owner: -
--

CREATE TABLE environment.protected_areas (
    id bigint NOT NULL,
    name text NOT NULL,
    area_type text NOT NULL,
    authority text,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT protected_areas_area_type_check CHECK ((area_type = ANY (ARRAY['national_park'::text, 'national_reserve'::text, 'conservancy'::text, 'sanctuary'::text, 'wildlife_corridor'::text, 'marine_protected'::text]))),
    CONSTRAINT protected_areas_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT protected_areas_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: protected_areas_id_seq; Type: SEQUENCE; Schema: environment; Owner: -
--

ALTER TABLE environment.protected_areas ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME environment.protected_areas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: riparian_buffers; Type: TABLE; Schema: environment; Owner: -
--

CREATE TABLE environment.riparian_buffers (
    id bigint NOT NULL,
    river_id bigint,
    buffer_width_m numeric NOT NULL,
    legal_basis text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT riparian_buffers_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT riparian_buffers_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: riparian_buffers_id_seq; Type: SEQUENCE; Schema: environment; Owner: -
--

ALTER TABLE environment.riparian_buffers ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME environment.riparian_buffers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: rivers; Type: TABLE; Schema: environment; Owner: -
--

CREATE TABLE environment.rivers (
    id bigint NOT NULL,
    name text,
    river_class text,
    stream_order smallint,
    county_code text,
    geom public.geometry(MultiLineString,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    waterway_type text,
    CONSTRAINT rivers_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT rivers_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text]))),
    CONSTRAINT rivers_waterway_type_check CHECK ((waterway_type = ANY (ARRAY['river'::text, 'stream'::text, 'canal'::text, 'drain'::text])))
);


--
-- Name: COLUMN rivers.waterway_type; Type: COMMENT; Schema: environment; Owner: -
--

COMMENT ON COLUMN environment.rivers.waterway_type IS 'Physical channel type from OSM: river, stream, canal, drain. Distinct from river_class (perennial/seasonal), which awaits a hydrological source.';


--
-- Name: rivers_id_seq; Type: SEQUENCE; Schema: environment; Owner: -
--

ALTER TABLE environment.rivers ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME environment.rivers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: waterbodies; Type: TABLE; Schema: environment; Owner: -
--

CREATE TABLE environment.waterbodies (
    id bigint NOT NULL,
    name text,
    body_type text NOT NULL,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT waterbodies_body_type_check CHECK ((body_type = ANY (ARRAY['lake'::text, 'reservoir'::text, 'pond'::text, 'lagoon'::text]))),
    CONSTRAINT waterbodies_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT waterbodies_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: waterbodies_id_seq; Type: SEQUENCE; Schema: environment; Owner: -
--

ALTER TABLE environment.waterbodies ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME environment.waterbodies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: wetlands; Type: TABLE; Schema: environment; Owner: -
--

CREATE TABLE environment.wetlands (
    id bigint NOT NULL,
    name text,
    wetland_type text,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT wetlands_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT wetlands_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: wetlands_id_seq; Type: SEQUENCE; Schema: environment; Owner: -
--

ALTER TABLE environment.wetlands ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME environment.wetlands_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: drone_missions; Type: TABLE; Schema: imagery; Owner: -
--

CREATE TABLE imagery.drone_missions (
    mission_id uuid DEFAULT gen_random_uuid() NOT NULL,
    company_id uuid,
    project_name text,
    flown_on date,
    pilot text,
    equipment text,
    gsd_cm numeric,
    footprint public.geometry(Polygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT drone_missions_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT drone_missions_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: orthophotos; Type: TABLE; Schema: imagery; Owner: -
--

CREATE TABLE imagery.orthophotos (
    id bigint NOT NULL,
    mission_id uuid,
    storage_url text NOT NULL,
    pixel_size_cm numeric,
    footprint public.geometry(Polygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT orthophotos_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT orthophotos_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: orthophotos_id_seq; Type: SEQUENCE; Schema: imagery; Owner: -
--

ALTER TABLE imagery.orthophotos ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME imagery.orthophotos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: scenes; Type: TABLE; Schema: imagery; Owner: -
--

CREATE TABLE imagery.scenes (
    id bigint NOT NULL,
    sensor text NOT NULL,
    scene_id text NOT NULL,
    acquired_on date NOT NULL,
    cloud_cover_pct numeric,
    storage_url text,
    footprint public.geometry(Polygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT scenes_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT scenes_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: scenes_id_seq; Type: SEQUENCE; Schema: imagery; Owner: -
--

ALTER TABLE imagery.scenes ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME imagery.scenes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: land_use; Type: TABLE; Schema: land; Owner: -
--

CREATE TABLE land.land_use (
    id bigint NOT NULL,
    use_class text NOT NULL,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT land_use_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT land_use_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: land_use_id_seq; Type: SEQUENCE; Schema: land; Owner: -
--

ALTER TABLE land.land_use ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME land.land_use_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: parcel_documents; Type: TABLE; Schema: land; Owner: -
--

CREATE TABLE land.parcel_documents (
    document_id uuid DEFAULT gen_random_uuid() NOT NULL,
    parcel_id uuid NOT NULL,
    doc_type text NOT NULL,
    storage_url text NOT NULL,
    uploaded_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT parcel_documents_doc_type_check CHECK ((doc_type = ANY (ARRAY['survey_plan'::text, 'mutation'::text, 'title_copy'::text, 'search_certificate'::text, 'agreement'::text, 'other'::text])))
);


--
-- Name: parcel_history; Type: TABLE; Schema: land; Owner: -
--

CREATE TABLE land.parcel_history (
    history_id bigint NOT NULL,
    parcel_id uuid NOT NULL,
    event text NOT NULL,
    detail jsonb,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    recorded_by uuid
);


--
-- Name: parcel_history_history_id_seq; Type: SEQUENCE; Schema: land; Owner: -
--

ALTER TABLE land.parcel_history ALTER COLUMN history_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME land.parcel_history_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: parcel_images; Type: TABLE; Schema: land; Owner: -
--

CREATE TABLE land.parcel_images (
    image_id uuid DEFAULT gen_random_uuid() NOT NULL,
    parcel_id uuid NOT NULL,
    image_type text,
    storage_url text NOT NULL,
    captured_on date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT parcel_images_image_type_check CHECK ((image_type = ANY (ARRAY['ground_photo'::text, 'drone'::text, 'satellite_chip'::text, 'other'::text])))
);


--
-- Name: parcels; Type: TABLE; Schema: land; Owner: -
--

CREATE TABLE land.parcels (
    parcel_id uuid DEFAULT gen_random_uuid() NOT NULL,
    company_id uuid NOT NULL,
    parcel_ref text NOT NULL,
    lr_number text,
    project_name text,
    county_code text,
    ward_code text,
    area_sqm numeric,
    price_kes numeric,
    listing_status text DEFAULT 'available'::text NOT NULL,
    geom public.geometry(MultiPolygon,4326) NOT NULL,
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    listed_date date,
    sold_date date,
    sold_price_kes numeric,
    CONSTRAINT parcels_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT parcels_listing_status_check CHECK ((listing_status = ANY (ARRAY['available'::text, 'reserved'::text, 'deposit_paid'::text, 'sold'::text, 'off_market'::text, 'coming_soon'::text, 'under_survey'::text, 'future_phase'::text, 'cancelled'::text, 'hidden'::text]))),
    CONSTRAINT parcels_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: COLUMN parcels.sold_date; Type: COMMENT; Schema: land; Owner: -
--

COMMENT ON COLUMN land.parcels.sold_date IS 'With listed_date gives time-on-market: the core market intelligence metric';


--
-- Name: valuations; Type: TABLE; Schema: land; Owner: -
--

CREATE TABLE land.valuations (
    valuation_id bigint NOT NULL,
    parcel_id uuid,
    valuation_kes numeric NOT NULL,
    valuation_date date NOT NULL,
    method text,
    valuer text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: valuations_valuation_id_seq; Type: SEQUENCE; Schema: land; Owner: -
--

ALTER TABLE land.valuations ALTER COLUMN valuation_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME land.valuations_valuation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: zoning; Type: TABLE; Schema: land; Owner: -
--

CREATE TABLE land.zoning (
    id bigint NOT NULL,
    zone_class text NOT NULL,
    zone_label text,
    plan_name text,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT zoning_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT zoning_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: zoning_id_seq; Type: SEQUENCE; Schema: land; Owner: -
--

ALTER TABLE land.zoning ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME land.zoning_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: api_logs; Type: TABLE; Schema: logs; Owner: -
--

CREATE TABLE logs.api_logs (
    log_id bigint NOT NULL,
    api_key_id uuid,
    endpoint text NOT NULL,
    method text NOT NULL,
    status_code integer,
    latency_ms integer,
    ip_address inet,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: api_logs_log_id_seq; Type: SEQUENCE; Schema: logs; Owner: -
--

ALTER TABLE logs.api_logs ALTER COLUMN log_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME logs.api_logs_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: downloads; Type: TABLE; Schema: logs; Owner: -
--

CREATE TABLE logs.downloads (
    download_id bigint NOT NULL,
    user_id uuid,
    report_id uuid,
    resource text NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: downloads_download_id_seq; Type: SEQUENCE; Schema: logs; Owner: -
--

ALTER TABLE logs.downloads ALTER COLUMN download_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME logs.downloads_download_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: error_logs; Type: TABLE; Schema: logs; Owner: -
--

CREATE TABLE logs.error_logs (
    error_id bigint NOT NULL,
    service text NOT NULL,
    severity text DEFAULT 'error'::text NOT NULL,
    message text NOT NULL,
    context jsonb,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT error_logs_severity_check CHECK ((severity = ANY (ARRAY['warning'::text, 'error'::text, 'critical'::text])))
);


--
-- Name: error_logs_error_id_seq; Type: SEQUENCE; Schema: logs; Owner: -
--

ALTER TABLE logs.error_logs ALTER COLUMN error_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME logs.error_logs_error_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: user_activity; Type: TABLE; Schema: logs; Owner: -
--

CREATE TABLE logs.user_activity (
    activity_id bigint NOT NULL,
    user_id uuid,
    activity text NOT NULL,
    detail jsonb,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_activity_activity_id_seq; Type: SEQUENCE; Schema: logs; Owner: -
--

ALTER TABLE logs.user_activity ALTER COLUMN activity_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME logs.user_activity_activity_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: datasets; Type: TABLE; Schema: metadata; Owner: -
--

CREATE TABLE metadata.datasets (
    dataset_id integer NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    category text NOT NULL,
    description text,
    buyer_question text,
    source_id integer,
    backup_source_id integer,
    license_id integer,
    storage text DEFAULT 'postgis'::text NOT NULL,
    target_table text,
    native_crs text,
    resolution text,
    update_frequency text,
    coverage text DEFAULT 'national'::text NOT NULL,
    priority text DEFAULT 'P2'::text NOT NULL,
    etl_status text DEFAULT 'planned'::text NOT NULL,
    confidence smallint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT datasets_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT datasets_coverage_check CHECK ((coverage = ANY (ARRAY['national'::text, 'pilot_counties'::text, 'partial'::text, 'global'::text]))),
    CONSTRAINT datasets_etl_status_check CHECK ((etl_status = ANY (ARRAY['planned'::text, 'sourced'::text, 'ingested'::text, 'validated'::text, 'published'::text, 'deprecated'::text]))),
    CONSTRAINT datasets_priority_check CHECK ((priority = ANY (ARRAY['P1'::text, 'P2'::text, 'P3'::text]))),
    CONSTRAINT datasets_storage_check CHECK ((storage = ANY (ARRAY['postgis'::text, 'object_storage'::text])))
);


--
-- Name: datasets_dataset_id_seq; Type: SEQUENCE; Schema: metadata; Owner: -
--

ALTER TABLE metadata.datasets ALTER COLUMN dataset_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME metadata.datasets_dataset_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: etl_runs; Type: TABLE; Schema: metadata; Owner: -
--

CREATE TABLE metadata.etl_runs (
    run_id bigint NOT NULL,
    dataset_id integer,
    pipeline text NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    run_status text DEFAULT 'running'::text NOT NULL,
    rows_in bigint,
    rows_out bigint,
    rows_rejected bigint,
    log_url text,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT etl_runs_run_status_check CHECK ((run_status = ANY (ARRAY['running'::text, 'success'::text, 'failed'::text, 'partial'::text])))
);


--
-- Name: etl_runs_run_id_seq; Type: SEQUENCE; Schema: metadata; Owner: -
--

ALTER TABLE metadata.etl_runs ALTER COLUMN run_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME metadata.etl_runs_run_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: licenses; Type: TABLE; Schema: metadata; Owner: -
--

CREATE TABLE metadata.licenses (
    license_id integer NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    commercial_use boolean,
    share_alike boolean,
    attribution_text text,
    full_text_url text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: licenses_license_id_seq; Type: SEQUENCE; Schema: metadata; Owner: -
--

ALTER TABLE metadata.licenses ALTER COLUMN license_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME metadata.licenses_license_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: quality_scores; Type: TABLE; Schema: metadata; Owner: -
--

CREATE TABLE metadata.quality_scores (
    quality_id bigint NOT NULL,
    dataset_id integer,
    assessed_at date NOT NULL,
    completeness numeric,
    positional_accuracy numeric,
    attribute_accuracy numeric,
    currency_months numeric,
    overall_score numeric,
    assessed_by text,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT quality_scores_attribute_accuracy_check CHECK (((attribute_accuracy >= (0)::numeric) AND (attribute_accuracy <= (100)::numeric))),
    CONSTRAINT quality_scores_completeness_check CHECK (((completeness >= (0)::numeric) AND (completeness <= (100)::numeric))),
    CONSTRAINT quality_scores_overall_score_check CHECK (((overall_score >= (0)::numeric) AND (overall_score <= (100)::numeric)))
);


--
-- Name: quality_scores_quality_id_seq; Type: SEQUENCE; Schema: metadata; Owner: -
--

ALTER TABLE metadata.quality_scores ALTER COLUMN quality_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME metadata.quality_scores_quality_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: raster_catalog; Type: TABLE; Schema: metadata; Owner: -
--

CREATE TABLE metadata.raster_catalog (
    raster_id integer NOT NULL,
    dataset_id integer,
    name text NOT NULL,
    variable text,
    storage_url text NOT NULL,
    format text DEFAULT 'COG'::text NOT NULL,
    pixel_size_m numeric,
    band_count integer DEFAULT 1,
    nodata_value numeric,
    temporal_start date,
    temporal_end date,
    bbox public.geometry(Polygon,4326),
    checksum text,
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT raster_catalog_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT raster_catalog_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: raster_catalog_raster_id_seq; Type: SEQUENCE; Schema: metadata; Owner: -
--

ALTER TABLE metadata.raster_catalog ALTER COLUMN raster_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME metadata.raster_catalog_raster_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: refresh_logs; Type: TABLE; Schema: metadata; Owner: -
--

CREATE TABLE metadata.refresh_logs (
    refresh_id bigint NOT NULL,
    dataset_id integer,
    previous_version integer,
    new_version integer,
    refreshed_at timestamp with time zone DEFAULT now() NOT NULL,
    refreshed_by text,
    change_summary text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: refresh_logs_refresh_id_seq; Type: SEQUENCE; Schema: metadata; Owner: -
--

ALTER TABLE metadata.refresh_logs ALTER COLUMN refresh_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME metadata.refresh_logs_refresh_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: sources; Type: TABLE; Schema: metadata; Owner: -
--

CREATE TABLE metadata.sources (
    source_id integer NOT NULL,
    name text NOT NULL,
    organisation text,
    tier smallint NOT NULL,
    url text,
    license text,
    redistribution_allowed boolean,
    attribution_required boolean DEFAULT true,
    api_available boolean DEFAULT false,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT sources_tier_check CHECK (((tier >= 1) AND (tier <= 5)))
);


--
-- Name: sources_source_id_seq; Type: SEQUENCE; Schema: metadata; Owner: -
--

ALTER TABLE metadata.sources ALTER COLUMN source_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME metadata.sources_source_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: validation_results; Type: TABLE; Schema: metadata; Owner: -
--

CREATE TABLE metadata.validation_results (
    result_id bigint NOT NULL,
    rule_id integer,
    run_id bigint,
    executed_at timestamp with time zone DEFAULT now() NOT NULL,
    passed boolean NOT NULL,
    failures bigint DEFAULT 0,
    sample_failures jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: validation_results_result_id_seq; Type: SEQUENCE; Schema: metadata; Owner: -
--

ALTER TABLE metadata.validation_results ALTER COLUMN result_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME metadata.validation_results_result_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: validation_rules; Type: TABLE; Schema: metadata; Owner: -
--

CREATE TABLE metadata.validation_rules (
    rule_id integer NOT NULL,
    dataset_id integer,
    rule_name text NOT NULL,
    rule_type text NOT NULL,
    rule_sql text,
    severity text DEFAULT 'error'::text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT validation_rules_rule_type_check CHECK ((rule_type = ANY (ARRAY['geometry'::text, 'attribute'::text, 'topology'::text, 'referential'::text, 'range'::text]))),
    CONSTRAINT validation_rules_severity_check CHECK ((severity = ANY (ARRAY['error'::text, 'warning'::text, 'info'::text])))
);


--
-- Name: validation_rules_rule_id_seq; Type: SEQUENCE; Schema: metadata; Owner: -
--

ALTER TABLE metadata.validation_rules ALTER COLUMN rule_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME metadata.validation_rules_rule_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: reports; Type: TABLE; Schema: reports; Owner: -
--

CREATE TABLE reports.reports (
    report_id uuid DEFAULT gen_random_uuid() NOT NULL,
    parcel_id uuid NOT NULL,
    company_id uuid,
    requested_by uuid,
    report_type text DEFAULT 'full'::text NOT NULL,
    intel_version integer,
    score_version integer,
    pdf_url text,
    price_kes numeric,
    report_status text DEFAULT 'queued'::text NOT NULL,
    generated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT reports_report_status_check CHECK ((report_status = ANY (ARRAY['queued'::text, 'generating'::text, 'ready'::text, 'failed'::text, 'expired'::text]))),
    CONSTRAINT reports_report_type_check CHECK ((report_type = ANY (ARRAY['full'::text, 'summary'::text, 'custom'::text])))
);


--
-- Name: education; Type: TABLE; Schema: social; Owner: -
--

CREATE TABLE social.education (
    id bigint NOT NULL,
    name text NOT NULL,
    level text NOT NULL,
    ownership text,
    knec_code text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT education_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT education_level_check CHECK ((level = ANY (ARRAY['primary'::text, 'secondary'::text, 'tvet'::text, 'university'::text, 'other'::text]))),
    CONSTRAINT education_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: education_id_seq; Type: SEQUENCE; Schema: social; Owner: -
--

ALTER TABLE social.education ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME social.education_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: financial; Type: TABLE; Schema: social; Owner: -
--

CREATE TABLE social.financial (
    id bigint NOT NULL,
    name text NOT NULL,
    facility_type text NOT NULL,
    institution text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT financial_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT financial_facility_type_check CHECK ((facility_type = ANY (ARRAY['bank_branch'::text, 'atm'::text, 'sacco'::text, 'microfinance'::text, 'mobile_money_agent'::text]))),
    CONSTRAINT financial_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: financial_id_seq; Type: SEQUENCE; Schema: social; Owner: -
--

ALTER TABLE social.financial ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME social.financial_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: health; Type: TABLE; Schema: social; Owner: -
--

CREATE TABLE social.health (
    id bigint NOT NULL,
    name text NOT NULL,
    facility_type text NOT NULL,
    kephs_level smallint,
    ownership text,
    mfl_code text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT health_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT health_facility_type_check CHECK ((facility_type = ANY (ARRAY['hospital'::text, 'health_centre'::text, 'dispensary'::text, 'clinic'::text, 'pharmacy'::text]))),
    CONSTRAINT health_kephs_level_check CHECK (((kephs_level >= 1) AND (kephs_level <= 6))),
    CONSTRAINT health_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: health_id_seq; Type: SEQUENCE; Schema: social; Owner: -
--

ALTER TABLE social.health ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME social.health_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: markets; Type: TABLE; Schema: social; Owner: -
--

CREATE TABLE social.markets (
    id bigint NOT NULL,
    name text NOT NULL,
    market_type text,
    market_days text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT markets_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT markets_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: markets_id_seq; Type: SEQUENCE; Schema: social; Owner: -
--

ALTER TABLE social.markets ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME social.markets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: public_services; Type: TABLE; Schema: social; Owner: -
--

CREATE TABLE social.public_services (
    id bigint NOT NULL,
    name text NOT NULL,
    service_type text NOT NULL,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT public_services_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT public_services_service_type_check CHECK ((service_type = ANY (ARRAY['police'::text, 'fire_station'::text, 'huduma_centre'::text, 'court'::text, 'chiefs_office'::text, 'government_office'::text]))),
    CONSTRAINT public_services_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: public_services_id_seq; Type: SEQUENCE; Schema: social; Owner: -
--

ALTER TABLE social.public_services ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME social.public_services_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: soil_map_units; Type: TABLE; Schema: soils; Owner: -
--

CREATE TABLE soils.soil_map_units (
    id bigint NOT NULL,
    unit_code text,
    soil_type text,
    texture_class text,
    drainage_class text,
    depth_class text,
    fertility_class text,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT soil_map_units_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT soil_map_units_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: soil_map_units_id_seq; Type: SEQUENCE; Schema: soils; Owner: -
--

ALTER TABLE soils.soil_map_units ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME soils.soil_map_units_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: counties_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.counties_raw (
    county_code text,
    geometry public.geometry(Geometry,4326)
);


--
-- Name: county_tiles; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.county_tiles (
    county_code text,
    geom public.geometry
);


--
-- Name: health_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.health_raw (
    gid bigint,
    mfl_code text,
    name text,
    facility_type text,
    kephs_level double precision,
    ownership text,
    county_norm text,
    ward_norm text
);


--
-- Name: pilot_tiles; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.pilot_tiles (
    county_code text,
    geom public.geometry
);


--
-- Name: roads_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.roads_raw (
    gid bigint,
    osm_id text,
    name text,
    road_class text,
    geometry public.geometry(LineString,4326)
);


--
-- Name: schools_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.schools_raw (
    gid bigint,
    s_name text,
    s_level text,
    s_own text,
    geometry public.geometry(Point,4326)
);


--
-- Name: subcounties_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.subcounties_raw (
    name text,
    county_code text,
    geometry public.geometry(Geometry,4326)
);


--
-- Name: towers_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.towers_raw (
    gid bigint,
    op text,
    rad text,
    cid text,
    geometry public.geometry(Point,4326)
);


--
-- Name: wards_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.wards_raw (
    ward_code text,
    name text,
    county_code text,
    geometry public.geometry(Geometry,4326)
);


--
-- Name: water_areas_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.water_areas_raw (
    gid bigint,
    name text,
    fclass text,
    geometry public.geometry(Geometry,4326)
);


--
-- Name: water_points_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.water_points_raw (
    gid bigint,
    point_type text,
    is_functional boolean,
    operator text,
    geometry public.geometry(Point,4326)
);


--
-- Name: waterways_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.waterways_raw (
    gid bigint,
    name text,
    fclass text,
    geometry public.geometry(LineString,4326)
);


--
-- Name: wdpa_raw; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.wdpa_raw (
    gid bigint,
    p_name text,
    p_type text,
    p_auth text,
    geometry public.geometry(Geometry,4326)
);


--
-- Name: contours; Type: TABLE; Schema: terrain; Owner: -
--

CREATE TABLE terrain.contours (
    id bigint NOT NULL,
    elevation_m numeric NOT NULL,
    interval_m numeric,
    county_code text,
    geom public.geometry(MultiLineString,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT contours_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT contours_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: contours_id_seq; Type: SEQUENCE; Schema: terrain; Owner: -
--

ALTER TABLE terrain.contours ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME terrain.contours_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: watersheds; Type: TABLE; Schema: terrain; Owner: -
--

CREATE TABLE terrain.watersheds (
    id bigint NOT NULL,
    name text,
    basin_code text,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT watersheds_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT watersheds_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: watersheds_id_seq; Type: SEQUENCE; Schema: terrain; Owner: -
--

ALTER TABLE terrain.watersheds ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME terrain.watersheds_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: airports; Type: TABLE; Schema: transport; Owner: -
--

CREATE TABLE transport.airports (
    id bigint NOT NULL,
    name text NOT NULL,
    facility_type text NOT NULL,
    iata_code text,
    county_code text,
    geom public.geometry(Point,4326) NOT NULL,
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT airports_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT airports_facility_type_check CHECK ((facility_type = ANY (ARRAY['international'::text, 'domestic'::text, 'airstrip'::text]))),
    CONSTRAINT airports_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: airports_id_seq; Type: SEQUENCE; Schema: transport; Owner: -
--

ALTER TABLE transport.airports ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME transport.airports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: bridges; Type: TABLE; Schema: transport; Owner: -
--

CREATE TABLE transport.bridges (
    id bigint NOT NULL,
    name text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bridges_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT bridges_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: bridges_id_seq; Type: SEQUENCE; Schema: transport; Owner: -
--

ALTER TABLE transport.bridges ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME transport.bridges_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: bus_stops; Type: TABLE; Schema: transport; Owner: -
--

CREATE TABLE transport.bus_stops (
    id bigint NOT NULL,
    name text,
    stop_type text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bus_stops_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT bus_stops_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: bus_stops_id_seq; Type: SEQUENCE; Schema: transport; Owner: -
--

ALTER TABLE transport.bus_stops ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME transport.bus_stops_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ports; Type: TABLE; Schema: transport; Owner: -
--

CREATE TABLE transport.ports (
    id bigint NOT NULL,
    name text NOT NULL,
    port_type text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ports_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT ports_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: ports_id_seq; Type: SEQUENCE; Schema: transport; Owner: -
--

ALTER TABLE transport.ports ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME transport.ports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: railways; Type: TABLE; Schema: transport; Owner: -
--

CREATE TABLE transport.railways (
    id bigint NOT NULL,
    name text,
    rail_type text,
    county_code text,
    geom public.geometry(MultiLineString,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT railways_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT railways_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: railways_id_seq; Type: SEQUENCE; Schema: transport; Owner: -
--

ALTER TABLE transport.railways ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME transport.railways_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: roads; Type: TABLE; Schema: transport; Owner: -
--

CREATE TABLE transport.roads (
    id bigint NOT NULL,
    osm_id bigint,
    name text,
    road_class text NOT NULL,
    surface text,
    county_code text,
    geom public.geometry(MultiLineString,4326) NOT NULL,
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT roads_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT roads_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: roads_id_seq; Type: SEQUENCE; Schema: transport; Owner: -
--

ALTER TABLE transport.roads ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME transport.roads_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: audit_log; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.audit_log (
    audit_id bigint NOT NULL,
    user_id uuid,
    action text NOT NULL,
    entity text,
    entity_id text,
    detail jsonb,
    ip_address inet,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_log_audit_id_seq; Type: SEQUENCE; Schema: users; Owner: -
--

ALTER TABLE users.audit_log ALTER COLUMN audit_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME users.audit_log_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: permissions; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.permissions (
    permission_id integer NOT NULL,
    code text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: permissions_permission_id_seq; Type: SEQUENCE; Schema: users; Owner: -
--

ALTER TABLE users.permissions ALTER COLUMN permission_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME users.permissions_permission_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: role_permissions; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.role_permissions (
    role_id integer NOT NULL,
    permission_id integer NOT NULL
);


--
-- Name: roles; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.roles (
    role_id integer NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: roles_role_id_seq; Type: SEQUENCE; Schema: users; Owner: -
--

ALTER TABLE users.roles ALTER COLUMN role_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME users.roles_role_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: user_roles; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.user_roles (
    user_id uuid NOT NULL,
    role_id integer NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: users; Owner: -
--

CREATE TABLE users.users (
    user_id uuid DEFAULT gen_random_uuid() NOT NULL,
    email text NOT NULL,
    full_name text,
    password_hash text,
    company_id uuid,
    is_active boolean DEFAULT true NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dams; Type: TABLE; Schema: utilities; Owner: -
--

CREATE TABLE utilities.dams (
    id bigint NOT NULL,
    name text,
    purpose text,
    county_code text,
    geom public.geometry(MultiPolygon,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT dams_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT dams_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: dams_id_seq; Type: SEQUENCE; Schema: utilities; Owner: -
--

ALTER TABLE utilities.dams ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME utilities.dams_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: power_facilities; Type: TABLE; Schema: utilities; Owner: -
--

CREATE TABLE utilities.power_facilities (
    id bigint NOT NULL,
    facility_type text NOT NULL,
    name text,
    capacity text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT power_facilities_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT power_facilities_facility_type_check CHECK ((facility_type = ANY (ARRAY['substation'::text, 'transformer'::text, 'power_plant'::text]))),
    CONSTRAINT power_facilities_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: power_facilities_id_seq; Type: SEQUENCE; Schema: utilities; Owner: -
--

ALTER TABLE utilities.power_facilities ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME utilities.power_facilities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: power_lines; Type: TABLE; Schema: utilities; Owner: -
--

CREATE TABLE utilities.power_lines (
    id bigint NOT NULL,
    line_type text NOT NULL,
    voltage_kv numeric,
    operator text,
    county_code text,
    geom public.geometry(MultiLineString,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT power_lines_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT power_lines_line_type_check CHECK ((line_type = ANY (ARRAY['transmission'::text, 'distribution'::text]))),
    CONSTRAINT power_lines_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: power_lines_id_seq; Type: SEQUENCE; Schema: utilities; Owner: -
--

ALTER TABLE utilities.power_lines ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME utilities.power_lines_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: sewer_lines; Type: TABLE; Schema: utilities; Owner: -
--

CREATE TABLE utilities.sewer_lines (
    id bigint NOT NULL,
    operator text,
    county_code text,
    geom public.geometry(MultiLineString,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT sewer_lines_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT sewer_lines_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: sewer_lines_id_seq; Type: SEQUENCE; Schema: utilities; Owner: -
--

ALTER TABLE utilities.sewer_lines ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME utilities.sewer_lines_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: waste_sites; Type: TABLE; Schema: utilities; Owner: -
--

CREATE TABLE utilities.waste_sites (
    id bigint NOT NULL,
    site_type text NOT NULL,
    name text,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT waste_sites_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT waste_sites_site_type_check CHECK ((site_type = ANY (ARRAY['dumpsite'::text, 'landfill'::text, 'transfer_station'::text]))),
    CONSTRAINT waste_sites_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: waste_sites_id_seq; Type: SEQUENCE; Schema: utilities; Owner: -
--

ALTER TABLE utilities.waste_sites ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME utilities.waste_sites_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: water_lines; Type: TABLE; Schema: utilities; Owner: -
--

CREATE TABLE utilities.water_lines (
    id bigint NOT NULL,
    name text,
    operator text,
    county_code text,
    geom public.geometry(MultiLineString,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT water_lines_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT water_lines_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: water_lines_id_seq; Type: SEQUENCE; Schema: utilities; Owner: -
--

ALTER TABLE utilities.water_lines ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME utilities.water_lines_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: water_points; Type: TABLE; Schema: utilities; Owner: -
--

CREATE TABLE utilities.water_points (
    id bigint NOT NULL,
    point_type text NOT NULL,
    name text,
    operator text,
    is_functional boolean,
    county_code text,
    geom public.geometry(Point,4326),
    source_id integer,
    source_date date,
    confidence smallint,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT water_points_confidence_check CHECK (((confidence >= 1) AND (confidence <= 5))),
    CONSTRAINT water_points_point_type_check CHECK ((point_type = ANY (ARRAY['borehole'::text, 'spring'::text, 'water_kiosk'::text, 'treatment_plant'::text, 'storage_tank'::text, 'well'::text, 'other'::text]))),
    CONSTRAINT water_points_status_check CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text, 'pending_review'::text, 'rejected'::text])))
);


--
-- Name: water_points_id_seq; Type: SEQUENCE; Schema: utilities; Owner: -
--

ALTER TABLE utilities.water_points ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME utilities.water_points_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: constituencies constituencies_constituency_code_key; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.constituencies
    ADD CONSTRAINT constituencies_constituency_code_key UNIQUE (constituency_code);


--
-- Name: constituencies constituencies_pkey; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.constituencies
    ADD CONSTRAINT constituencies_pkey PRIMARY KEY (id);


--
-- Name: counties counties_county_code_key; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.counties
    ADD CONSTRAINT counties_county_code_key UNIQUE (county_code);


--
-- Name: counties counties_pkey; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.counties
    ADD CONSTRAINT counties_pkey PRIMARY KEY (id);


--
-- Name: country country_pkey; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.country
    ADD CONSTRAINT country_pkey PRIMARY KEY (id);


--
-- Name: locations locations_pkey; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.locations
    ADD CONSTRAINT locations_pkey PRIMARY KEY (id);


--
-- Name: subcounties subcounties_pkey; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.subcounties
    ADD CONSTRAINT subcounties_pkey PRIMARY KEY (id);


--
-- Name: subcounties subcounties_subcounty_code_key; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.subcounties
    ADD CONSTRAINT subcounties_subcounty_code_key UNIQUE (subcounty_code);


--
-- Name: sublocations sublocations_pkey; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.sublocations
    ADD CONSTRAINT sublocations_pkey PRIMARY KEY (id);


--
-- Name: wards wards_pkey; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.wards
    ADD CONSTRAINT wards_pkey PRIMARY KEY (id);


--
-- Name: wards wards_ward_code_key; Type: CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.wards
    ADD CONSTRAINT wards_ward_code_key UNIQUE (ward_code);


--
-- Name: accessibility accessibility_pkey; Type: CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.accessibility
    ADD CONSTRAINT accessibility_pkey PRIMARY KEY (id);


--
-- Name: enrichment_runs enrichment_runs_pkey; Type: CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.enrichment_runs
    ADD CONSTRAINT enrichment_runs_pkey PRIMARY KEY (run_id);


--
-- Name: parcel_intelligence parcel_intelligence_parcel_id_version_key; Type: CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.parcel_intelligence
    ADD CONSTRAINT parcel_intelligence_parcel_id_version_key UNIQUE (parcel_id, version);


--
-- Name: parcel_intelligence parcel_intelligence_pkey; Type: CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.parcel_intelligence
    ADD CONSTRAINT parcel_intelligence_pkey PRIMARY KEY (intel_id);


--
-- Name: suitability_scores suitability_scores_parcel_id_version_key; Type: CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.suitability_scores
    ADD CONSTRAINT suitability_scores_parcel_id_version_key UNIQUE (parcel_id, version);


--
-- Name: suitability_scores suitability_scores_pkey; Type: CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.suitability_scores
    ADD CONSTRAINT suitability_scores_pkey PRIMARY KEY (score_id);


--
-- Name: api_keys api_keys_key_hash_key; Type: CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.api_keys
    ADD CONSTRAINT api_keys_key_hash_key UNIQUE (key_hash);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (api_key_id);


--
-- Name: api_usage api_usage_pkey; Type: CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.api_usage
    ADD CONSTRAINT api_usage_pkey PRIMARY KEY (usage_id);


--
-- Name: branding branding_company_id_key; Type: CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.branding
    ADD CONSTRAINT branding_company_id_key UNIQUE (company_id);


--
-- Name: branding branding_pkey; Type: CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.branding
    ADD CONSTRAINT branding_pkey PRIMARY KEY (branding_id);


--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (company_id);


--
-- Name: companies companies_slug_key; Type: CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.companies
    ADD CONSTRAINT companies_slug_key UNIQUE (slug);


--
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (subscription_id);


--
-- Name: stations stations_pkey; Type: CONSTRAINT; Schema: climate; Owner: -
--

ALTER TABLE ONLY climate.stations
    ADD CONSTRAINT stations_pkey PRIMARY KEY (id);


--
-- Name: stations stations_station_code_key; Type: CONSTRAINT; Schema: climate; Owner: -
--

ALTER TABLE ONLY climate.stations
    ADD CONSTRAINT stations_station_code_key UNIQUE (station_code);


--
-- Name: zonal_stats zonal_stats_admin_level_admin_code_variable_period_stat_ver_key; Type: CONSTRAINT; Schema: climate; Owner: -
--

ALTER TABLE ONLY climate.zonal_stats
    ADD CONSTRAINT zonal_stats_admin_level_admin_code_variable_period_stat_ver_key UNIQUE (admin_level, admin_code, variable, period, stat, version);


--
-- Name: zonal_stats zonal_stats_pkey; Type: CONSTRAINT; Schema: climate; Owner: -
--

ALTER TABLE ONLY climate.zonal_stats
    ADD CONSTRAINT zonal_stats_pkey PRIMARY KEY (id);


--
-- Name: coverage coverage_pkey; Type: CONSTRAINT; Schema: connectivity; Owner: -
--

ALTER TABLE ONLY connectivity.coverage
    ADD CONSTRAINT coverage_pkey PRIMARY KEY (id);


--
-- Name: fiber fiber_pkey; Type: CONSTRAINT; Schema: connectivity; Owner: -
--

ALTER TABLE ONLY connectivity.fiber
    ADD CONSTRAINT fiber_pkey PRIMARY KEY (id);


--
-- Name: towers towers_pkey; Type: CONSTRAINT; Schema: connectivity; Owner: -
--

ALTER TABLE ONLY connectivity.towers
    ADD CONSTRAINT towers_pkey PRIMARY KEY (id);


--
-- Name: nightlights_stats nightlights_stats_admin_level_admin_code_period_version_key; Type: CONSTRAINT; Schema: demographics; Owner: -
--

ALTER TABLE ONLY demographics.nightlights_stats
    ADD CONSTRAINT nightlights_stats_admin_level_admin_code_period_version_key UNIQUE (admin_level, admin_code, period, version);


--
-- Name: nightlights_stats nightlights_stats_pkey; Type: CONSTRAINT; Schema: demographics; Owner: -
--

ALTER TABLE ONLY demographics.nightlights_stats
    ADD CONSTRAINT nightlights_stats_pkey PRIMARY KEY (id);


--
-- Name: population_stats population_stats_admin_level_admin_code_year_version_key; Type: CONSTRAINT; Schema: demographics; Owner: -
--

ALTER TABLE ONLY demographics.population_stats
    ADD CONSTRAINT population_stats_admin_level_admin_code_year_version_key UNIQUE (admin_level, admin_code, year, version);


--
-- Name: population_stats population_stats_pkey; Type: CONSTRAINT; Schema: demographics; Owner: -
--

ALTER TABLE ONLY demographics.population_stats
    ADD CONSTRAINT population_stats_pkey PRIMARY KEY (id);


--
-- Name: forests forests_pkey; Type: CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.forests
    ADD CONSTRAINT forests_pkey PRIMARY KEY (id);


--
-- Name: protected_areas protected_areas_pkey; Type: CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.protected_areas
    ADD CONSTRAINT protected_areas_pkey PRIMARY KEY (id);


--
-- Name: riparian_buffers riparian_buffers_pkey; Type: CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.riparian_buffers
    ADD CONSTRAINT riparian_buffers_pkey PRIMARY KEY (id);


--
-- Name: rivers rivers_pkey; Type: CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.rivers
    ADD CONSTRAINT rivers_pkey PRIMARY KEY (id);


--
-- Name: waterbodies waterbodies_pkey; Type: CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.waterbodies
    ADD CONSTRAINT waterbodies_pkey PRIMARY KEY (id);


--
-- Name: wetlands wetlands_pkey; Type: CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.wetlands
    ADD CONSTRAINT wetlands_pkey PRIMARY KEY (id);


--
-- Name: drone_missions drone_missions_pkey; Type: CONSTRAINT; Schema: imagery; Owner: -
--

ALTER TABLE ONLY imagery.drone_missions
    ADD CONSTRAINT drone_missions_pkey PRIMARY KEY (mission_id);


--
-- Name: orthophotos orthophotos_pkey; Type: CONSTRAINT; Schema: imagery; Owner: -
--

ALTER TABLE ONLY imagery.orthophotos
    ADD CONSTRAINT orthophotos_pkey PRIMARY KEY (id);


--
-- Name: scenes scenes_pkey; Type: CONSTRAINT; Schema: imagery; Owner: -
--

ALTER TABLE ONLY imagery.scenes
    ADD CONSTRAINT scenes_pkey PRIMARY KEY (id);


--
-- Name: scenes scenes_scene_id_key; Type: CONSTRAINT; Schema: imagery; Owner: -
--

ALTER TABLE ONLY imagery.scenes
    ADD CONSTRAINT scenes_scene_id_key UNIQUE (scene_id);


--
-- Name: land_use land_use_pkey; Type: CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.land_use
    ADD CONSTRAINT land_use_pkey PRIMARY KEY (id);


--
-- Name: parcel_documents parcel_documents_pkey; Type: CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcel_documents
    ADD CONSTRAINT parcel_documents_pkey PRIMARY KEY (document_id);


--
-- Name: parcel_history parcel_history_pkey; Type: CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcel_history
    ADD CONSTRAINT parcel_history_pkey PRIMARY KEY (history_id);


--
-- Name: parcel_images parcel_images_pkey; Type: CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcel_images
    ADD CONSTRAINT parcel_images_pkey PRIMARY KEY (image_id);


--
-- Name: parcels parcels_company_id_parcel_ref_version_key; Type: CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcels
    ADD CONSTRAINT parcels_company_id_parcel_ref_version_key UNIQUE (company_id, parcel_ref, version);


--
-- Name: parcels parcels_pkey; Type: CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcels
    ADD CONSTRAINT parcels_pkey PRIMARY KEY (parcel_id);


--
-- Name: valuations valuations_pkey; Type: CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.valuations
    ADD CONSTRAINT valuations_pkey PRIMARY KEY (valuation_id);


--
-- Name: zoning zoning_pkey; Type: CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.zoning
    ADD CONSTRAINT zoning_pkey PRIMARY KEY (id);


--
-- Name: api_logs api_logs_pkey; Type: CONSTRAINT; Schema: logs; Owner: -
--

ALTER TABLE ONLY logs.api_logs
    ADD CONSTRAINT api_logs_pkey PRIMARY KEY (log_id);


--
-- Name: downloads downloads_pkey; Type: CONSTRAINT; Schema: logs; Owner: -
--

ALTER TABLE ONLY logs.downloads
    ADD CONSTRAINT downloads_pkey PRIMARY KEY (download_id);


--
-- Name: error_logs error_logs_pkey; Type: CONSTRAINT; Schema: logs; Owner: -
--

ALTER TABLE ONLY logs.error_logs
    ADD CONSTRAINT error_logs_pkey PRIMARY KEY (error_id);


--
-- Name: user_activity user_activity_pkey; Type: CONSTRAINT; Schema: logs; Owner: -
--

ALTER TABLE ONLY logs.user_activity
    ADD CONSTRAINT user_activity_pkey PRIMARY KEY (activity_id);


--
-- Name: datasets datasets_code_key; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.datasets
    ADD CONSTRAINT datasets_code_key UNIQUE (code);


--
-- Name: datasets datasets_pkey; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.datasets
    ADD CONSTRAINT datasets_pkey PRIMARY KEY (dataset_id);


--
-- Name: etl_runs etl_runs_pkey; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.etl_runs
    ADD CONSTRAINT etl_runs_pkey PRIMARY KEY (run_id);


--
-- Name: licenses licenses_code_key; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.licenses
    ADD CONSTRAINT licenses_code_key UNIQUE (code);


--
-- Name: licenses licenses_pkey; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.licenses
    ADD CONSTRAINT licenses_pkey PRIMARY KEY (license_id);


--
-- Name: quality_scores quality_scores_pkey; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.quality_scores
    ADD CONSTRAINT quality_scores_pkey PRIMARY KEY (quality_id);


--
-- Name: raster_catalog raster_catalog_pkey; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.raster_catalog
    ADD CONSTRAINT raster_catalog_pkey PRIMARY KEY (raster_id);


--
-- Name: refresh_logs refresh_logs_pkey; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.refresh_logs
    ADD CONSTRAINT refresh_logs_pkey PRIMARY KEY (refresh_id);


--
-- Name: sources sources_name_key; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.sources
    ADD CONSTRAINT sources_name_key UNIQUE (name);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (source_id);


--
-- Name: validation_results validation_results_pkey; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.validation_results
    ADD CONSTRAINT validation_results_pkey PRIMARY KEY (result_id);


--
-- Name: validation_rules validation_rules_pkey; Type: CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.validation_rules
    ADD CONSTRAINT validation_rules_pkey PRIMARY KEY (rule_id);


--
-- Name: reports reports_pkey; Type: CONSTRAINT; Schema: reports; Owner: -
--

ALTER TABLE ONLY reports.reports
    ADD CONSTRAINT reports_pkey PRIMARY KEY (report_id);


--
-- Name: education education_pkey; Type: CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.education
    ADD CONSTRAINT education_pkey PRIMARY KEY (id);


--
-- Name: financial financial_pkey; Type: CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.financial
    ADD CONSTRAINT financial_pkey PRIMARY KEY (id);


--
-- Name: health health_pkey; Type: CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.health
    ADD CONSTRAINT health_pkey PRIMARY KEY (id);


--
-- Name: markets markets_pkey; Type: CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.markets
    ADD CONSTRAINT markets_pkey PRIMARY KEY (id);


--
-- Name: public_services public_services_pkey; Type: CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.public_services
    ADD CONSTRAINT public_services_pkey PRIMARY KEY (id);


--
-- Name: soil_map_units soil_map_units_pkey; Type: CONSTRAINT; Schema: soils; Owner: -
--

ALTER TABLE ONLY soils.soil_map_units
    ADD CONSTRAINT soil_map_units_pkey PRIMARY KEY (id);


--
-- Name: contours contours_pkey; Type: CONSTRAINT; Schema: terrain; Owner: -
--

ALTER TABLE ONLY terrain.contours
    ADD CONSTRAINT contours_pkey PRIMARY KEY (id);


--
-- Name: watersheds watersheds_pkey; Type: CONSTRAINT; Schema: terrain; Owner: -
--

ALTER TABLE ONLY terrain.watersheds
    ADD CONSTRAINT watersheds_pkey PRIMARY KEY (id);


--
-- Name: airports airports_pkey; Type: CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.airports
    ADD CONSTRAINT airports_pkey PRIMARY KEY (id);


--
-- Name: bridges bridges_pkey; Type: CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.bridges
    ADD CONSTRAINT bridges_pkey PRIMARY KEY (id);


--
-- Name: bus_stops bus_stops_pkey; Type: CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.bus_stops
    ADD CONSTRAINT bus_stops_pkey PRIMARY KEY (id);


--
-- Name: ports ports_pkey; Type: CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.ports
    ADD CONSTRAINT ports_pkey PRIMARY KEY (id);


--
-- Name: railways railways_pkey; Type: CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.railways
    ADD CONSTRAINT railways_pkey PRIMARY KEY (id);


--
-- Name: roads roads_pkey; Type: CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.roads
    ADD CONSTRAINT roads_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (audit_id);


--
-- Name: permissions permissions_code_key; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.permissions
    ADD CONSTRAINT permissions_code_key UNIQUE (code);


--
-- Name: permissions permissions_pkey; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (permission_id);


--
-- Name: role_permissions role_permissions_pkey; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (role_id, permission_id);


--
-- Name: roles roles_code_key; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.roles
    ADD CONSTRAINT roles_code_key UNIQUE (code);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (role_id);


--
-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: dams dams_pkey; Type: CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.dams
    ADD CONSTRAINT dams_pkey PRIMARY KEY (id);


--
-- Name: power_facilities power_facilities_pkey; Type: CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.power_facilities
    ADD CONSTRAINT power_facilities_pkey PRIMARY KEY (id);


--
-- Name: power_lines power_lines_pkey; Type: CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.power_lines
    ADD CONSTRAINT power_lines_pkey PRIMARY KEY (id);


--
-- Name: sewer_lines sewer_lines_pkey; Type: CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.sewer_lines
    ADD CONSTRAINT sewer_lines_pkey PRIMARY KEY (id);


--
-- Name: waste_sites waste_sites_pkey; Type: CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.waste_sites
    ADD CONSTRAINT waste_sites_pkey PRIMARY KEY (id);


--
-- Name: water_lines water_lines_pkey; Type: CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.water_lines
    ADD CONSTRAINT water_lines_pkey PRIMARY KEY (id);


--
-- Name: water_points water_points_pkey; Type: CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.water_points
    ADD CONSTRAINT water_points_pkey PRIMARY KEY (id);


--
-- Name: constituencies_county_code_idx; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX constituencies_county_code_idx ON admin.constituencies USING btree (county_code);


--
-- Name: constituencies_geom_gix; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX constituencies_geom_gix ON admin.constituencies USING gist (geom);


--
-- Name: counties_geom_gix; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX counties_geom_gix ON admin.counties USING gist (geom);


--
-- Name: country_geom_gix; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX country_geom_gix ON admin.country USING gist (geom);


--
-- Name: locations_county_code_idx; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX locations_county_code_idx ON admin.locations USING btree (county_code);


--
-- Name: locations_geom_gix; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX locations_geom_gix ON admin.locations USING gist (geom);


--
-- Name: subcounties_county_code_idx; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX subcounties_county_code_idx ON admin.subcounties USING btree (county_code);


--
-- Name: subcounties_geom_gix; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX subcounties_geom_gix ON admin.subcounties USING gist (geom);


--
-- Name: sublocations_county_code_idx; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX sublocations_county_code_idx ON admin.sublocations USING btree (county_code);


--
-- Name: sublocations_geom_gix; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX sublocations_geom_gix ON admin.sublocations USING gist (geom);


--
-- Name: wards_county_code_idx; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX wards_county_code_idx ON admin.wards USING btree (county_code);


--
-- Name: wards_geom_gix; Type: INDEX; Schema: admin; Owner: -
--

CREATE INDEX wards_geom_gix ON admin.wards USING gist (geom);


--
-- Name: idx_parcel_intel_flood; Type: INDEX; Schema: analytics; Owner: -
--

CREATE INDEX idx_parcel_intel_flood ON analytics.parcel_intelligence USING btree (flood_risk_class) WHERE (status = 'active'::text);


--
-- Name: idx_parcel_intel_parcel_active; Type: INDEX; Schema: analytics; Owner: -
--

CREATE INDEX idx_parcel_intel_parcel_active ON analytics.parcel_intelligence USING btree (parcel_id) WHERE (status = 'active'::text);


--
-- Name: idx_parcel_intel_run; Type: INDEX; Schema: analytics; Owner: -
--

CREATE INDEX idx_parcel_intel_run ON analytics.parcel_intelligence USING btree (run_id);


--
-- Name: intel_parcel_idx; Type: INDEX; Schema: analytics; Owner: -
--

CREATE INDEX intel_parcel_idx ON analytics.parcel_intelligence USING btree (parcel_id);


--
-- Name: scores_parcel_idx; Type: INDEX; Schema: analytics; Owner: -
--

CREATE INDEX scores_parcel_idx ON analytics.suitability_scores USING btree (parcel_id);


--
-- Name: companies_county_code_idx; Type: INDEX; Schema: clients; Owner: -
--

CREATE INDEX companies_county_code_idx ON clients.companies USING btree (county_code);


--
-- Name: stations_county_code_idx; Type: INDEX; Schema: climate; Owner: -
--

CREATE INDEX stations_county_code_idx ON climate.stations USING btree (county_code);


--
-- Name: stations_geom_gix; Type: INDEX; Schema: climate; Owner: -
--

CREATE INDEX stations_geom_gix ON climate.stations USING gist (geom);


--
-- Name: coverage_county_code_idx; Type: INDEX; Schema: connectivity; Owner: -
--

CREATE INDEX coverage_county_code_idx ON connectivity.coverage USING btree (county_code);


--
-- Name: coverage_geom_gix; Type: INDEX; Schema: connectivity; Owner: -
--

CREATE INDEX coverage_geom_gix ON connectivity.coverage USING gist (geom);


--
-- Name: fiber_county_code_idx; Type: INDEX; Schema: connectivity; Owner: -
--

CREATE INDEX fiber_county_code_idx ON connectivity.fiber USING btree (county_code);


--
-- Name: fiber_geom_gix; Type: INDEX; Schema: connectivity; Owner: -
--

CREATE INDEX fiber_geom_gix ON connectivity.fiber USING gist (geom);


--
-- Name: idx_coverage_admin_code; Type: INDEX; Schema: connectivity; Owner: -
--

CREATE INDEX idx_coverage_admin_code ON connectivity.coverage USING btree (admin_code);


--
-- Name: idx_coverage_tech_operator; Type: INDEX; Schema: connectivity; Owner: -
--

CREATE INDEX idx_coverage_tech_operator ON connectivity.coverage USING btree (technology, operator);


--
-- Name: towers_county_code_idx; Type: INDEX; Schema: connectivity; Owner: -
--

CREATE INDEX towers_county_code_idx ON connectivity.towers USING btree (county_code);


--
-- Name: towers_geom_gix; Type: INDEX; Schema: connectivity; Owner: -
--

CREATE INDEX towers_geom_gix ON connectivity.towers USING gist (geom);


--
-- Name: idx_nightlights_trend; Type: INDEX; Schema: demographics; Owner: -
--

CREATE INDEX idx_nightlights_trend ON demographics.nightlights_stats USING btree (admin_level, trend_radiance_yr DESC);


--
-- Name: forests_county_code_idx; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX forests_county_code_idx ON environment.forests USING btree (county_code);


--
-- Name: forests_geom_gix; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX forests_geom_gix ON environment.forests USING gist (geom);


--
-- Name: protected_areas_county_code_idx; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX protected_areas_county_code_idx ON environment.protected_areas USING btree (county_code);


--
-- Name: protected_areas_geom_gix; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX protected_areas_geom_gix ON environment.protected_areas USING gist (geom);


--
-- Name: riparian_buffers_geom_gix; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX riparian_buffers_geom_gix ON environment.riparian_buffers USING gist (geom);


--
-- Name: rivers_county_code_idx; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX rivers_county_code_idx ON environment.rivers USING btree (county_code);


--
-- Name: rivers_geom_gix; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX rivers_geom_gix ON environment.rivers USING gist (geom);


--
-- Name: waterbodies_county_code_idx; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX waterbodies_county_code_idx ON environment.waterbodies USING btree (county_code);


--
-- Name: waterbodies_geom_gix; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX waterbodies_geom_gix ON environment.waterbodies USING gist (geom);


--
-- Name: wetlands_county_code_idx; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX wetlands_county_code_idx ON environment.wetlands USING btree (county_code);


--
-- Name: wetlands_geom_gix; Type: INDEX; Schema: environment; Owner: -
--

CREATE INDEX wetlands_geom_gix ON environment.wetlands USING gist (geom);


--
-- Name: drone_missions_footprint_gix; Type: INDEX; Schema: imagery; Owner: -
--

CREATE INDEX drone_missions_footprint_gix ON imagery.drone_missions USING gist (footprint);


--
-- Name: orthophotos_footprint_gix; Type: INDEX; Schema: imagery; Owner: -
--

CREATE INDEX orthophotos_footprint_gix ON imagery.orthophotos USING gist (footprint);


--
-- Name: scenes_footprint_gix; Type: INDEX; Schema: imagery; Owner: -
--

CREATE INDEX scenes_footprint_gix ON imagery.scenes USING gist (footprint);


--
-- Name: land_use_county_code_idx; Type: INDEX; Schema: land; Owner: -
--

CREATE INDEX land_use_county_code_idx ON land.land_use USING btree (county_code);


--
-- Name: land_use_geom_gix; Type: INDEX; Schema: land; Owner: -
--

CREATE INDEX land_use_geom_gix ON land.land_use USING gist (geom);


--
-- Name: parcels_company_idx; Type: INDEX; Schema: land; Owner: -
--

CREATE INDEX parcels_company_idx ON land.parcels USING btree (company_id);


--
-- Name: parcels_county_code_idx; Type: INDEX; Schema: land; Owner: -
--

CREATE INDEX parcels_county_code_idx ON land.parcels USING btree (county_code);


--
-- Name: parcels_geom_gix; Type: INDEX; Schema: land; Owner: -
--

CREATE INDEX parcels_geom_gix ON land.parcels USING gist (geom);


--
-- Name: parcels_listing_idx; Type: INDEX; Schema: land; Owner: -
--

CREATE INDEX parcels_listing_idx ON land.parcels USING btree (listing_status) WHERE (status = 'active'::text);


--
-- Name: zoning_county_code_idx; Type: INDEX; Schema: land; Owner: -
--

CREATE INDEX zoning_county_code_idx ON land.zoning USING btree (county_code);


--
-- Name: zoning_geom_gix; Type: INDEX; Schema: land; Owner: -
--

CREATE INDEX zoning_geom_gix ON land.zoning USING gist (geom);


--
-- Name: api_logs_time_idx; Type: INDEX; Schema: logs; Owner: -
--

CREATE INDEX api_logs_time_idx ON logs.api_logs USING btree (occurred_at);


--
-- Name: raster_catalog_bbox_gix; Type: INDEX; Schema: metadata; Owner: -
--

CREATE INDEX raster_catalog_bbox_gix ON metadata.raster_catalog USING gist (bbox);


--
-- Name: reports_parcel_idx; Type: INDEX; Schema: reports; Owner: -
--

CREATE INDEX reports_parcel_idx ON reports.reports USING btree (parcel_id);


--
-- Name: education_county_code_idx; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX education_county_code_idx ON social.education USING btree (county_code);


--
-- Name: education_geom_gix; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX education_geom_gix ON social.education USING gist (geom);


--
-- Name: financial_county_code_idx; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX financial_county_code_idx ON social.financial USING btree (county_code);


--
-- Name: financial_geom_gix; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX financial_geom_gix ON social.financial USING gist (geom);


--
-- Name: health_county_code_idx; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX health_county_code_idx ON social.health USING btree (county_code);


--
-- Name: health_geom_gix; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX health_geom_gix ON social.health USING gist (geom);


--
-- Name: markets_county_code_idx; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX markets_county_code_idx ON social.markets USING btree (county_code);


--
-- Name: markets_geom_gix; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX markets_geom_gix ON social.markets USING gist (geom);


--
-- Name: public_services_county_code_idx; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX public_services_county_code_idx ON social.public_services USING btree (county_code);


--
-- Name: public_services_geom_gix; Type: INDEX; Schema: social; Owner: -
--

CREATE INDEX public_services_geom_gix ON social.public_services USING gist (geom);


--
-- Name: soil_map_units_county_code_idx; Type: INDEX; Schema: soils; Owner: -
--

CREATE INDEX soil_map_units_county_code_idx ON soils.soil_map_units USING btree (county_code);


--
-- Name: soil_map_units_geom_gix; Type: INDEX; Schema: soils; Owner: -
--

CREATE INDEX soil_map_units_geom_gix ON soils.soil_map_units USING gist (geom);


--
-- Name: county_tiles_geom_idx; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX county_tiles_geom_idx ON staging.county_tiles USING gist (geom);


--
-- Name: idx_counties_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_counties_raw_geometry ON staging.counties_raw USING gist (geometry);


--
-- Name: idx_roads_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_roads_raw_geometry ON staging.roads_raw USING gist (geometry);


--
-- Name: idx_schools_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_schools_raw_geometry ON staging.schools_raw USING gist (geometry);


--
-- Name: idx_subcounties_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_subcounties_raw_geometry ON staging.subcounties_raw USING gist (geometry);


--
-- Name: idx_towers_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_towers_raw_geometry ON staging.towers_raw USING gist (geometry);


--
-- Name: idx_wards_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_wards_raw_geometry ON staging.wards_raw USING gist (geometry);


--
-- Name: idx_water_areas_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_water_areas_raw_geometry ON staging.water_areas_raw USING gist (geometry);


--
-- Name: idx_water_points_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_water_points_raw_geometry ON staging.water_points_raw USING gist (geometry);


--
-- Name: idx_waterways_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_waterways_raw_geometry ON staging.waterways_raw USING gist (geometry);


--
-- Name: idx_wdpa_raw_geometry; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX idx_wdpa_raw_geometry ON staging.wdpa_raw USING gist (geometry);


--
-- Name: pilot_tiles_geom_idx; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX pilot_tiles_geom_idx ON staging.pilot_tiles USING gist (geom);


--
-- Name: roads_raw_geometry_idx; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX roads_raw_geometry_idx ON staging.roads_raw USING gist (geometry);


--
-- Name: schools_raw_geometry_idx; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX schools_raw_geometry_idx ON staging.schools_raw USING gist (geometry);


--
-- Name: towers_raw_geometry_idx; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX towers_raw_geometry_idx ON staging.towers_raw USING gist (geometry);


--
-- Name: water_areas_raw_geometry_idx; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX water_areas_raw_geometry_idx ON staging.water_areas_raw USING gist (geometry);


--
-- Name: water_points_raw_geometry_idx; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX water_points_raw_geometry_idx ON staging.water_points_raw USING gist (geometry);


--
-- Name: waterways_raw_geometry_idx; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX waterways_raw_geometry_idx ON staging.waterways_raw USING gist (geometry);


--
-- Name: wdpa_raw_geometry_idx; Type: INDEX; Schema: staging; Owner: -
--

CREATE INDEX wdpa_raw_geometry_idx ON staging.wdpa_raw USING gist (geometry);


--
-- Name: contours_county_code_idx; Type: INDEX; Schema: terrain; Owner: -
--

CREATE INDEX contours_county_code_idx ON terrain.contours USING btree (county_code);


--
-- Name: contours_geom_gix; Type: INDEX; Schema: terrain; Owner: -
--

CREATE INDEX contours_geom_gix ON terrain.contours USING gist (geom);


--
-- Name: watersheds_county_code_idx; Type: INDEX; Schema: terrain; Owner: -
--

CREATE INDEX watersheds_county_code_idx ON terrain.watersheds USING btree (county_code);


--
-- Name: watersheds_geom_gix; Type: INDEX; Schema: terrain; Owner: -
--

CREATE INDEX watersheds_geom_gix ON terrain.watersheds USING gist (geom);


--
-- Name: airports_county_code_idx; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX airports_county_code_idx ON transport.airports USING btree (county_code);


--
-- Name: airports_geom_gix; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX airports_geom_gix ON transport.airports USING gist (geom);


--
-- Name: bridges_county_code_idx; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX bridges_county_code_idx ON transport.bridges USING btree (county_code);


--
-- Name: bridges_geom_gix; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX bridges_geom_gix ON transport.bridges USING gist (geom);


--
-- Name: bus_stops_county_code_idx; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX bus_stops_county_code_idx ON transport.bus_stops USING btree (county_code);


--
-- Name: bus_stops_geom_gix; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX bus_stops_geom_gix ON transport.bus_stops USING gist (geom);


--
-- Name: ports_county_code_idx; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX ports_county_code_idx ON transport.ports USING btree (county_code);


--
-- Name: ports_geom_gix; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX ports_geom_gix ON transport.ports USING gist (geom);


--
-- Name: railways_county_code_idx; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX railways_county_code_idx ON transport.railways USING btree (county_code);


--
-- Name: railways_geom_gix; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX railways_geom_gix ON transport.railways USING gist (geom);


--
-- Name: roads_county_code_idx; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX roads_county_code_idx ON transport.roads USING btree (county_code);


--
-- Name: roads_geom_gix; Type: INDEX; Schema: transport; Owner: -
--

CREATE INDEX roads_geom_gix ON transport.roads USING gist (geom);


--
-- Name: audit_time_idx; Type: INDEX; Schema: users; Owner: -
--

CREATE INDEX audit_time_idx ON users.audit_log USING btree (occurred_at);


--
-- Name: dams_county_code_idx; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX dams_county_code_idx ON utilities.dams USING btree (county_code);


--
-- Name: dams_geom_gix; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX dams_geom_gix ON utilities.dams USING gist (geom);


--
-- Name: power_facilities_county_code_idx; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX power_facilities_county_code_idx ON utilities.power_facilities USING btree (county_code);


--
-- Name: power_facilities_geom_gix; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX power_facilities_geom_gix ON utilities.power_facilities USING gist (geom);


--
-- Name: power_lines_county_code_idx; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX power_lines_county_code_idx ON utilities.power_lines USING btree (county_code);


--
-- Name: power_lines_geom_gix; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX power_lines_geom_gix ON utilities.power_lines USING gist (geom);


--
-- Name: sewer_lines_county_code_idx; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX sewer_lines_county_code_idx ON utilities.sewer_lines USING btree (county_code);


--
-- Name: sewer_lines_geom_gix; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX sewer_lines_geom_gix ON utilities.sewer_lines USING gist (geom);


--
-- Name: waste_sites_county_code_idx; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX waste_sites_county_code_idx ON utilities.waste_sites USING btree (county_code);


--
-- Name: waste_sites_geom_gix; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX waste_sites_geom_gix ON utilities.waste_sites USING gist (geom);


--
-- Name: water_lines_county_code_idx; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX water_lines_county_code_idx ON utilities.water_lines USING btree (county_code);


--
-- Name: water_lines_geom_gix; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX water_lines_geom_gix ON utilities.water_lines USING gist (geom);


--
-- Name: water_points_county_code_idx; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX water_points_county_code_idx ON utilities.water_points USING btree (county_code);


--
-- Name: water_points_geom_gix; Type: INDEX; Schema: utilities; Owner: -
--

CREATE INDEX water_points_geom_gix ON utilities.water_points USING gist (geom);


--
-- Name: constituencies trg_set_updated_at; Type: TRIGGER; Schema: admin; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON admin.constituencies FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: counties trg_set_updated_at; Type: TRIGGER; Schema: admin; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON admin.counties FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: country trg_set_updated_at; Type: TRIGGER; Schema: admin; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON admin.country FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: locations trg_set_updated_at; Type: TRIGGER; Schema: admin; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON admin.locations FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: subcounties trg_set_updated_at; Type: TRIGGER; Schema: admin; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON admin.subcounties FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: sublocations trg_set_updated_at; Type: TRIGGER; Schema: admin; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON admin.sublocations FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: wards trg_set_updated_at; Type: TRIGGER; Schema: admin; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON admin.wards FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: accessibility trg_set_updated_at; Type: TRIGGER; Schema: analytics; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON analytics.accessibility FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: enrichment_runs trg_set_updated_at; Type: TRIGGER; Schema: analytics; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON analytics.enrichment_runs FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: parcel_intelligence trg_set_updated_at; Type: TRIGGER; Schema: analytics; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON analytics.parcel_intelligence FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: suitability_scores trg_set_updated_at; Type: TRIGGER; Schema: analytics; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON analytics.suitability_scores FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: api_keys trg_set_updated_at; Type: TRIGGER; Schema: clients; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON clients.api_keys FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: api_usage trg_set_updated_at; Type: TRIGGER; Schema: clients; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON clients.api_usage FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: branding trg_set_updated_at; Type: TRIGGER; Schema: clients; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON clients.branding FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: companies trg_set_updated_at; Type: TRIGGER; Schema: clients; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON clients.companies FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: subscriptions trg_set_updated_at; Type: TRIGGER; Schema: clients; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON clients.subscriptions FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: stations trg_set_updated_at; Type: TRIGGER; Schema: climate; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON climate.stations FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: zonal_stats trg_set_updated_at; Type: TRIGGER; Schema: climate; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON climate.zonal_stats FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: coverage trg_set_updated_at; Type: TRIGGER; Schema: connectivity; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON connectivity.coverage FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: fiber trg_set_updated_at; Type: TRIGGER; Schema: connectivity; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON connectivity.fiber FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: towers trg_set_updated_at; Type: TRIGGER; Schema: connectivity; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON connectivity.towers FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: nightlights_stats trg_set_updated_at; Type: TRIGGER; Schema: demographics; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON demographics.nightlights_stats FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: population_stats trg_set_updated_at; Type: TRIGGER; Schema: demographics; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON demographics.population_stats FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: forests trg_set_updated_at; Type: TRIGGER; Schema: environment; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON environment.forests FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: protected_areas trg_set_updated_at; Type: TRIGGER; Schema: environment; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON environment.protected_areas FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: riparian_buffers trg_set_updated_at; Type: TRIGGER; Schema: environment; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON environment.riparian_buffers FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: rivers trg_set_updated_at; Type: TRIGGER; Schema: environment; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON environment.rivers FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: waterbodies trg_set_updated_at; Type: TRIGGER; Schema: environment; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON environment.waterbodies FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: wetlands trg_set_updated_at; Type: TRIGGER; Schema: environment; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON environment.wetlands FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: drone_missions trg_set_updated_at; Type: TRIGGER; Schema: imagery; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON imagery.drone_missions FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: orthophotos trg_set_updated_at; Type: TRIGGER; Schema: imagery; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON imagery.orthophotos FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: scenes trg_set_updated_at; Type: TRIGGER; Schema: imagery; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON imagery.scenes FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: parcels trg_log_listing_status; Type: TRIGGER; Schema: land; Owner: -
--

CREATE TRIGGER trg_log_listing_status BEFORE UPDATE ON land.parcels FOR EACH ROW EXECUTE FUNCTION land.log_listing_status_change();


--
-- Name: land_use trg_set_updated_at; Type: TRIGGER; Schema: land; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON land.land_use FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: parcel_documents trg_set_updated_at; Type: TRIGGER; Schema: land; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON land.parcel_documents FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: parcel_images trg_set_updated_at; Type: TRIGGER; Schema: land; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON land.parcel_images FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: parcels trg_set_updated_at; Type: TRIGGER; Schema: land; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON land.parcels FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: valuations trg_set_updated_at; Type: TRIGGER; Schema: land; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON land.valuations FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: zoning trg_set_updated_at; Type: TRIGGER; Schema: land; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON land.zoning FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: datasets trg_set_updated_at; Type: TRIGGER; Schema: metadata; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON metadata.datasets FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: etl_runs trg_set_updated_at; Type: TRIGGER; Schema: metadata; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON metadata.etl_runs FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: licenses trg_set_updated_at; Type: TRIGGER; Schema: metadata; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON metadata.licenses FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: quality_scores trg_set_updated_at; Type: TRIGGER; Schema: metadata; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON metadata.quality_scores FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: raster_catalog trg_set_updated_at; Type: TRIGGER; Schema: metadata; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON metadata.raster_catalog FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: refresh_logs trg_set_updated_at; Type: TRIGGER; Schema: metadata; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON metadata.refresh_logs FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: sources trg_set_updated_at; Type: TRIGGER; Schema: metadata; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON metadata.sources FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: validation_results trg_set_updated_at; Type: TRIGGER; Schema: metadata; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON metadata.validation_results FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: validation_rules trg_set_updated_at; Type: TRIGGER; Schema: metadata; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON metadata.validation_rules FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: reports trg_set_updated_at; Type: TRIGGER; Schema: reports; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON reports.reports FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: education trg_set_updated_at; Type: TRIGGER; Schema: social; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON social.education FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: financial trg_set_updated_at; Type: TRIGGER; Schema: social; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON social.financial FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: health trg_set_updated_at; Type: TRIGGER; Schema: social; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON social.health FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: markets trg_set_updated_at; Type: TRIGGER; Schema: social; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON social.markets FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: public_services trg_set_updated_at; Type: TRIGGER; Schema: social; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON social.public_services FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: soil_map_units trg_set_updated_at; Type: TRIGGER; Schema: soils; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON soils.soil_map_units FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: contours trg_set_updated_at; Type: TRIGGER; Schema: terrain; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON terrain.contours FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: watersheds trg_set_updated_at; Type: TRIGGER; Schema: terrain; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON terrain.watersheds FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: airports trg_set_updated_at; Type: TRIGGER; Schema: transport; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON transport.airports FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: bridges trg_set_updated_at; Type: TRIGGER; Schema: transport; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON transport.bridges FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: bus_stops trg_set_updated_at; Type: TRIGGER; Schema: transport; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON transport.bus_stops FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: ports trg_set_updated_at; Type: TRIGGER; Schema: transport; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON transport.ports FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: railways trg_set_updated_at; Type: TRIGGER; Schema: transport; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON transport.railways FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: roads trg_set_updated_at; Type: TRIGGER; Schema: transport; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON transport.roads FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: permissions trg_set_updated_at; Type: TRIGGER; Schema: users; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON users.permissions FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: roles trg_set_updated_at; Type: TRIGGER; Schema: users; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON users.roles FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: users trg_set_updated_at; Type: TRIGGER; Schema: users; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON users.users FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: dams trg_set_updated_at; Type: TRIGGER; Schema: utilities; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON utilities.dams FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: power_facilities trg_set_updated_at; Type: TRIGGER; Schema: utilities; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON utilities.power_facilities FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: power_lines trg_set_updated_at; Type: TRIGGER; Schema: utilities; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON utilities.power_lines FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: sewer_lines trg_set_updated_at; Type: TRIGGER; Schema: utilities; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON utilities.sewer_lines FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: waste_sites trg_set_updated_at; Type: TRIGGER; Schema: utilities; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON utilities.waste_sites FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: water_lines trg_set_updated_at; Type: TRIGGER; Schema: utilities; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON utilities.water_lines FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: water_points trg_set_updated_at; Type: TRIGGER; Schema: utilities; Owner: -
--

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON utilities.water_points FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: constituencies constituencies_county_code_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.constituencies
    ADD CONSTRAINT constituencies_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: constituencies constituencies_source_id_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.constituencies
    ADD CONSTRAINT constituencies_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: counties counties_source_id_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.counties
    ADD CONSTRAINT counties_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: country country_source_id_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.country
    ADD CONSTRAINT country_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: locations locations_county_code_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.locations
    ADD CONSTRAINT locations_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: locations locations_source_id_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.locations
    ADD CONSTRAINT locations_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: subcounties subcounties_county_code_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.subcounties
    ADD CONSTRAINT subcounties_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: subcounties subcounties_source_id_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.subcounties
    ADD CONSTRAINT subcounties_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: sublocations sublocations_county_code_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.sublocations
    ADD CONSTRAINT sublocations_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: sublocations sublocations_location_id_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.sublocations
    ADD CONSTRAINT sublocations_location_id_fkey FOREIGN KEY (location_id) REFERENCES admin.locations(id);


--
-- Name: sublocations sublocations_source_id_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.sublocations
    ADD CONSTRAINT sublocations_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: wards wards_constituency_code_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.wards
    ADD CONSTRAINT wards_constituency_code_fkey FOREIGN KEY (constituency_code) REFERENCES admin.constituencies(constituency_code);


--
-- Name: wards wards_county_code_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.wards
    ADD CONSTRAINT wards_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: wards wards_source_id_fkey; Type: FK CONSTRAINT; Schema: admin; Owner: -
--

ALTER TABLE ONLY admin.wards
    ADD CONSTRAINT wards_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: accessibility accessibility_parcel_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.accessibility
    ADD CONSTRAINT accessibility_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES land.parcels(parcel_id);


--
-- Name: enrichment_runs enrichment_runs_company_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.enrichment_runs
    ADD CONSTRAINT enrichment_runs_company_id_fkey FOREIGN KEY (company_id) REFERENCES clients.companies(company_id);


--
-- Name: parcel_intelligence parcel_intelligence_parcel_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.parcel_intelligence
    ADD CONSTRAINT parcel_intelligence_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES land.parcels(parcel_id);


--
-- Name: parcel_intelligence parcel_intelligence_run_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.parcel_intelligence
    ADD CONSTRAINT parcel_intelligence_run_id_fkey FOREIGN KEY (run_id) REFERENCES analytics.enrichment_runs(run_id);


--
-- Name: suitability_scores suitability_scores_intel_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.suitability_scores
    ADD CONSTRAINT suitability_scores_intel_id_fkey FOREIGN KEY (intel_id) REFERENCES analytics.parcel_intelligence(intel_id);


--
-- Name: suitability_scores suitability_scores_parcel_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: -
--

ALTER TABLE ONLY analytics.suitability_scores
    ADD CONSTRAINT suitability_scores_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES land.parcels(parcel_id);


--
-- Name: api_keys api_keys_company_id_fkey; Type: FK CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.api_keys
    ADD CONSTRAINT api_keys_company_id_fkey FOREIGN KEY (company_id) REFERENCES clients.companies(company_id);


--
-- Name: api_usage api_usage_api_key_id_fkey; Type: FK CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.api_usage
    ADD CONSTRAINT api_usage_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES clients.api_keys(api_key_id);


--
-- Name: branding branding_company_id_fkey; Type: FK CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.branding
    ADD CONSTRAINT branding_company_id_fkey FOREIGN KEY (company_id) REFERENCES clients.companies(company_id);


--
-- Name: companies companies_county_code_fkey; Type: FK CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.companies
    ADD CONSTRAINT companies_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: subscriptions subscriptions_company_id_fkey; Type: FK CONSTRAINT; Schema: clients; Owner: -
--

ALTER TABLE ONLY clients.subscriptions
    ADD CONSTRAINT subscriptions_company_id_fkey FOREIGN KEY (company_id) REFERENCES clients.companies(company_id);


--
-- Name: stations stations_county_code_fkey; Type: FK CONSTRAINT; Schema: climate; Owner: -
--

ALTER TABLE ONLY climate.stations
    ADD CONSTRAINT stations_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: stations stations_source_id_fkey; Type: FK CONSTRAINT; Schema: climate; Owner: -
--

ALTER TABLE ONLY climate.stations
    ADD CONSTRAINT stations_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: zonal_stats zonal_stats_source_id_fkey; Type: FK CONSTRAINT; Schema: climate; Owner: -
--

ALTER TABLE ONLY climate.zonal_stats
    ADD CONSTRAINT zonal_stats_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: coverage coverage_county_code_fkey; Type: FK CONSTRAINT; Schema: connectivity; Owner: -
--

ALTER TABLE ONLY connectivity.coverage
    ADD CONSTRAINT coverage_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: coverage coverage_source_id_fkey; Type: FK CONSTRAINT; Schema: connectivity; Owner: -
--

ALTER TABLE ONLY connectivity.coverage
    ADD CONSTRAINT coverage_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: fiber fiber_county_code_fkey; Type: FK CONSTRAINT; Schema: connectivity; Owner: -
--

ALTER TABLE ONLY connectivity.fiber
    ADD CONSTRAINT fiber_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: fiber fiber_source_id_fkey; Type: FK CONSTRAINT; Schema: connectivity; Owner: -
--

ALTER TABLE ONLY connectivity.fiber
    ADD CONSTRAINT fiber_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: towers towers_county_code_fkey; Type: FK CONSTRAINT; Schema: connectivity; Owner: -
--

ALTER TABLE ONLY connectivity.towers
    ADD CONSTRAINT towers_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: towers towers_source_id_fkey; Type: FK CONSTRAINT; Schema: connectivity; Owner: -
--

ALTER TABLE ONLY connectivity.towers
    ADD CONSTRAINT towers_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: nightlights_stats nightlights_stats_source_id_fkey; Type: FK CONSTRAINT; Schema: demographics; Owner: -
--

ALTER TABLE ONLY demographics.nightlights_stats
    ADD CONSTRAINT nightlights_stats_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: population_stats population_stats_source_id_fkey; Type: FK CONSTRAINT; Schema: demographics; Owner: -
--

ALTER TABLE ONLY demographics.population_stats
    ADD CONSTRAINT population_stats_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: forests forests_county_code_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.forests
    ADD CONSTRAINT forests_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: forests forests_source_id_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.forests
    ADD CONSTRAINT forests_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: protected_areas protected_areas_county_code_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.protected_areas
    ADD CONSTRAINT protected_areas_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: protected_areas protected_areas_source_id_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.protected_areas
    ADD CONSTRAINT protected_areas_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: riparian_buffers riparian_buffers_river_id_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.riparian_buffers
    ADD CONSTRAINT riparian_buffers_river_id_fkey FOREIGN KEY (river_id) REFERENCES environment.rivers(id);


--
-- Name: riparian_buffers riparian_buffers_source_id_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.riparian_buffers
    ADD CONSTRAINT riparian_buffers_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: rivers rivers_county_code_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.rivers
    ADD CONSTRAINT rivers_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: rivers rivers_source_id_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.rivers
    ADD CONSTRAINT rivers_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: waterbodies waterbodies_county_code_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.waterbodies
    ADD CONSTRAINT waterbodies_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: waterbodies waterbodies_source_id_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.waterbodies
    ADD CONSTRAINT waterbodies_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: wetlands wetlands_county_code_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.wetlands
    ADD CONSTRAINT wetlands_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: wetlands wetlands_source_id_fkey; Type: FK CONSTRAINT; Schema: environment; Owner: -
--

ALTER TABLE ONLY environment.wetlands
    ADD CONSTRAINT wetlands_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: drone_missions drone_missions_company_id_fkey; Type: FK CONSTRAINT; Schema: imagery; Owner: -
--

ALTER TABLE ONLY imagery.drone_missions
    ADD CONSTRAINT drone_missions_company_id_fkey FOREIGN KEY (company_id) REFERENCES clients.companies(company_id);


--
-- Name: drone_missions drone_missions_source_id_fkey; Type: FK CONSTRAINT; Schema: imagery; Owner: -
--

ALTER TABLE ONLY imagery.drone_missions
    ADD CONSTRAINT drone_missions_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: orthophotos orthophotos_mission_id_fkey; Type: FK CONSTRAINT; Schema: imagery; Owner: -
--

ALTER TABLE ONLY imagery.orthophotos
    ADD CONSTRAINT orthophotos_mission_id_fkey FOREIGN KEY (mission_id) REFERENCES imagery.drone_missions(mission_id);


--
-- Name: orthophotos orthophotos_source_id_fkey; Type: FK CONSTRAINT; Schema: imagery; Owner: -
--

ALTER TABLE ONLY imagery.orthophotos
    ADD CONSTRAINT orthophotos_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: scenes scenes_source_id_fkey; Type: FK CONSTRAINT; Schema: imagery; Owner: -
--

ALTER TABLE ONLY imagery.scenes
    ADD CONSTRAINT scenes_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: land_use land_use_county_code_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.land_use
    ADD CONSTRAINT land_use_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: land_use land_use_source_id_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.land_use
    ADD CONSTRAINT land_use_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: parcel_documents parcel_documents_parcel_id_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcel_documents
    ADD CONSTRAINT parcel_documents_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES land.parcels(parcel_id);


--
-- Name: parcel_documents parcel_documents_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcel_documents
    ADD CONSTRAINT parcel_documents_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES users.users(user_id);


--
-- Name: parcel_history parcel_history_parcel_id_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcel_history
    ADD CONSTRAINT parcel_history_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES land.parcels(parcel_id);


--
-- Name: parcel_history parcel_history_recorded_by_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcel_history
    ADD CONSTRAINT parcel_history_recorded_by_fkey FOREIGN KEY (recorded_by) REFERENCES users.users(user_id);


--
-- Name: parcel_images parcel_images_parcel_id_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcel_images
    ADD CONSTRAINT parcel_images_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES land.parcels(parcel_id);


--
-- Name: parcels parcels_company_id_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcels
    ADD CONSTRAINT parcels_company_id_fkey FOREIGN KEY (company_id) REFERENCES clients.companies(company_id);


--
-- Name: parcels parcels_county_code_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcels
    ADD CONSTRAINT parcels_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: parcels parcels_source_id_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcels
    ADD CONSTRAINT parcels_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: parcels parcels_ward_code_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.parcels
    ADD CONSTRAINT parcels_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES admin.wards(ward_code);


--
-- Name: valuations valuations_parcel_id_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.valuations
    ADD CONSTRAINT valuations_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES land.parcels(parcel_id);


--
-- Name: zoning zoning_county_code_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.zoning
    ADD CONSTRAINT zoning_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: zoning zoning_source_id_fkey; Type: FK CONSTRAINT; Schema: land; Owner: -
--

ALTER TABLE ONLY land.zoning
    ADD CONSTRAINT zoning_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: datasets datasets_backup_source_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.datasets
    ADD CONSTRAINT datasets_backup_source_id_fkey FOREIGN KEY (backup_source_id) REFERENCES metadata.sources(source_id);


--
-- Name: datasets datasets_license_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.datasets
    ADD CONSTRAINT datasets_license_id_fkey FOREIGN KEY (license_id) REFERENCES metadata.licenses(license_id);


--
-- Name: datasets datasets_source_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.datasets
    ADD CONSTRAINT datasets_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: etl_runs etl_runs_dataset_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.etl_runs
    ADD CONSTRAINT etl_runs_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES metadata.datasets(dataset_id);


--
-- Name: quality_scores quality_scores_dataset_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.quality_scores
    ADD CONSTRAINT quality_scores_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES metadata.datasets(dataset_id);


--
-- Name: raster_catalog raster_catalog_dataset_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.raster_catalog
    ADD CONSTRAINT raster_catalog_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES metadata.datasets(dataset_id);


--
-- Name: raster_catalog raster_catalog_source_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.raster_catalog
    ADD CONSTRAINT raster_catalog_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: refresh_logs refresh_logs_dataset_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.refresh_logs
    ADD CONSTRAINT refresh_logs_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES metadata.datasets(dataset_id);


--
-- Name: validation_results validation_results_rule_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.validation_results
    ADD CONSTRAINT validation_results_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES metadata.validation_rules(rule_id);


--
-- Name: validation_results validation_results_run_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.validation_results
    ADD CONSTRAINT validation_results_run_id_fkey FOREIGN KEY (run_id) REFERENCES metadata.etl_runs(run_id);


--
-- Name: validation_rules validation_rules_dataset_id_fkey; Type: FK CONSTRAINT; Schema: metadata; Owner: -
--

ALTER TABLE ONLY metadata.validation_rules
    ADD CONSTRAINT validation_rules_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES metadata.datasets(dataset_id);


--
-- Name: reports reports_company_id_fkey; Type: FK CONSTRAINT; Schema: reports; Owner: -
--

ALTER TABLE ONLY reports.reports
    ADD CONSTRAINT reports_company_id_fkey FOREIGN KEY (company_id) REFERENCES clients.companies(company_id);


--
-- Name: reports reports_parcel_id_fkey; Type: FK CONSTRAINT; Schema: reports; Owner: -
--

ALTER TABLE ONLY reports.reports
    ADD CONSTRAINT reports_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES land.parcels(parcel_id);


--
-- Name: reports reports_requested_by_fkey; Type: FK CONSTRAINT; Schema: reports; Owner: -
--

ALTER TABLE ONLY reports.reports
    ADD CONSTRAINT reports_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES users.users(user_id);


--
-- Name: education education_county_code_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.education
    ADD CONSTRAINT education_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: education education_source_id_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.education
    ADD CONSTRAINT education_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: financial financial_county_code_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.financial
    ADD CONSTRAINT financial_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: financial financial_source_id_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.financial
    ADD CONSTRAINT financial_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: health health_county_code_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.health
    ADD CONSTRAINT health_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: health health_source_id_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.health
    ADD CONSTRAINT health_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: markets markets_county_code_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.markets
    ADD CONSTRAINT markets_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: markets markets_source_id_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.markets
    ADD CONSTRAINT markets_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: public_services public_services_county_code_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.public_services
    ADD CONSTRAINT public_services_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: public_services public_services_source_id_fkey; Type: FK CONSTRAINT; Schema: social; Owner: -
--

ALTER TABLE ONLY social.public_services
    ADD CONSTRAINT public_services_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: soil_map_units soil_map_units_county_code_fkey; Type: FK CONSTRAINT; Schema: soils; Owner: -
--

ALTER TABLE ONLY soils.soil_map_units
    ADD CONSTRAINT soil_map_units_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: soil_map_units soil_map_units_source_id_fkey; Type: FK CONSTRAINT; Schema: soils; Owner: -
--

ALTER TABLE ONLY soils.soil_map_units
    ADD CONSTRAINT soil_map_units_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: contours contours_county_code_fkey; Type: FK CONSTRAINT; Schema: terrain; Owner: -
--

ALTER TABLE ONLY terrain.contours
    ADD CONSTRAINT contours_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: contours contours_source_id_fkey; Type: FK CONSTRAINT; Schema: terrain; Owner: -
--

ALTER TABLE ONLY terrain.contours
    ADD CONSTRAINT contours_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: watersheds watersheds_county_code_fkey; Type: FK CONSTRAINT; Schema: terrain; Owner: -
--

ALTER TABLE ONLY terrain.watersheds
    ADD CONSTRAINT watersheds_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: watersheds watersheds_source_id_fkey; Type: FK CONSTRAINT; Schema: terrain; Owner: -
--

ALTER TABLE ONLY terrain.watersheds
    ADD CONSTRAINT watersheds_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: airports airports_county_code_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.airports
    ADD CONSTRAINT airports_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: airports airports_source_id_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.airports
    ADD CONSTRAINT airports_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: bridges bridges_county_code_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.bridges
    ADD CONSTRAINT bridges_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: bridges bridges_source_id_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.bridges
    ADD CONSTRAINT bridges_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: bus_stops bus_stops_county_code_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.bus_stops
    ADD CONSTRAINT bus_stops_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: bus_stops bus_stops_source_id_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.bus_stops
    ADD CONSTRAINT bus_stops_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: ports ports_county_code_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.ports
    ADD CONSTRAINT ports_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: ports ports_source_id_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.ports
    ADD CONSTRAINT ports_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: railways railways_county_code_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.railways
    ADD CONSTRAINT railways_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: railways railways_source_id_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.railways
    ADD CONSTRAINT railways_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: roads roads_county_code_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.roads
    ADD CONSTRAINT roads_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: roads roads_source_id_fkey; Type: FK CONSTRAINT; Schema: transport; Owner: -
--

ALTER TABLE ONLY transport.roads
    ADD CONSTRAINT roads_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: audit_log audit_log_user_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.audit_log
    ADD CONSTRAINT audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.users(user_id);


--
-- Name: role_permissions role_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES users.permissions(permission_id);


--
-- Name: role_permissions role_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES users.roles(role_id);


--
-- Name: user_roles user_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.user_roles
    ADD CONSTRAINT user_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES users.roles(role_id);


--
-- Name: user_roles user_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.user_roles
    ADD CONSTRAINT user_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.users(user_id);


--
-- Name: users users_company_id_fkey; Type: FK CONSTRAINT; Schema: users; Owner: -
--

ALTER TABLE ONLY users.users
    ADD CONSTRAINT users_company_id_fkey FOREIGN KEY (company_id) REFERENCES clients.companies(company_id);


--
-- Name: dams dams_county_code_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.dams
    ADD CONSTRAINT dams_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: dams dams_source_id_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.dams
    ADD CONSTRAINT dams_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: power_facilities power_facilities_county_code_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.power_facilities
    ADD CONSTRAINT power_facilities_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: power_facilities power_facilities_source_id_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.power_facilities
    ADD CONSTRAINT power_facilities_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: power_lines power_lines_county_code_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.power_lines
    ADD CONSTRAINT power_lines_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: power_lines power_lines_source_id_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.power_lines
    ADD CONSTRAINT power_lines_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: sewer_lines sewer_lines_county_code_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.sewer_lines
    ADD CONSTRAINT sewer_lines_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: sewer_lines sewer_lines_source_id_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.sewer_lines
    ADD CONSTRAINT sewer_lines_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: waste_sites waste_sites_county_code_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.waste_sites
    ADD CONSTRAINT waste_sites_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: waste_sites waste_sites_source_id_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.waste_sites
    ADD CONSTRAINT waste_sites_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: water_lines water_lines_county_code_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.water_lines
    ADD CONSTRAINT water_lines_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: water_lines water_lines_source_id_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.water_lines
    ADD CONSTRAINT water_lines_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- Name: water_points water_points_county_code_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.water_points
    ADD CONSTRAINT water_points_county_code_fkey FOREIGN KEY (county_code) REFERENCES admin.counties(county_code);


--
-- Name: water_points water_points_source_id_fkey; Type: FK CONSTRAINT; Schema: utilities; Owner: -
--

ALTER TABLE ONLY utilities.water_points
    ADD CONSTRAINT water_points_source_id_fkey FOREIGN KEY (source_id) REFERENCES metadata.sources(source_id);


--
-- PostgreSQL database dump complete
--

\unrestrict hZLeWWduxsfeU5x6tTPuVItxaJJMlfYNNfiHb0tAXraGz0KNLmgcUwykQzpSlB8

