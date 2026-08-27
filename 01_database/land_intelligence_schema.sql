-- ============================================================================
-- LAND INTELLIGENCE PLATFORM - NATIONAL SPATIAL INTELLIGENCE DATABASE
-- Geocode Spatial Solutions Ltd
-- Database: land_intelligence_kenya
-- Target:   PostgreSQL 15+ with PostGIS 3.3+
-- Version:  1.0.0 (2026-07-13)
--
-- HOW TO RUN
--   1. As a superuser:  CREATE DATABASE land_intelligence_kenya;
--   2. Connect:         \c land_intelligence_kenya
--   3. Execute:         \i land_intelligence_schema.sql
--
-- DESIGN RULES (enforced throughout)
--   * All geometries stored in EPSG:4326. Reproject in queries when measuring.
--   * Every data row carries: source_id, source_date, confidence, version,
--     status, created_at, updated_at. Nothing enters without provenance.
--   * Never overwrite: superseded rows get status = 'superseded', new rows
--     get version + 1.
--   * Rasters (DEM, soils, rainfall, land cover, imagery) are NOT stored in
--     the database. They live in object storage as Cloud Optimized GeoTIFFs.
--     The database stores catalogue entries and URLs (metadata.raster_catalog).
--   * The frontend never touches this database. Access is API -> service
--     layer -> PostGIS only.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 01  EXTENSIONS
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- uuid generation
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- fuzzy text search on names

-- ---------------------------------------------------------------------------
-- 02  SCHEMAS
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS metadata;      -- data governance: sources, catalogues, ETL history
CREATE SCHEMA IF NOT EXISTS admin;         -- administrative boundaries
CREATE SCHEMA IF NOT EXISTS clients;       -- land companies, subscriptions, API keys
CREATE SCHEMA IF NOT EXISTS users;         -- platform users, roles, audit
CREATE SCHEMA IF NOT EXISTS land;          -- client parcels and land administration
CREATE SCHEMA IF NOT EXISTS transport;     -- roads, rail, air, ports
CREATE SCHEMA IF NOT EXISTS utilities;     -- power, water, sewer, waste
CREATE SCHEMA IF NOT EXISTS social;        -- schools, health, services, finance, markets
CREATE SCHEMA IF NOT EXISTS environment;   -- forests, wetlands, protected areas, water
CREATE SCHEMA IF NOT EXISTS terrain;       -- vector terrain products (rasters in catalogue)
CREATE SCHEMA IF NOT EXISTS climate;       -- stations and zonal climate statistics
CREATE SCHEMA IF NOT EXISTS soils;         -- soil map units (rasters in catalogue)
CREATE SCHEMA IF NOT EXISTS demographics;  -- population and nightlights statistics
CREATE SCHEMA IF NOT EXISTS connectivity;  -- towers, mobile coverage, fiber
CREATE SCHEMA IF NOT EXISTS imagery;       -- scene and drone mission catalogues
CREATE SCHEMA IF NOT EXISTS analytics;     -- parcel enrichment results and scores
CREATE SCHEMA IF NOT EXISTS reports;       -- generated PDF report records
CREATE SCHEMA IF NOT EXISTS logs;          -- API, error, download, activity logs

-- ---------------------------------------------------------------------------
-- 03  HELPER FUNCTION: keep updated_at current automatically
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 04  METADATA (created first: every other table points back here)
-- ============================================================================

CREATE TABLE metadata.sources (
    source_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,                -- e.g. 'OpenStreetMap', 'KNBS', 'iSDAsoil'
    organisation text,
    tier smallint NOT NULL CHECK (tier BETWEEN 1 AND 5),  -- 1 Kenya govt ... 5 Geocode generated
    url text,
    license text,                             -- e.g. 'ODbL 1.0', 'CC BY 4.0'
    redistribution_allowed boolean,           -- can we ship this in a paid product?
    attribution_required boolean DEFAULT true,
    api_available boolean DEFAULT false,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE metadata.licenses (
    license_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,                -- 'ODbL-1.0', 'CC-BY-4.0', 'CC-BY-SA-4.0', 'GOK-OPEN'
    name text NOT NULL,
    commercial_use boolean,
    share_alike boolean,
    attribution_text text,
    full_text_url text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE metadata.datasets (
    dataset_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,                -- 'transport.roads', 'soils.ph' etc.
    name text NOT NULL,
    category text NOT NULL,                   -- one of the 13 inventory categories
    description text,
    buyer_question text,                      -- which buyer question this answers
    source_id integer REFERENCES metadata.sources(source_id),
    backup_source_id integer REFERENCES metadata.sources(source_id),
    license_id integer REFERENCES metadata.licenses(license_id),
    storage text NOT NULL DEFAULT 'postgis' CHECK (storage IN ('postgis','object_storage')),
    target_table text,                        -- where it lands in this database
    native_crs text,
    resolution text,                          -- '10 m', '30 m', '1:50000', 'point'
    update_frequency text,                    -- 'daily', 'monthly', 'annual', 'static'
    coverage text NOT NULL DEFAULT 'national' CHECK (coverage IN ('national','pilot_counties','partial','global')),
    priority text NOT NULL DEFAULT 'P2' CHECK (priority IN ('P1','P2','P3')),
    etl_status text NOT NULL DEFAULT 'planned'
        CHECK (etl_status IN ('planned','sourced','ingested','validated','published','deprecated')),
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Rasters never enter PostGIS. This catalogue is how the platform finds them.
CREATE TABLE metadata.raster_catalog (
    raster_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id integer REFERENCES metadata.datasets(dataset_id),
    name text NOT NULL,                       -- 'Copernicus DEM GLO-30 Kenya', 'CHIRPS 2025 annual'
    variable text,                            -- 'elevation', 'slope', 'rainfall', 'ph', 'ndvi'
    storage_url text NOT NULL,                -- s3:// or https:// COG location
    format text NOT NULL DEFAULT 'COG',
    pixel_size_m numeric,
    band_count integer DEFAULT 1,
    nodata_value numeric,
    temporal_start date,
    temporal_end date,
    bbox geometry(Polygon, 4326),             -- footprint for spatial lookup
    checksum text,
    source_id integer REFERENCES metadata.sources(source_id),
    source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE metadata.etl_runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id integer REFERENCES metadata.datasets(dataset_id),
    pipeline text NOT NULL,                   -- script/DAG identifier
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    run_status text NOT NULL DEFAULT 'running'
        CHECK (run_status IN ('running','success','failed','partial')),
    rows_in bigint, rows_out bigint, rows_rejected bigint,
    log_url text, error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE metadata.refresh_logs (
    refresh_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id integer REFERENCES metadata.datasets(dataset_id),
    previous_version integer,
    new_version integer,
    refreshed_at timestamptz NOT NULL DEFAULT now(),
    refreshed_by text,
    change_summary text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE metadata.quality_scores (
    quality_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id integer REFERENCES metadata.datasets(dataset_id),
    assessed_at date NOT NULL,
    completeness numeric CHECK (completeness BETWEEN 0 AND 100),
    positional_accuracy numeric,              -- metres, where measurable
    attribute_accuracy numeric CHECK (attribute_accuracy BETWEEN 0 AND 100),
    currency_months numeric,                  -- how old is the data
    overall_score numeric CHECK (overall_score BETWEEN 0 AND 100),
    assessed_by text, notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE metadata.validation_rules (
    rule_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id integer REFERENCES metadata.datasets(dataset_id),
    rule_name text NOT NULL,
    rule_type text NOT NULL CHECK (rule_type IN ('geometry','attribute','topology','referential','range')),
    rule_sql text,                            -- executable check
    severity text NOT NULL DEFAULT 'error' CHECK (severity IN ('error','warning','info')),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE metadata.validation_results (
    result_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_id integer REFERENCES metadata.validation_rules(rule_id),
    run_id bigint REFERENCES metadata.etl_runs(run_id),
    executed_at timestamptz NOT NULL DEFAULT now(),
    passed boolean NOT NULL,
    failures bigint DEFAULT 0,
    sample_failures jsonb,                    -- a few offending ids for debugging
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 05  ADMIN - administrative boundaries
-- ============================================================================

CREATE TABLE admin.country (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    iso3 text NOT NULL DEFAULT 'KEN',
    name text NOT NULL DEFAULT 'Kenya',
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin.counties (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    county_code text NOT NULL UNIQUE,         -- official code, '001' Mombasa ... '047' Nairobi
    name text NOT NULL,
    is_pilot boolean NOT NULL DEFAULT false,  -- true for the 20 launch counties
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin.constituencies (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    constituency_code text UNIQUE,
    name text NOT NULL,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin.subcounties (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subcounty_code text UNIQUE,
    name text NOT NULL,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin.wards (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ward_code text UNIQUE,
    name text NOT NULL,
    constituency_code text REFERENCES admin.constituencies(constituency_code),
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin.locations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin.sublocations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    location_id bigint REFERENCES admin.locations(id),
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 06  CLIENTS - the land companies who license the platform
-- ============================================================================

CREATE TABLE clients.companies (
    company_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    slug text NOT NULL UNIQUE,                -- used in white-label URLs
    contact_email text, contact_phone text,
    county_code text REFERENCES admin.counties(county_code),
    is_active boolean NOT NULL DEFAULT true,
    onboarded_at date,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE clients.subscriptions (
    subscription_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES clients.companies(company_id),
    plan text NOT NULL CHECK (plan IN ('starter','growth','enterprise','custom')),
    monthly_fee_kes numeric,
    parcel_limit integer,                     -- how many parcels the plan covers
    report_limit integer,                     -- PDF reports per month
    api_calls_limit bigint,
    starts_on date NOT NULL,
    ends_on date,
    sub_status text NOT NULL DEFAULT 'active' CHECK (sub_status IN ('trial','active','past_due','cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE clients.branding (
    branding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL UNIQUE REFERENCES clients.companies(company_id),
    logo_url text, primary_color text, secondary_color text,
    report_footer text, custom_domain text,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE clients.api_keys (
    api_key_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES clients.companies(company_id),
    key_hash text NOT NULL UNIQUE,            -- never store the raw key
    label text,
    scopes text[] NOT NULL DEFAULT '{read}',
    expires_at timestamptz,
    revoked boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE clients.api_usage (
    usage_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    api_key_id uuid REFERENCES clients.api_keys(api_key_id),
    period_start date NOT NULL,
    period_end date NOT NULL,
    calls bigint NOT NULL DEFAULT 0,
    reports_generated integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 07  USERS - platform users (Geocode staff + client admins)
-- ============================================================================

CREATE TABLE users.users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE,
    full_name text,
    password_hash text,                       -- null if using external auth
    company_id uuid REFERENCES clients.companies(company_id),  -- null = Geocode staff
    is_active boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users.roles (
    role_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,                -- 'superadmin', 'data_engineer', 'client_admin', 'client_viewer'
    name text NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users.permissions (
    permission_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,                -- 'parcels.write', 'reports.generate', 'datasets.publish'
    description text,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users.role_permissions (
    role_id integer NOT NULL REFERENCES users.roles(role_id),
    permission_id integer NOT NULL REFERENCES users.permissions(permission_id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE users.user_roles (
    user_id uuid NOT NULL REFERENCES users.users(user_id),
    role_id integer NOT NULL REFERENCES users.roles(role_id),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE users.audit_log (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid REFERENCES users.users(user_id),
    action text NOT NULL,                     -- 'parcel.upload', 'report.generate', 'dataset.publish'
    entity text, entity_id text,
    detail jsonb,
    ip_address inet,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 08  LAND - client parcels. Clients upload their surveyed boundaries;
--     the platform enriches them. This is the product's centre of gravity.
-- ============================================================================

CREATE TABLE land.parcels (
    parcel_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES clients.companies(company_id),
    parcel_ref text NOT NULL,                 -- client's own reference, 'Juja Farm Ph2 Plot 45'
    lr_number text,                           -- official land reference number if provided
    project_name text,                        -- the estate/scheme the plot belongs to
    county_code text REFERENCES admin.counties(county_code),
    ward_code text REFERENCES admin.wards(ward_code),
    area_sqm numeric,                         -- computed on ingest from geometry
    price_kes numeric,
    listing_status text NOT NULL DEFAULT 'available'
        CHECK (listing_status IN ('available','reserved','sold','withdrawn')),
    geom geometry(MultiPolygon, 4326) NOT NULL,
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, parcel_ref, version)
);

CREATE TABLE land.parcel_documents (
    document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id uuid NOT NULL REFERENCES land.parcels(parcel_id),
    doc_type text NOT NULL CHECK (doc_type IN ('survey_plan','mutation','title_copy','search_certificate','agreement','other')),
    storage_url text NOT NULL,                -- object storage, never stored in-db
    uploaded_by uuid REFERENCES users.users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE land.parcel_images (
    image_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id uuid NOT NULL REFERENCES land.parcels(parcel_id),
    image_type text CHECK (image_type IN ('ground_photo','drone','satellite_chip','other')),
    storage_url text NOT NULL,
    captured_on date,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE land.parcel_history (
    history_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parcel_id uuid NOT NULL REFERENCES land.parcels(parcel_id),
    event text NOT NULL,                      -- 'uploaded', 'boundary_corrected', 'price_change', 'sold'
    detail jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid REFERENCES users.users(user_id)
);

CREATE TABLE land.zoning (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zone_class text NOT NULL,                 -- 'residential', 'agricultural', 'commercial', 'industrial', 'mixed'
    zone_label text,
    plan_name text,                           -- physical development plan it comes from
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE land.land_use (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    use_class text NOT NULL,                  -- observed use: 'cropland', 'grazing', 'built', 'forest'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE land.valuations (
    valuation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parcel_id uuid REFERENCES land.parcels(parcel_id),
    valuation_kes numeric NOT NULL,
    valuation_date date NOT NULL,
    method text,                              -- 'market_comparison', 'client_declared', 'model_estimate'
    valuer text,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 09  TRANSPORT
-- ============================================================================

CREATE TABLE transport.roads (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    osm_id bigint,
    name text,
    road_class text NOT NULL,                 -- 'motorway','trunk','primary','secondary','tertiary','unclassified','residential','track','path'
    surface text,                             -- 'paved','unpaved','unknown'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiLineString, 4326) NOT NULL,
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transport.railways (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text, rail_type text,                -- 'sgr','mgr','commuter'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiLineString, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transport.airports (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    facility_type text NOT NULL CHECK (facility_type IN ('international','domestic','airstrip')),
    iata_code text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326) NOT NULL,
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transport.ports (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL, port_type text,       -- 'sea','lake','dry'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transport.bridges (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transport.bus_stops (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text, stop_type text,                -- 'stage','terminus','stop'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 10  UTILITIES
-- ============================================================================

CREATE TABLE utilities.power_lines (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    line_type text NOT NULL CHECK (line_type IN ('transmission','distribution')),
    voltage_kv numeric,
    operator text,                            -- 'KETRACO','Kenya Power','REREC'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiLineString, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE utilities.power_facilities (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    facility_type text NOT NULL CHECK (facility_type IN ('substation','transformer','power_plant')),
    name text, capacity text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE utilities.water_lines (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text, operator text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiLineString, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE utilities.water_points (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    point_type text NOT NULL CHECK (point_type IN ('borehole','spring','water_kiosk','treatment_plant','storage_tank')),
    name text, operator text, is_functional boolean,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE utilities.dams (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text, purpose text,                  -- 'water_supply','irrigation','hydropower','multi'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE utilities.sewer_lines (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operator text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiLineString, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE utilities.waste_sites (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_type text NOT NULL CHECK (site_type IN ('dumpsite','landfill','transfer_station')),
    name text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 11  SOCIAL - grouped tables with a type column, not one table per subtype.
--     Same columns, same geometry, one ETL path, one API query.
-- ============================================================================

CREATE TABLE social.education (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    level text NOT NULL CHECK (level IN ('primary','secondary','tvet','university','other')),
    ownership text,                           -- 'public','private'
    knec_code text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE social.health (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    facility_type text NOT NULL CHECK (facility_type IN ('hospital','health_centre','dispensary','clinic','pharmacy')),
    kephs_level smallint CHECK (kephs_level BETWEEN 1 AND 6),
    ownership text,                           -- 'moh','private','faith_based','ngo'
    mfl_code text,                            -- Kenya Master Facility List code
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE social.public_services (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    service_type text NOT NULL CHECK (service_type IN ('police','fire_station','huduma_centre','court','chiefs_office','government_office')),
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE social.financial (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    facility_type text NOT NULL CHECK (facility_type IN ('bank_branch','atm','sacco','microfinance','mobile_money_agent')),
    institution text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE social.markets (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    market_type text,                         -- 'open_air','livestock','wholesale','retail_centre'
    market_days text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 12  ENVIRONMENT
-- ============================================================================

CREATE TABLE environment.protected_areas (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    area_type text NOT NULL CHECK (area_type IN ('national_park','national_reserve','conservancy','sanctuary','wildlife_corridor','marine_protected')),
    authority text,                           -- 'KWS','county','community'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE environment.forests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text,
    forest_type text,                         -- 'gazetted','community','private','mangrove'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE environment.wetlands (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text, wetland_type text,             -- 'swamp','marsh','floodplain','ramsar'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE environment.waterbodies (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text,
    body_type text NOT NULL CHECK (body_type IN ('lake','reservoir','pond','lagoon')),
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE environment.rivers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text,
    river_class text,                         -- 'perennial','seasonal'
    stream_order smallint,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiLineString, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE environment.riparian_buffers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    river_id bigint REFERENCES environment.rivers(id),
    buffer_width_m numeric NOT NULL,          -- statutory width used
    legal_basis text,                         -- 'WRA guideline', 'Survey Act', 'EMCA'
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 13  TERRAIN - vector products only. DEM, slope, aspect, hillshade, TWI,
--     flow direction and accumulation are rasters -> metadata.raster_catalog.
-- ============================================================================

CREATE TABLE terrain.watersheds (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text, basin_code text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE terrain.contours (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    elevation_m numeric NOT NULL,
    interval_m numeric,                       -- contour interval this belongs to
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiLineString, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 14  CLIMATE - stations + pre-summarised statistics per admin unit.
--     Gridded rainfall/temperature rasters -> metadata.raster_catalog.
-- ============================================================================

CREATE TABLE climate.stations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL, station_code text UNIQUE,
    operator text DEFAULT 'Kenya Meteorological Department',
    elevation_m numeric,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE climate.zonal_stats (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_level text NOT NULL CHECK (admin_level IN ('county','constituency','ward')),
    admin_code text NOT NULL,
    variable text NOT NULL,                   -- 'rainfall_mm','temp_mean_c','solar_kwh_m2','wind_ms','eto_mm','spi'
    period text NOT NULL,                     -- '2025', '2025-03', '1991-2020_normal'
    stat text NOT NULL DEFAULT 'mean' CHECK (stat IN ('mean','min','max','sum','median','stddev')),
    value numeric NOT NULL,
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (admin_level, admin_code, variable, period, stat, version)
);

-- ============================================================================
-- 15  SOILS - vector soil map units. Gridded soil properties (iSDAsoil,
--     SoilGrids pH, texture, carbon at 30 m) -> metadata.raster_catalog.
-- ============================================================================

CREATE TABLE soils.soil_map_units (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unit_code text,
    soil_type text,                           -- WRB class: 'Ferralsol','Vertisol','Nitisol'...
    texture_class text,                       -- 'clay','sandy loam','loam'...
    drainage_class text,                      -- 'well','moderate','poor','very poor'
    depth_class text,                         -- 'shallow','moderate','deep'
    fertility_class text,                     -- 'low','moderate','high'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 16  DEMOGRAPHICS - statistics per admin unit. WorldPop / nightlights
--     rasters -> metadata.raster_catalog.
-- ============================================================================

CREATE TABLE demographics.population_stats (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_level text NOT NULL CHECK (admin_level IN ('county','constituency','ward','sublocation')),
    admin_code text NOT NULL,
    year integer NOT NULL,
    population bigint,
    households bigint,
    density_per_km2 numeric,
    growth_rate_pct numeric,
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (admin_level, admin_code, year, version)
);

CREATE TABLE demographics.nightlights_stats (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_level text NOT NULL CHECK (admin_level IN ('county','constituency','ward')),
    admin_code text NOT NULL,
    period text NOT NULL,                     -- '2025', '2025-06'
    radiance_mean numeric,
    radiance_sum numeric,
    lit_area_pct numeric,
    trend_pct_yr numeric,                     -- change over trailing 3 years: is the area developing?
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (admin_level, admin_code, period, version)
);

-- ============================================================================
-- 17  CONNECTIVITY
-- ============================================================================

CREATE TABLE connectivity.towers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operator text,                            -- 'Safaricom','Airtel','Telkom','shared'
    radio text CHECK (radio IN ('gsm','umts','lte','nr','unknown')),
    cell_id text,
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(Point, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE connectivity.coverage (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operator text NOT NULL,
    technology text NOT NULL CHECK (technology IN ('2g','3g','4g','5g')),
    signal_class text,                        -- 'strong','fair','weak'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiPolygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE connectivity.fiber (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operator text, network_level text,        -- 'national_backbone','metro','last_mile'
    county_code text REFERENCES admin.counties(county_code),
    geom geometry(MultiLineString, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 18  IMAGERY - catalogues only. Pixels live in object storage / GEE.
-- ============================================================================

CREATE TABLE imagery.scenes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sensor text NOT NULL,                     -- 'sentinel2','landsat8','landsat9'
    scene_id text NOT NULL UNIQUE,
    acquired_on date NOT NULL,
    cloud_cover_pct numeric,
    storage_url text,                         -- COG or GEE asset id
    footprint geometry(Polygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE imagery.drone_missions (
    mission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid REFERENCES clients.companies(company_id),
    project_name text,
    flown_on date, pilot text, equipment text,
    gsd_cm numeric,                           -- ground sampling distance
    footprint geometry(Polygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE imagery.orthophotos (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mission_id uuid REFERENCES imagery.drone_missions(mission_id),
    storage_url text NOT NULL,
    pixel_size_cm numeric,
    footprint geometry(Polygon, 4326),
    source_id integer REFERENCES metadata.sources(source_id), source_date date,
    confidence smallint CHECK (confidence BETWEEN 1 AND 5),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 19  ANALYTICS - the money tables. One enrichment run per parcel batch,
--     one wide intelligence row per parcel, scores broken out for the report.
-- ============================================================================

CREATE TABLE analytics.enrichment_runs (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid REFERENCES clients.companies(company_id),
    engine_version text NOT NULL,             -- version of the enrichment code, for reproducibility
    parcels_processed integer,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    run_status text NOT NULL DEFAULT 'running' CHECK (run_status IN ('running','success','failed','partial')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analytics.parcel_intelligence (
    intel_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parcel_id uuid NOT NULL REFERENCES land.parcels(parcel_id),
    run_id uuid REFERENCES analytics.enrichment_runs(run_id),
    -- access (metres unless stated)
    dist_paved_road_m numeric, dist_any_road_m numeric, dist_bus_stop_m numeric,
    dist_town_centre_m numeric, travel_time_town_min numeric,
    -- social
    dist_primary_school_m numeric, dist_secondary_school_m numeric,
    dist_hospital_m numeric, dist_clinic_m numeric, dist_market_m numeric,
    dist_police_m numeric,
    -- utilities
    dist_power_line_m numeric, dist_transformer_m numeric,
    dist_water_point_m numeric, dist_water_line_m numeric, dist_sewer_m numeric,
    -- environment and hazard
    dist_river_m numeric, in_riparian_buffer boolean,
    in_protected_area boolean, dist_protected_area_m numeric,
    in_wetland boolean, flood_risk_class text CHECK (flood_risk_class IN ('low','moderate','high','very_high')),
    landslide_risk_class text CHECK (landslide_risk_class IN ('low','moderate','high')),
    -- terrain (sampled from rasters at enrichment time)
    elevation_mean_m numeric, slope_mean_pct numeric, slope_max_pct numeric,
    aspect_dominant text, twi_mean numeric,
    -- soils
    soil_type text, soil_ph numeric, soil_texture text,
    soil_drainage text, soil_depth_class text, soil_fertility text,
    -- climate
    rainfall_mm_yr numeric, temp_mean_c numeric, solar_kwh_m2_day numeric,
    -- land cover and vegetation
    landcover_class text, ndvi_mean numeric, built_up_pct_1km numeric,
    -- people and growth
    pop_density_km2 numeric, nightlights_trend_pct numeric,
    -- connectivity
    coverage_2g boolean, coverage_3g boolean, coverage_4g boolean, coverage_5g boolean,
    dist_fiber_m numeric,
    -- zoning
    zoning_class text,
    computed_at timestamptz NOT NULL DEFAULT now(),
    engine_version text NOT NULL,
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (parcel_id, version)
);

CREATE TABLE analytics.suitability_scores (
    score_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parcel_id uuid NOT NULL REFERENCES land.parcels(parcel_id),
    intel_id bigint REFERENCES analytics.parcel_intelligence(intel_id),
    residential_score numeric CHECK (residential_score BETWEEN 0 AND 100),
    agricultural_score numeric CHECK (agricultural_score BETWEEN 0 AND 100),
    commercial_score numeric CHECK (commercial_score BETWEEN 0 AND 100),
    investment_score numeric CHECK (investment_score BETWEEN 0 AND 100),
    overall_score numeric CHECK (overall_score BETWEEN 0 AND 100),
    score_breakdown jsonb,                    -- per-factor weights and values, shown in the PDF
    model_version text NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (parcel_id, version)
);

CREATE TABLE analytics.accessibility (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parcel_id uuid NOT NULL REFERENCES land.parcels(parcel_id),
    destination_type text NOT NULL,           -- 'nairobi_cbd','county_hq','nearest_town','sgr_station'
    destination_name text,
    distance_km numeric,
    travel_time_min numeric,
    mode text NOT NULL DEFAULT 'driving' CHECK (mode IN ('driving','walking','matatu')),
    computed_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','pending_review','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 20  REPORTS
-- ============================================================================

CREATE TABLE reports.reports (
    report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id uuid NOT NULL REFERENCES land.parcels(parcel_id),
    company_id uuid REFERENCES clients.companies(company_id),
    requested_by uuid REFERENCES users.users(user_id),
    report_type text NOT NULL DEFAULT 'full' CHECK (report_type IN ('full','summary','custom')),
    intel_version integer,                    -- which parcel_intelligence version it used
    score_version integer,
    pdf_url text,                             -- object storage
    price_kes numeric,
    report_status text NOT NULL DEFAULT 'queued' CHECK (report_status IN ('queued','generating','ready','failed','expired')),
    generated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 21  LOGS
-- ============================================================================

CREATE TABLE logs.api_logs (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    api_key_id uuid,
    endpoint text NOT NULL, method text NOT NULL,
    status_code integer, latency_ms integer,
    ip_address inet,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE logs.error_logs (
    error_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service text NOT NULL,                    -- 'api','etl','enrichment','report_engine'
    severity text NOT NULL DEFAULT 'error' CHECK (severity IN ('warning','error','critical')),
    message text NOT NULL,
    context jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE logs.downloads (
    download_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid, report_id uuid,
    resource text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE logs.user_activity (
    activity_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid,
    activity text NOT NULL,                   -- 'login','parcel_view','map_view','search'
    detail jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 22  SEED DATA - all 47 counties, with the 20 launch counties flagged
-- ============================================================================

INSERT INTO admin.counties (county_code, name, is_pilot) VALUES
('001','Mombasa',true),      ('002','Kwale',false),        ('003','Kilifi',true),
('004','Tana River',false),  ('005','Lamu',false),         ('006','Taita Taveta',false),
('007','Garissa',false),     ('008','Wajir',false),        ('009','Mandera',false),
('010','Marsabit',false),    ('011','Isiolo',false),       ('012','Meru',true),
('013','Tharaka-Nithi',false),('014','Embu',true),         ('015','Kitui',true),
('016','Machakos',true),     ('017','Makueni',false),      ('018','Nyandarua',false),
('019','Nyeri',true),        ('020','Kirinyaga',true),     ('021','Murang''a',true),
('022','Kiambu',true),       ('023','Turkana',false),      ('024','West Pokot',false),
('025','Samburu',false),     ('026','Trans Nzoia',false),  ('027','Uasin Gishu',true),
('028','Elgeyo-Marakwet',false),('029','Nandi',false),     ('030','Baringo',false),
('031','Laikipia',true),     ('032','Nakuru',true),        ('033','Narok',true),
('034','Kajiado',true),      ('035','Kericho',true),       ('036','Bomet',false),
('037','Kakamega',true),     ('038','Vihiga',false),       ('039','Bungoma',true),
('040','Busia',false),       ('041','Siaya',false),        ('042','Kisumu',true),
('043','Homa Bay',false),    ('044','Migori',false),       ('045','Kisii',true),
('046','Nyamira',false),     ('047','Nairobi',false);

-- Core roles
INSERT INTO users.roles (code, name, description) VALUES
('superadmin','Super Administrator','Full platform control (Geocode)'),
('data_engineer','Data Engineer','Manages datasets, ETL and QA (Geocode)'),
('analyst','Analyst','Runs enrichment and builds reports (Geocode)'),
('client_admin','Client Administrator','Manages own company parcels and branding'),
('client_viewer','Client Viewer','Read-only access to own company data');

-- ============================================================================
-- 23  AUTOMATIC INDEXES AND TRIGGERS
--     Instead of hand-writing ~150 statements, loop over the catalogue:
--     every geometry column gets a GiST index, every county_code gets a
--     B-tree index, every table with updated_at gets the touch trigger.
-- ============================================================================

-- GiST spatial indexes on every geometry column
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT f_table_schema AS s, f_table_name AS t, f_geometry_column AS c
        FROM geometry_columns
        WHERE f_table_schema NOT IN ('public','tiger','topology')
    LOOP
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I.%I USING gist (%I)',
                       r.t || '_' || r.c || '_gix', r.s, r.t, r.c);
    END LOOP;
END $$;

-- B-tree indexes on every county_code column
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT table_schema AS s, table_name AS t
        FROM information_schema.columns
        WHERE column_name = 'county_code'
          AND table_schema NOT IN ('information_schema','pg_catalog')
          AND table_name <> 'counties'
    LOOP
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I.%I (county_code)',
                       r.t || '_county_code_idx', r.s, r.t);
    END LOOP;
END $$;

-- updated_at maintenance trigger on every table that has the column
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT table_schema AS s, table_name AS t
        FROM information_schema.columns
        WHERE column_name = 'updated_at'
          AND table_schema NOT IN ('information_schema','pg_catalog')
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_set_updated_at ON %I.%I', r.s, r.t);
        EXECUTE format('CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON %I.%I
                        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()', r.s, r.t);
    END LOOP;
END $$;

-- Frequently hit foreign keys
CREATE INDEX IF NOT EXISTS parcels_company_idx ON land.parcels (company_id);
CREATE INDEX IF NOT EXISTS parcels_listing_idx ON land.parcels (listing_status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS intel_parcel_idx ON analytics.parcel_intelligence (parcel_id);
CREATE INDEX IF NOT EXISTS scores_parcel_idx ON analytics.suitability_scores (parcel_id);
CREATE INDEX IF NOT EXISTS reports_parcel_idx ON reports.reports (parcel_id);
CREATE INDEX IF NOT EXISTS api_logs_time_idx ON logs.api_logs (occurred_at);
CREATE INDEX IF NOT EXISTS audit_time_idx ON users.audit_log (occurred_at);

-- ============================================================================
-- END. Next steps: role/grant setup per environment, then the Master Data
-- Catalogue rows are loaded into metadata.sources / metadata.datasets by ETL.
-- ============================================================================
