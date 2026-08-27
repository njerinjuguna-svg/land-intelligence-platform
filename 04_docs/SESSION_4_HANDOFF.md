# LAND INTELLIGENCE PLATFORM — SESSION 4 HANDOFF (2026-08-08)

Paste this into a fresh chat, reconnect the project folder, and continue.

## Company / product (unchanged)

Geocode Spatial Solutions Ltd (Kenya). Product: Land Intelligence Platform (LIP),
a B2B white-label geospatial intelligence layer for land selling companies.
Buyers see parcel-level intelligence (soil, flood, terrain, proximity,
connectivity, suitability score out of 100). Revenue: SaaS (KES 25k to
120k/month), B2C reports (KES 500 to 5,000), API licensing. Core principle: the
product is the National Spatial Intelligence Database, not the frontend. All
analysis is parcel-level via spatial sampling of national layers. Clients upload
their own parcel boundaries; our database enriches them at upload time
(precomputed). Title verification (Ardhisasa) deferred. Phase 1 intelligence
engine, Phase 2 professional services, Phase 3 optional opt-in marketplace
(never scrape client listings).

**Working style:** build step by step together, Claude explains every step in
plain language because I am learning as we go, Claude writes files directly into
my project folder. No em dashes or hyphens as separators in writing.
Production-ready mindset, most recent and accurate data only. **Connect my
project folder at the start of every session.** Only use the best available
data; do not downgrade resolution to save time unless the source has no finer
version.

**Project folder:** `E:\Land Intelligence Platform Geocode\Land Intelligence Platform`

## Environment

PostgreSQL 16 + PostGIS 3.4, database `land_intelligence_kenya`. pgAdmin 4.
Python 3.12.7, VS Code, venv at `03_etl\venv`. `.env` in 03_etl holds
DB_PASSWORD. QGIS LTR connected to PostGIS.

Installed in venv: geopandas, sqlalchemy, geoalchemy2, psycopg2-binary,
python-dotenv, pandas, **rasterio 1.5.0**, **pysheds 0.5**, numpy 2.x, scipy,
scikit-image, numba.

To run any ETL: `cd 03_etl`, `venv\Scripts\activate` (prompt must show (venv)),
then `python etl_XX.py`.

## Schema

v1.0 (18 schemas, ~65 tables, every row has source_id, source_date, confidence
1-5, version, status, created_at, updated_at; rasters never in PostGIS, only
catalogued in `metadata.raster_catalog` as COG URLs; EPSG:4326 everywhere; GiST
+ B-tree indexes; update triggers). Updates applied: v1.1, v1.2
(environment.rivers.waterway_type), v1.3 (water_points.point_type). SQL in
`01_database`.

## Data catalogue

`02_data_catalogue\sources.csv` (48 sources) and `datasets.csv` (74 datasets),
loaded by etl_04. CSVs are the editable master; rerun etl_04 after edits.

## COMPLETED ETLs

Vector (sessions 1-3): etl_01 admin boundaries (47 counties, 290 subcounties,
1,425 wards), etl_02 OSM roads (730,006), etl_03 OSM water (46,529 rivers /
14,945 waterbodies), etl_04 catalogue loader, etl_05 country boundary,
etl_07 WPDx water points (21,953), etl_08 KMHFL health (12,403, ward centroid,
confidence 2), etl_09 WDPA protected areas (349), etl_10 schools (37,930),
etl_11 OpenCellID towers (142,279).

**Session 4 additions (this session):**

* **etl_12_riparian_buffers.py** (run 24 success): 41,862 riparian buffer
  polygons derived from environment.rivers, pure PostGIS, no download.
  Widths: river 30 m, stream 6 m, canal 6 m, **drain excluded**.
  Counts verified: 6 m band 35,287 (streams 35,071 + canals 216), 30 m band
  6,575 (rivers). Legal basis on every row: EMCA (Wetlands, Riverbanks,
  Lakeshores and Seashores) Regs 2009 (6 m min to 30 m max from high-water
  mark); Water (Resources) Regs 2025; Survey Regs Cap 299. Buffered from river
  CENTRE LINE (OSM has no channel width), geography-based so metres are real.
  Confidence 3. Verified in QGIS.
* **etl_13_copernicus_dem_download.py** (run 26 success): all 96 Copernicus
  GLO-30 tiles for Kenya from the AWS open-data bucket into
  `data/raw/terrain/copernicus_glo30`. stdlib only, resumable, chunked, retries.
* **etl_14_dem_mosaic.py** (run 27 success): national DEM
  `06_rasters/cog/terrain/terrain_dem_copernicus_glo30_2021.tif`, 32,400 x
  39,600 px (~1.28 billion), ~30.9 m, 3,507 MB COG. Memory-safe (empty canvas on
  disk, paste tiles one at a time). Catalogued variable='elevation',
  confidence 4 (DSM incl. canopy/buildings, not bare earth).
* **etl_15_terrain_slope.py** (run 29 success): slope, Horn 3x3, latitude-aware
  metres, strip processed. `terrain_slope_derived_glo30_2021.tif`.
  Stored **Int16 centi-degrees with a 0.01 scale tag** -> 1,984 MB (was 5,016 MB
  as Float32). Catalogued variable='slope', confidence 4.
* **etl_16_terrain_twi.py** (run 32 success): Topographic Wetness Index at ~90 m
  (interim flood proxy), via pysheds fill_pits/fill_depressions/resolve_flats/
  flowdir/accumulation. `terrain_twi_derived_glo30_90m.tif`, Int16 scale 0.01,
  254 MB. Catalogued variable='twi', confidence 3.
* **etl_17_isda_soils.py** (run 40 success for BOTH layers; pH being redone,
  see OPEN ITEMS): soils.ph and soils.texture from iSDAsoil, 30 m, CC-BY-4.0
  (commercial OK with attribution).
  - `soils_texture_class_isda_30m.tif` (114 MB) DONE and correct: classes 1-12,
    mean 5.82. Legend: 1 Clay, 2 Silty Clay, 3 Sandy Clay, 4 Clay Loam, 5 Silty
    Clay Loam, 6 Sandy Clay Loam, 7 Loam, 8 Silt Loam, 9 Sandy Loam, 10 Silt,
    11 Loamy Sand, 12 Sand. (Heavy clay = black cotton risk.)
  - `soils_ph_isda_30m.tif` (487 MB) written but **needs the rerun** to apply
    the impossible-value clamp.
* **etl_18_chirps_rainfall.py** WRITTEN BUT NOT YET RUN: mean annual rainfall
  1991-2020 (WMO normal) from CHIRPS annual Africa grids, ~5 km native, public
  domain. Probes 4 candidate URL patterns and reports which works. Sequential
  whole-file downloads (kind to a weak connection), resumable.

## Storage decision (session 4)

Rasters live in a **local folder**, `06_rasters/cog/{terrain,soils,climate,
satellite,demographics}/`, with `06_rasters/README.md` documenting the naming
convention `<domain>_<variable>_<source>_<resolution>_<period>.tif`. The database
only stores a POINTER (`metadata.raster_catalog.storage_url`), so moving to a
cloud bucket later is a copy-the-files-and-update-one-column job, not a rewrite.
Raw downloads stay in `03_etl/data/raw/<layer>/`; only cleaned COGs go in
`06_rasters/cog/`.

## HARD-WON LESSONS (do not relearn these)

1. **PostgreSQL hijacks PROJ.** PostgreSQL sets `PROJ_LIB` / `GDAL_DATA`
   system-wide to its own older copies, which breaks rasterio with
   "proj.db LAYOUT.VERSION ... is expected". **Every script that reprojects must
   do this BEFORE importing rasterio:**
   ```python
   for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
       os.environ.pop(_k, None)
   ```
2. **pysheds 0.5 predates NumPy 2.** It calls `np.in1d` etc. Cannot downgrade
   NumPy (rasterio needs 2.x). Use the compat shim at the top of etl_16
   (aliases in1d->isin, bool8, float_, int0, uint0, alltrue, sometrue).
3. **Big raster maths must be float32 and in place**, and free the upstream
   library's arrays (`del` + `gc.collect()`) before heavy numpy work, or you get
   MemoryError on a 1.28-billion-pixel grid.
4. **Noisy rasters do not compress as Float32.** Store as Int16 with a scale tag
   (e.g. 0.01) — slope went 5,016 MB -> 1,984 MB with no visible loss.
5. **Always print raw AND transformed value statistics for a new source, and
   sanity-check them before trusting.** This caught a wrong pH back-transform:
   I assumed iSDA's `exp(x/10)-1` (gave mean 7.6 million); the truth is the file
   stores **pH x 10**, so pH = raw/10, mean 7.04. Correct for Kenya.
6. **Reject, never squash, impossible values.** `clip()` turns nonsense into a
   plausible-looking wrong number. Mark it nodata instead. A buyer can handle a
   gap; they cannot handle a confident wrong answer.
7. **iSDA is not in lon/lat.** Its CRS is Web Mercator written as a `LOCAL_CS`
   PROJ cannot use. Force `src_crs="EPSG:3857"` then warp to 4326.
8. **Do not "optimise" a configuration that already works.** Raising strip size
   to 4096 and enabling `GDAL_HTTP_MULTIRANGE=YES` + merged ranges made etl_17
   stall for 2+ hours with no output. The working config is small strips
   (512-1024) and `GDAL_HTTP_MULTIRANGE=NO`.

## OPEN ITEMS / IMMEDIATE NEXT STEPS

### 1. THE STREAMING PROBLEM — needs the permanent fix below

`etl_17` (iSDA soils) reads Kenya's window remotely from an Africa-wide COG
through a `WarpedVRT`. This is painfully slow and unreliable on this connection
(hours, frequent truncated-tile errors, sometimes stalls). Downloading whole
files sequentially (etl_13 DEM tiles) works fine on the same connection.

**Diagnosis:** the reprojection is the problem, not the bytes. Reading in
EPSG:4326 while the source is EPSG:3857 makes GDAL request source blocks in a
scattered, non-sequential pattern — thousands of small random range requests,
each a chance to fail.

**PERMANENT FIX (implement first next session): separate FETCH from REPROJECT.**
1. Read Kenya's window in the source's NATIVE CRS (EPSG:3857) with no warp.
   Native-CRS windowed reads are contiguous and behave like a sequential
   download, which this connection handles well. Save that to a local file.
2. Reproject that small LOCAL file to EPSG:4326 on disk (fast, no network).
3. Then transform values, encode, COG, catalogue as now.

Keep the existing resume support (progress marker file), the per-strip progress
printing with ETA, and `GDAL_HTTP_MULTIRANGE=NO`. Apply this same
fetch-then-reproject pattern to every future remote-COG source.

Note the whole iSDA Africa file cannot be downloaded (328,563 x 289,306 px), so
a native-CRS windowed fetch is the right unit of work.

### 2. Finish soils.ph

Rerun after the fix: `python etl_17_isda_soils.py ph`. The clamp is already in
(reject pH outside 3.0-10.0 as nodata; previously max read an impossible 25.40).
Verify printed pH: expect min ~4.3, **max <= 10**, mean ~7.0. Texture is done
and correct; the `ph` argument skips it.

### 3. Run etl_18 rainfall

`python etl_18_chirps_rainfall.py`. Watch the URL probe (prints OK/no for 4
candidates) and the sanity check: ASALs ~150-400 mm, Nairobi ~900 mm, western
highlands ~1,200-2,000 mm.

### 4. Remaining P1 rasters

* `soils.soil_type` — **NOT an iSDA layer.** The catalogue defines it as a WRB
  taxonomy class; iSDA publishes soil PROPERTIES, not taxonomy. Take it from
  **SoilGrids** (ISRIC, 250 m, CC-BY-4.0, already registered as a source).
* `satellite.ndvi`, `satellite.landcover`, `satellite.builtup`
* `demographics.population` (WorldPop, zonal per ward). Prefer the Kenya-only
  file over a continental one.

### 5. Older follow-ups (from session 3, still open)

* Wards incomplete: 1,425 of 1,450 official (confidence 3). Replace with a
  complete 1,450-ward file as version 2 when found (must count 1,450 features).
  Ward codes NULL; backfill from IEBC. Verify Nakuru 55, Kiambu 60.
* Health: only 9 pharmacies loaded (expected many) — check the pharmacies CSV
  Facility_type_category / operational filter. Improve the 82% ward match with a
  ward-name alias table. Upgrade health to true GPS (kmhfr.health.go.ke or
  healthsites.io) to lift confidence above 2.
* Water points and towers assigned county by point-in-county; check for NULL
  county on coastal/border points.
* Licensing before commercial launch: OSM ODbL share-alike, OpenCellID CC-BY-SA
  share-alike, **WDPA non-commercial (use KWS primary for protected areas in the
  paid product)**, Communications Authority coverage maps, Kenya Power data.
  Cleared as commercial-safe: Copernicus GLO-30 (attribution), iSDAsoil
  (CC-BY-4.0), CHIRPS (public domain).
* Formatted xlsx version of the catalogue still pending.

## Attribution strings that must ship with the product

* Copernicus DEM: "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014
  and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the
  European Union and ESA; all rights reserved."
* iSDAsoil: "iSDAsoil © iSDA Africa, CC-BY-4.0; Hengl et al. 2021, Sci Rep
  11:6130."
* CHIRPS: "CHIRPS (Climate Hazards Center, UC Santa Barbara), public domain.
  Funk et al. 2015, Sci Data 2:150066."

## ROADMAP AFTER DATA

Enrichment engine (sample every layer per parcel at upload) -> suitability
scoring (score out of 100) -> REST API -> PDF reports -> admin portal -> buyer
dashboard -> first pilot client.

Realistic remaining effort to a functioning intelligence database (data complete
+ enrichment + scoring): roughly 5 to 8 working sessions. The product shell
(API, reports, portals) is a separate stretch beyond that.

## Build log

`04_docs/PROGRESS.md` is fully updated through session 4 and is the detailed
record. This file is the quick-start summary.
