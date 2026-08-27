# Land Intelligence Platform — Build Log

## Session 1 (2026-07-14)

### Done
1. Database land_intelligence_kenya created on local PostgreSQL 16 + PostGIS 3.4
2. Schema v1.0 executed: 18 schemas, ~65 tables, provenance columns everywhere,
   auto indexes and triggers (01_database/land_intelligence_schema.sql)
3. Schema v1.1 applied: full sales status ladder, automatic status audit
   trigger, composition/range intelligence fields, marketplace_opt_in
   (01_database/02_schema_update_v1.1.sql)
4. Master Data Catalogue: 48 sources + 74 datasets across 13 categories,
   with priorities and licensing flags (02_data_catalogue/)
5. Python 3.12 + venv + GeoPandas toolchain working in 03_etl
6. ETL 01 ran to success (run 6): 47 counties, 290 subcounties, 1,425 wards
   loaded with source registration and run logging

### Known issues / decisions
- Wards source is incomplete: 1,425 of 1,450 official wards (98.3%).
  Confidence downgraded to 3. Replace with a complete 1,450-ward file,
  loaded as version 2 (supersede, never delete).
- 11 wards initially unassigned to counties; fixed by largest-overlap
  spatial join (verify counts after running the UPDATE).
- Ward codes are NULL: file's PCODE was not unique per ward. Backfill
  from an authoritative IEBC list later.
- ETL run 1 manually closed as failed (predates failure logging).
- Licensing to resolve before commercial launch: OSM ODbL, OpenCellID
  CC-BY-SA, CA coverage maps, Kenya Power data, WDPA non-commercial.

### Next session
1. Install QGIS (qgis.org/download, Long Term Release version), connect to
   PostGIS (localhost, 5432, land_intelligence_kenya) and view the loaded data
2. If complete ward data found: load as v2 via ETL 01 rerun/adaptation
3. ETL 02: OSM road network for the 20 pilot counties
   (Geofabrik kenya-latest-free.shp.zip -> transport.roads)
4. Then: schools (MoE), health facilities (KMHFL), rivers, water points
5. Load catalogue CSVs into metadata.sources / metadata.datasets

### Verification results (session 1)
- 47/47 counties matched and loaded, geometry valid
- ETL audit trail intact: runs 1-5 failed with recorded reasons, run 6 success
- Ward counts vs official: Nakuru 54/55, Kiambu 56/60 (source gap, see above)

## Session 2 (2026-07-17)

### Done
1. Postgres password rotated (ALTER USER + .env updated)
2. QGIS LTR installed, PostGIS connection working, admin layers
   visually verified (counties/subcounties/wards styled as outlines,
   ward density matches settlement patterns, coastline clean)
3. ETL 02 ran to success (run 7): 735,889 OSM road segments read from
   Geofabrik extract (2026-07-16), 226 unmapped-class segments dropped,
   397,537 segments in the 20 pilot counties loaded into transport.roads
   (03_etl/etl_02_osm_roads.py)
4. SCOPE DECISION: switched from pilot-only to national loading.
   Both ETL scripts now carry a PILOT_ONLY flag (default False).
   Rationale: the product is a National Spatial Intelligence Database,
   and pilot-only loading breaks proximity queries near county borders.
5. ETL 02 rerun national (run 8): 730,006 road segments across all 47
   counties in transport.roads (~5,657 unmatched segments fall outside
   county polygons: border slivers, correct behaviour)
6. Schema v1.2 applied: waterway_type column on environment.rivers
   (01_database/03_schema_update_v1.2.sql)
7. ETL 03 ran to success (run 9): 46,529 waterway segments into
   environment.rivers + 14,945 waterbodies into environment.waterbodies,
   national. 3,383 wetland/riverbank polygons deliberately skipped,
   awaiting a dedicated wetlands ETL from a better source
   (03_etl/etl_03_osm_water.py)

### ETL 02 design decisions
- OSM fclass mapped to 9 schema road classes; track_grade1-5 -> track,
  footway/cycleway/steps/pedestrian -> path, service -> unclassified
- surface = 'unknown' for all rows: Geofabrik shapefile carries no
  surface attribute. Upgrade later from kenya-latest.osm.pbf surface tags.
- Confidence 4 for motorway..tertiary, 3 for minor roads
- Roads kept unclipped; county_code assigned via ST_Intersects against
  ST_Subdivide(128) pilot-county tiles, boundary crossers deduplicated
  by DISTINCT ON (first county alphabetically)
- Roads outside the 20 pilot counties are not loaded: RESOLVED same
  session by the national rerun (run 8), see scope decision above

### ETL 03 design decisions
- environment.rivers gets waterway_type (river/stream/canal/drain) from
  OSM fclass; river_class (perennial/seasonal) stays NULL until a
  hydrological source (WRA) provides it
- Waterbody classification heuristic: 'reservoir' maps directly; generic
  OSM 'water' polygons split by real-world area, >= 5 ha = lake, else
  pond. Confidence 3 reflects the inference.
- Wetlands, riverbanks, docks, glaciers skipped (3,383 polygons),
  wetlands get a dedicated ETL from a better source later

8. ETL 04 built (etl_04_load_catalogue.py): upserts sources.csv and
   datasets.csv into metadata.sources/metadata.datasets, marks the six
   already-loaded datasets as 'ingested', never downgrades live
   etl_status on rerun. FIRST RUN FAILED (run 10, logged): land.parcels
   row in datasets.csv was missing its update_frequency field, shifting
   values into wrong columns; CHECK constraint caught it. CSV row fixed
   ('on upload' added) and pre-load validation added to the script.
   RERUN PENDING: first task next session. Sources (48) committed;
   datasets rolled back cleanly by the transaction.

### Verification results (session 2)
- pgAdmin: 155 county x road_class combinations, distribution plausible
  (motorways only near Nairobi/Mombasa corridors)
- QGIS visual: roads cluster correctly, Lake Victoria/Turkana render,
  river network national, admin hierarchy styled and checked

## Session 3 (2026-07-18)

### Done
1. etl_04 catalogue loader FIXED and succeeded (run 13): 48 sources, 74
   datasets in metadata. Second malformed row (land.zoning, missing
   update_frequency) caught by the new pre-load validation and fixed.
   Added row validation against schema constraints before any insert.
2. etl_05 national boundary (run 16): admin.country built by dissolving
   the 47 counties (ST_Union), guarantees no seams between layers.
3. Both etl_02/etl_03 now carry PILOT_ONLY flag (default False, national).
4. Schema v1.3 applied: water_points.point_type gains 'other' and 'well'.
5. etl_07 WPDx water points (run 19): 21,953 points with GPS, national,
   typed borehole/well/water_kiosk/spring/other, functionality captured.
6. etl_08 KMHFL health (run 20): 12,403 operational facilities loaded.
   NO GPS in the openAFRICA export, so located to WARD CENTROID
   (confidence 2); 82% matched a ward. Attributes (KEPH level, ownership,
   MFL code, facility_type) are exact.
7. etl_09 WDPA protected areas (run 21): 349 areas with official names,
   classified national_park/national_reserve/conservancy/sanctuary/
   marine_protected, authority from manager. Replaced the abandoned OSM
   attempt.
8. etl_10 schools (run 22): 37,930 MoE schools with GPS (World Bank/KODI
   shapefile), 29,097 primary + 8,833 secondary, into social.education.
9. etl_11 OpenCellID towers (run 23): 142,279 cells (MCC 639) into
   connectivity.towers. Safaricom 120,833 / Airtel 19,840 / Telkom 1,482.
   Confidence 2 (crowdsourced positions). CC-BY-SA licensing flag.

ALL P1 VECTOR LAYERS COMPLETE. The accessibility + services half of the
product now answers: what surrounds the parcel, how accessible, are
schools/hospitals nearby, is water available, is internet available.

### Decisions / notes
- OSM free protected_areas layer ABANDONED: it has no name column
  (only osm_id/code/fclass), useless for a name-required table.
  Switched to WDPA (etl_09).
- WDPA is non-commercial: OK for build/test, resolve before commercial
  launch (secure KWS or clear WDPA terms). Known licensing issue.
- Health located at ward centroid is interim. Upgrade to true GPS from
  the live KMHFR portal or healthsites.io later; will lift confidence.

### Follow-ups / cleanup
- Health: only 9 pharmacies came through (expected many). Check the
  pharmacies CSV's Facility_type_category values / operational filter.
- Health ward match 82%: improve with ward-name alias table + the
  complete 1,450-ward file when found.
- Water points: county assigned by point-in-county; a few coastal/border
  points may be NULL county (check count).

### Verification results (session 3)
- metadata self-describes: SELECT priority, etl_status FROM
  metadata.datasets confirmed 6 ingested at start, now 10.
- P1 vector sweep: water_points, health, protected_areas, admin.country
  all loaded and marked ingested.

### Next session
1. THE RASTER PIPELINE (the big new architecture). P1 rasters: terrain.dem
   (Copernicus GLO-30) -> derive terrain.slope + terrain.twi; soils.ph /
   soils.soil_type / soils.texture (iSDAsoil); climate.rainfall (CHIRPS);
   satellite.ndvi / landcover / builtup. Rasters are NOT stored in PostGIS:
   convert to COG, put in object storage, catalogue URL in
   metadata.raster_catalog, then zonal-sample per parcel/ward at enrichment.
   Decide object storage (local folder for dev vs cloud bucket) first.
2. demographics.population (WorldPop) -> zonal stats per ward.
3. environment.riparian_buffers: derive from environment.rivers (statutory
   widths) - pure PostGIS, no download. Good quick win.
4. Cleanup: health pharmacies (only 9 loaded), health ward-match to 82%+,
   complete 1,450-ward file if found (load as v2).
5. Then: enrichment engine, suitability scoring (score/100), REST API,
   PDF reports, admin portal, buyer dashboard, pilot client.

## Session 4 (2026-07-24)

### Done
1. Project folder reconnected; Session 3 state confirmed intact (11 ETL
   scripts, 4 schema SQL files, both catalogue CSVs, all raw data, PROGRESS.md).
2. DECISION - raster storage: Option A, a LOCAL folder now, deliberately
   designed for a one-step move to the cloud later. Rationale: zero setup and
   zero cost while the raster architecture is still being proven, and because
   metadata.raster_catalog only stores a POINTER (storage_url), migrating to a
   bucket later is a copy-the-files-and-update-storage_url job, not a rewrite.
3. Created the raster store skeleton: 06_rasters/ with README.md and
   cog/{terrain,soils,climate,satellite,demographics}/. Raw multi-GB downloads
   stay in 03_etl/data/raw/<layer>; only cleaned COGs live in 06_rasters/cog/.
   Naming convention documented: <domain>_<variable>_<source>_<res>_<period>.tif.
4. QUICK WIN built (no download): etl_12_riparian_buffers.py derives
   environment.riparian_buffers from environment.rivers by statutory width.
   - Widths by OSM channel type: river 30 m, stream 6 m, canal 6 m,
     drain EXCLUDED (man-made drainage, not a natural watercourse).
   - Legal basis recorded on every row: EMCA (Wetlands, Riverbanks,
     Lakeshores and Seashores) Regs 2009 (6 m min - 30 m max from high-water
     mark); Water (Resources) Regs 2025; Survey Regs Cap 299.
   - Buffered from the river CENTRE LINE (OSM gives no channel width), using
     GEOGRAPHY so the width is real meters, not degrees. Confidence 3
     (rules-based approximation, not a surveyed boundary).
   - Idempotent full rebuild (this ETL is the only writer to the table);
     reuses the rivers' dominant source_id for honest provenance; logs to
     metadata.etl_runs; marks the dataset ingested on success.

### To run (Njeri, next time at the laptop)
- cd 03_etl, activate venv, `python etl_12_riparian_buffers.py`.
- Expected next run_id = 24 (last success was run 23). Report back: the
  per-width buffer counts the script prints, and the total.
- I cannot run this myself: it connects to your LOCAL PostgreSQL, which only
  exists on your machine.

### Verify after running
- pgAdmin: SELECT buffer_width_m, count(*) FROM environment.riparian_buffers
  GROUP BY 1;  -> expect a 30 m group (rivers) and a 6 m group (streams+canals),
  and ZERO buffers for drains.
- QGIS: buffers should hug the river network as thin corridors; spot-check a
  wide river and confirm the band looks ~30 m each side of the line.
- metadata.datasets: environment.riparian_buffers should now read 'ingested'.

### Notes / follow-ups
- Centre-line buffering slightly under-measures very wide rivers (reserve is
  legally from each BANK). Sharpen later if a surveyed channel-width or
  highest-flood-mark source arrives; rerun etl_12 to refresh.
- Canal at 6 m is a deliberate conservative flag (WRA obligations can attach
  to artificial channels). Easy to change: edit the WIDTHS dict at the top of
  etl_12 and rerun.
- Still open from Session 3: health pharmacies (only 9 loaded), health
  ward-match above 82%, complete 1,450-ward file if found (load as v2).

### Terrain raster pipeline - STARTED and DEM COMPLETE this session
5. etl_13_copernicus_dem_download.py (run 26 success): downloaded all 96
   Copernicus GLO-30 tiles covering Kenya from the AWS open-data bucket
   (copernicus-dem-30m) into data/raw/terrain/copernicus_glo30. Tiles chosen by
   filtering the bucket's tileList.txt against Kenya's admin.country bbox.
   stdlib only (no deps), resumable, streams in 256 KB chunks, retries on
   timeout, logs 'partial' if any tile still pending. FIRST RUN (24) crashed on
   a read-timeout mid-tile; fixed to catch TimeoutError + chunked streaming;
   rerun (26) completed 96/96.
6. LICENSING (good news): Copernicus GLO-30 is Full, Free & Open incl.
   COMMERCIAL use, attribution only. Notice recorded on the catalogue row:
   "produced using Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and
   (c) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by
   the European Union and ESA; all rights reserved."
7. TOOLING: installed rasterio 1.5.0 into venv (bundles GDAL; no separate GDAL
   install). numpy 2.5 already present.
8. etl_14_dem_mosaic.py (run 27 success): stitched the 96 tiles into ONE
   national DEM the memory-safe way (empty canvas on disk, paste tiles one at a
   time via windows, then COG-convert). Output:
   06_rasters/cog/terrain/terrain_dem_copernicus_glo30_2021.tif
   Canvas 32,400 x 39,600 px (~1.28 billion px), pixel ~30.9 m, 3,507 MB COG,
   DEFLATE+predictor3, average overviews. Catalogued in metadata.raster_catalog
   (variable='elevation', bbox envelope, md5 checksum, source=Copernicus DEM,
   confidence 4 - it is a DSM incl. canopy/buildings, not bare-earth DTM).
   metadata.datasets terrain.dem marked 'ingested'. Harmless NumPy 2.5
   DeprecationWarning on dst.write (rasterio internal), output verified correct.
9. etl_15_terrain_slope.py (run 29 success): slope in degrees via Horn 3x3 on
   the DEM, computed in EPSG:4326 with LATITUDE-AWARE pixel width (pixel height
   ~30.9 m constant; width = 30.9 m * cos(lat) per row). Windowed strip
   processing (1024-row strips, 1 px halo, boundless edges -> nodata), peak RAM
   ~1 GB. Output 06_rasters/cog/terrain/terrain_slope_derived_glo30_2021.tif.
   STORAGE FIX: first run (28) wrote Float32 = 5,016 MB (slope is noisy, barely
   compresses). Reran (29) as Int16 centi-degrees (0.01 deg precision) with a
   0.01 scale tag so QGIS still shows degrees, predictor=2 -> 1,984 MB. Same
   data, ~40% the size. Pattern: reuse this Int16+scale trick for future noisy
   rasters. Catalogued variable='slope', source=Geocode Spatial Solutions,
   confidence 4; terrain.slope marked 'ingested'.
10. etl_16_terrain_twi.py (run 32 success): Topographic Wetness Index at ~90 m
    (Njeri's choice), interim flood proxy. Pipeline: resample DEM 30m->90m
    (average, EPSG:4326) -> pysheds fill_pits/fill_depressions/resolve_flats/
    flowdir/accumulation -> slope (latitude-aware metres) -> TWI = ln(SCA/
    tan(slope)) with a MIN_SLOPE floor. Output
    06_rasters/cog/terrain/terrain_twi_derived_glo30_90m.tif, Int16 scale 0.01,
    254 MB. Catalogued variable='twi', source=Geocode, confidence 3 (proxy);
    terrain.twi marked 'ingested'.
    TWO FIXES on first runs, both dependency issues not logic:
    (a) pysheds 0.5 calls np.in1d, removed in NumPy 2.x (cannot downgrade NumPy,
        rasterio 1.5 needs 2.x). Added compat shim at top of script aliasing
        in1d->isin (+ bool8/float_/int0/uint0/alltrue/sometrue).
    (b) MemoryError on the slope maths (float64 full-country arrays + pysheds
        still holding its arrays). Fixed: float32, in-place ops, del+gc of
        pysheds objects first. Peak RAM ~2 GB.
    Reusable lessons: keep a NumPy-2 compat shim handy for older geo libs; do
    big raster maths in float32 and in place; free the upstream library's
    arrays before heavy numpy work.

TERRAIN TRIO COMPLETE: terrain.dem + terrain.slope + terrain.twi all built and
catalogued. First rasters in the platform. rasterio 1.5.0 + pysheds 0.5 now in
the venv.

### Soils raster domain - STARTED
11. etl_17_isda_soils.py (run 40 success): soils.ph + soils.texture from
    iSDAsoil, 30 m, CC-BY-4.0 (COMMERCIAL USE OK with attribution; attribution
    string stored on each catalogue row).
    METHOD - no bulk download: iSDA publishes ONE Africa-wide COG per property
    on public S3. We open it remotely via /vsicurl and read ONLY Kenya's window,
    warped to EPSG:4326 on the fly with WarpedVRT, streamed in 1024-row strips.
    Outputs: 06_rasters/cog/soils/soils_ph_isda_30m.tif (487 MB, Int16 scale 0.1)
    and soils_texture_class_isda_30m.tif (114 MB, Byte classes 1-12, 0=nodata).
    Both catalogued; soils.ph + soils.texture marked 'ingested'.
    Texture legend: 1 Clay, 2 Silty Clay, 3 Sandy Clay, 4 Clay Loam, 5 Silty
    Clay Loam, 6 Sandy Clay Loam, 7 Loam, 8 Silt Loam, 9 Sandy Loam, 10 Silt,
    11 Loamy Sand, 12 Sand. (Heavy clay = black cotton risk for foundations.)
    THREE FIXES needed, all worth remembering:
    (a) Kenya window came back 0x0: iSDA is NOT in lon/lat. Its CRS is Web
        Mercator but written as a LOCAL_CS PROJ cannot use, so we force
        src_crs='EPSG:3857' and warp to 4326 via WarpedVRT.
    (b) CRSError "proj.db LAYOUT.VERSION too old": PostgreSQL sets PROJ_LIB /
        GDAL_DATA system-wide to ITS older copies, hijacking rasterio. Fix: pop
        PROJ_LIB/PROJ_DATA/GDAL_DATA from os.environ BEFORE importing rasterio.
        *** This will affect every future reprojecting script on this laptop. ***
    (c) Truncated remote tile reads (TIFFReadEncodedTile / strile errors) on a
        flaky link. Fix: GDAL_HTTP_MULTIRANGE=NO + retries, plus our own retry
        loop that REOPENS the remote file fresh per attempt (a dropped tile
        leaves the connection stale; reusing it keeps failing).
    pH BACK-TRANSFORM CORRECTED EMPIRICALLY: assumed iSDA's exp(x/10)-1 and the
    printed stats exposed it as nonsense (mean 7.6 million). Raw values are
    43..254 mean 70.4, i.e. the file stores pH x 10 -> pH = raw/10, mean 7.04.
    Lesson: always print raw + transformed stats and sanity-check before trusting.

### Follow-up (soils, minor)
- soils.ph max reads 25.40 pH, which is impossible (scale is 0-14). A few edge
  pixels sit just below the 255 nodata marker. Add a clamp: treat pH > 10 (and
  < 3) as nodata, then rerun etl_17. Cosmetic now, but it would distort any
  average-pH statistic computed later.
- soils.soil_type still PENDING and is NOT an iSDA layer: the catalogue defines
  it as a WRB taxonomy class, which iSDA does not publish (they publish soil
  PROPERTIES). Take it from SoilGrids (ISRIC, 250 m, CC-BY-4.0, already
  registered as a source) as its own ETL.

### Verify (terrain)
- QGIS: add terrain_dem_copernicus_glo30_2021.tif -> whole-country relief,
  bright highlands (Mt Kenya, Aberdares, Rift shoulders), dark coast/Turkana.
- pgAdmin: SELECT name, variable, pixel_size_m, storage_url FROM
  metadata.raster_catalog; one 'elevation' row pointing at the COG.

### Next session
1. DONE so far: riparian buffers, terrain trio (DEM/slope/TWI), soils pH +
   texture. REMAINING P1 rasters: soils.soil_type (from SoilGrids, NOT iSDA,
   see soils follow-up above), climate.rainfall (CHIRPS), satellite
   (ndvi/landcover/builtup), demographics.population (WorldPop, zonal per ward).
2. Small cleanup: clamp impossible pH values (>10) in etl_17 and rerun.
3. Carry the naming + catalogue discipline from 06_rasters/README.md.
4. Still open: health pharmacies (9 loaded), health ward-match >82%,
   complete 1,450-ward file if found (load as v2).

---

## Session 5 (2026-08-08)

### Done
- **etl_17 rewritten (v2): the fetch-then-reproject fix.** The streaming
  problem carried over from session 4 is SOLVED. soils.ph reingested cleanly
  (runs 46 and 47).
- **etl_18 hardened and run (run 48): climate.rainfall COMPLETE.** All 30
  CHIRPS annual grids 1991-2020, catalogued, verified.
- **verify_18_rainfall.py written**: a read-only verification script that
  checks the rainfall layer against 16 towns with documented climatology.

### The streaming problem: diagnosis and permanent fix
The session 4 symptom was that reading Kenya's window from the Africa-wide
iSDA COG took hours, threw constant truncated-tile errors and sometimes
stalled outright, while plain sequential downloads on the same connection
(etl_13, 96 DEM tiles) were fine.

**Cause: the reprojection, not the bytes.** v1 opened the remote file through
a WarpedVRT and read in EPSG:4326 while the source is EPSG:3857. Those grids
do not line up, so to return one row of lon/lat pixels GDAL had to gather
scraps of source pixels from many places at once. Every read became thousands
of small scattered range requests, and on a weak link each one is another
chance to fail.

**Fix: separate FETCH from REPROJECT.**
- STAGE A (network): read Kenya's window in the source's OWN grid, no warp.
  Contiguous bytes, behaves like a sequential download. Saved to
  `03_etl/data/raw/soils/native_ph_3857.tif`.
- STAGE B (local, no network): reproject that local file to EPSG:4326 and
  apply the value transform in the same pass. Cannot drop a tile.
- STAGE C: stats, COG, catalogue. Unchanged.

**Result, measured:** stage A pulled 1,137 million pixels in 53 minutes at a
steady ~700 rows/min with 4 hiccups, all recovered on retry. Stage B took
6 minutes at ~5,900 rows/min. Total under an hour, versus hours of stalling.

**Apply this pattern to EVERY future remote-COG source.** It is the general
lesson, not an iSDA quirk. Next candidates: SoilGrids, any Sentinel or
Landsat derived COG.

The native download is KEPT on disk on purpose. If the encoding or a
transform rule ever changes, stage B reruns in minutes with zero download.

### soils.ph FINAL (run 47)
- `soils_ph_isda_30m.tif`, 443 MB COG, 29,694 x 37,475 px at ~30 m.
- Int16 storing pH x 10 with a 0.1 scale tag. Nodata -32768.
- **Verified: min 4.20, max 9.90, mean 7.03.** Raw source across the whole
  layer: min 42, max 102, mean 70.3, confirming iSDA stores pH x 10.
- Impossible values REJECTED not clipped: raw 102 (pH 10.2) went to nodata
  while 4.2 was correctly kept as a real acidic highland value.
- Confidence 3. Catalogued, dataset marked ingested.

### NEAR MISS worth remembering: the stale resume
Run 46 printed `RESUMING at row 30720 of 37475` in stage B. It had inherited a
half-finished working file from an ABORTED v1 attempt whose grid dimensions
happened to match, so nothing errored. Only the last 18% of that raster came
from the new clean code path. The statistics looked entirely plausible
(min 4.30, max 10.00, mean 6.97) and it was catalogued as success.

We rejected it and reran stage B from the local native file. The clean run
gave min 4.20, max 9.90, mean 7.03 and a 443 MB COG versus 364 MB, proving
the two files were genuinely different content.

**Fix applied:** progress markers now carry a fingerprint, `rows|width|height|
stage_tag`, instead of a bare row count. A leftover from different code or a
different grid is refused with a printed message. Stage A accepts a legacy
bare count (the fetch geometry has not changed, and honouring it saves a 53
minute redownload); stage B never does, because it is local and cheap to redo.
Bump STAGE_A_TAG / STAGE_B_TAG whenever the logic that fills a stage changes.

**The principle:** a resume marker is a promise that the rows below it are
good. Only code that can honour that promise may write one. Plausible
statistics are not provenance.

### climate.rainfall COMPLETE (run 48)
- `climate_rainfall_chirps_5km_1991-2020.tif`, 44,972 bytes, 164 x 206 px at
  ~5.6 km, Int16 mm/year, nodata -9999. Confidence 3.
- Live URL pattern (first probe candidate hit):
  `https://data.chc.ucsb.edu/products/CHIRPS/v3.0/annual/africa/tifs/chirps-v3.0.{y}.tif`
- All 30 years 1991-2020 downloaded, ~5.9 MB each, sequential, no failures.
- Kenya only: min 167 mm, max 3,492 mm, mean 681 mm. Padded box mean 712 mm.
- 2,034 nodata pixels = Indian Ocean and lake surface. CHIRPS masks water.
- A 0.045 MB file is CORRECT at 5 km. etl_18 printed "0.0 MB" purely from
  `.1f` rounding. No overviews is also correct: the raster is smaller than one
  tile, so GDAL declines to build pyramids.

### etl_18 hardening (three fixes before it was ever run)
1. **Grid mismatch was unchecked.** It cut Kenya's window once from the first
   year then reused those pixel OFFSETS for all 30 files. Valid only if every
   file shares a grid. Had CHIRPS served one year from the global folder and
   the rest from africa, the same offsets would point at a different part of
   the planet and we would have averaged Kenya with somewhere else, producing
   a map that looks perfectly normal and is wrong. Every year is now checked
   against the reference grid (`transform.almost_equals`, width, height) and a
   mismatch stops the run.
2. **It clipped instead of rejecting.** `np.clip(..., 0, 32000)`, the exact
   instinct that burned us on pH. Now averages above 15,000 mm/year become
   nodata with a printed count. (None occurred.)
3. **It would have labelled a partial average a 30-year normal.** Old code
   accepted as few as 10 years and still catalogued "1991-2020 normal". Now it
   refuses below 25 years, warns loudly above 25, and the catalogue name and
   temporal_start/end record the years ACTUALLY averaged.

### Verification results (session 5)
Rainfall, via `verify_18_rainfall.py`:
- **Correlation 0.983** across 16 towns spanning 200 to 1,900 mm. The layer
  ranks wet and dry places correctly, which is what suitability scoring rests
  on.
- The 3,492 mm maximum is NOT an artefact. Top 4 pixels cluster at lon
  37.87-37.98, lat 0.225-0.275 (Nyambene range), 3x3 neighbourhood mean
  2,859 mm. Pixels 5-10 form a second cluster at lon 37.32-37.43, lat
  -3.02 to -3.12 (northern flank of Kilimanjaro above Loitokitok). Both are
  where orographic maxima belong. An artefact does not form two mountains.
- **Caveat: the layer runs wet.** 14 of 16 towns read high, average +145 mm.
  Consistent with CHIRPS over steep East African terrain where gauge density
  is thin. BUT part of that gap is our reference figures, which were
  approximate, not station records (Machakos is nearer 800-900 than the 700
  used; Kitale nearer 1,200 than 1,100). Do not treat +145 mm as calibrated.
  **Record this caveat wherever rainfall feeds a buyer-facing number.**
- **Discard the ASAL cross-check in that script.** It predicted 75-85% of
  Kenya under 700 mm and got 66.1%. That is a badly designed test, not a
  failure: Kenya's ASAL classification uses an aridity index built from
  rainfall AND potential evapotranspiration, not a raw rainfall cutoff.

### HARD-WON LESSONS ADDED THIS SESSION
9. **Separate FETCH from REPROJECT for every remote COG.** Read the window in
   the source's native CRS first, save locally, then reproject on disk.
   Warping across the network turns a download into thousands of scattered
   range requests.
10. **Never assume a source's CRS when you can measure it.** etl_17 v2 checks
    how wide the file is in its own units (Africa is ~80 degrees but ~9.86
    MILLION metres, so there is no ambiguity) and picks the CRS from that.
    Confirmed at runtime: "file spans 9,856,890 units across". Getting this
    wrong would silently fetch the wrong patch of the planet.
11. **A resume marker must be fingerprinted, never a bare row count.** See the
    near miss above.
12. **NumPy 2 scalars must be cast to plain Python before they touch SQL.**
    `src.xy()` returns np.float64, and psycopg2 sends it to Postgres as its
    repr, `np.float64(37.925)`, which the server parses as schema "np".
    Error: `InvalidSchemaName: schema "np" does not exist`. Wrap in `float()`.
    Same applies to np.int64 into any query parameter.
13. **Declare nodata explicitly when the header omits it.** iSDA marks empty
    pixels 255 but does not always declare it. A bilinear warp with undeclared
    nodata averages 255 into real pixels along coastlines and invents values
    that never existed.
14. **Design cross-checks you can actually interpret.** The ASAL check above
    compared a rainfall threshold against an aridity-index statistic and could
    never have lined up. A test that cannot fail cleanly is not a test.

### satellite.landcover COMPLETE (run 49)
- `satellite_landcover_esaworldcover_10m_2021.tif`, 886 MB COG,
  96,430 x 121,573 px (11.72 billion). ESA WorldCover 2021 **v200** (v100 is
  the older, weaker 2020 map: do not use it). Confidence 4.
- Already EPSG:4326 and already COG, so NO reprojection: 12 tiles of 3x3
  degrees downloaded whole and sequentially, ~1.2 GB total. Mosaic took
  8.3 minutes.
- **Pixel size is 9.28 m, not 10 m.** The grid is 1/12000 of a degree. ESA
  markets it as "10 m". We catalogue the real figure.
- Nodata 0. Overviews built with **NEAREST** (see lesson 15).

**Structural change from etl_14, needed because this mosaic is COMPRESSED:**
etl_14 pasted tiles in one at a time. That cannot work here. A 3 degree tile
is 36,000 px wide, blocks are 512, and 36,000 is not a multiple of 512, so
tile edges fall mid-block and neighbouring tiles both write into the same seam
blocks. For a compressed file GDAL must then decompress, merge and recompress
on the second visit. etl_14 got away with it because its scratch file was
uncompressed; uncompressed this canvas is ~12 GB. So etl_19 sweeps the CANVAS
in horizontal bands instead, gathering whichever tiles overlap each band and
writing every block row exactly once, in order. Peak memory ~49 MB.

### satellite.builtup COMPLETE (run 50)
- `satellite_builtup_ghsl_92m_2020.tif`, 40 MB COG, 9,644 x 12,158 px.
  GHS-BUILT-S R2023A, epoch 2020, 3 arcsec, EPSG:4326 native. Confidence 4.
- Tiles R9_C22, R9_C23, R10_C22, R10_C23 (10 degree grid, probed before
  downloading). Kenya total 3,054 km2 built = 0.52% of the country.
- **Stored as SQUARE METRES per cell, NOT a percentage.** Two reasons, both
  load-bearing: (a) in EPSG:4326 cell area shrinks away from the equator, so
  converting here would bake one assumed cell size in forever; (b) square
  metres ADD, percentages do not, and the enrichment sums over a 1 km
  neighbourhood then divides by that neighbourhood's true area.
- **Resolution is 92 m, a deliberate departure from the catalogue's "10 m".**
  GHSL's 10 m product exists only in Mollweide and would mean reprojecting a
  global grid to compute a statistic that is explicitly averaged over a
  kilometre. WorldCover already answers "is this exact spot built" at 10 m.
- **Epoch 2020 is the last OBSERVED epoch.** R2023A also ships 2025 and 2030,
  which are MODELLED PROJECTIONS. We do not sell a forecast as a measurement.
  A future satellite.urban_growth (P2) should be E2020 minus E2015, both
  observed.

**CELL AREA / THE 101% PROBLEM (must be honoured by the enrichment engine):**
The observed saturation value is **8,606 m2**, against 8,548 m2 computed on
the WGS84 ellipsoid (100.7%) and 8,586 m2 on the authalic sphere (100.2%).
GHSL is computed on an equal-area Mollweide grid and regridded to lat/lon, so
its cell does not match a naive lat/lon calculation. Under 1% is harmless on a
map and NOT harmless in a buyer-facing number: divide by the wrong constant
and a parcel reads "101% built".
**Rule: use 8,606 m2 as a full cell and CAP the fraction at 1.0.**

### GHSL vs WorldCover: they disagree, and that is correct
GHSL 0.52% of Kenya built vs WorldCover's Built-up class at 0.32%. They
measure different things. WorldCover asks "is this 10 m patch built-up LAND"
and is known to miss sparse rural buildings, the same conservatism that makes
its cropland read low. GHSL measures building SURFACE and catches scattered
structures that never form a whole 10 m patch. GHSL being higher is the
expected direction; GHSL lower would have been the surprise.
**Product rule: WorldCover says what a parcel IS, GHSL says how developed its
surroundings ARE. Never present them as two measurements of one quantity.**

### Verification results (landcover and built-up)
`verify_19_landcover.py`, `verify_20_builtup.py`, both read-only.

Land cover:
- **Mangrove alignment test PASSED decisively.** 6,775 mangrove pixels inside
  Kenya, longitude 39.196 to 41.284, latitude -4.675 to -1.876, which is the
  coastline from Vanga to Kiunga. **Zero inland.** Mangroves need tidal
  saltwater, so this is a biological constraint we do not control, and a
  tile-shifted mosaic cannot produce it. This is the strongest alignment
  evidence available for a categorical layer.
- 12 of 12 landmarks correct over a ~1.9 km neighbourhood. Mt Kenya summit
  returned 6% Snow and ice (the last glacier remnants, at 10 m, on the
  equator). Kakamega Forest 96% Tree cover. Turkana and Victoria 100% water.
- Kenya-clipped shares: Shrubland 47.98%, Grassland 31.20%, Tree cover 9.22%,
  Cropland 4.46%, Bare 4.55%, Water 2.13%, Built-up 0.32%, Mangroves 0.03%.
- **CROPLAND READS LOW (4.46%) AND THIS IS A PRODUCT-LEVEL CAVEAT, not a
  defect to fix.** WorldCover's cropland class under-detects smallholder
  mosaic farming, which is most of Kenyan agriculture: small mixed plots with
  scrub and trees between them classify as shrubland or grassland. **Never
  tell a buyer "this is not farmland" on the strength of this layer alone.**
  NDVI sees the growing season directly and is the layer that answers it.

Built-up:
- **County ranking BY SHARE passed emphatically:** Nairobi 14.17%, Kiambu
  5.20%, Kakamega 4.16%, Murang'a 3.74%, Bungoma 3.04%. Nairobi leads by
  nearly 3x.
- Point checks with a 1 km neighbourhood: Nairobi CBD (Moi Avenue) 39.0% cell
  / 38.6% over 1 km / 64.0% peak; Nakuru 39.1 / 39.6 / 56.0; Mombasa 35.9 /
  29.3 / 54.0; Eldoret 28.7 / 25.3 / 48.1. Lake Turkana, the Chalbi and the
  Maasai Mara all **exactly 0.0%** on all three measures.
- Uhuru Park is retained in the script as a CONTROL: 3.2% at the cell but
  23.7% over 1 km. A layer that reports green space as unbuilt in the middle
  of a capital is behaving correctly.
- Note GHSL rarely saturates a cell even downtown (Nairobi 1 km peak 64%),
  because it measures roof footprint and streets, yards and parking are not
  roof. The 8,606 m2 saturation value is still the right divisor.

### HARD-WON LESSONS (continued)
15. **Categorical rasters: overviews MUST use NEAREST.** Averaging class codes
    invents classes. The mean of Built-up (50) and Bare (60) is 55, which is
    not a class, and a zoomed-out map fills with codes that do not exist. This
    also has a happy consequence: because the overviews are a SUBSAMPLE of
    real codes rather than an average, class proportions survive, so national
    statistics can legitimately be computed from an overview instead of from
    11.7 billion pixels.
16. **A compressed mosaic must be written by sweeping the CANVAS, not the
    tiles**, unless tile edges happen to align with block boundaries. See the
    etl_19 note above.
17. **MY VERIFICATION TESTS WERE THE WEAK LINK THIS SESSION, NOT THE ETLs.**
    Three separate times a test "failed" and the layer was fine, always for
    the same underlying reason: the test was framed against the wrong
    denominator or the wrong precision.
      - Rainfall: compared a rainfall threshold against an ASAL statistic that
        is defined by an aridity index including evapotranspiration.
      - Land cover: compared bounding-box shares against country expectations,
        when 38% of the box is not Kenya.
      - Built-up: ranked counties by ABSOLUTE built area, which measures
        county size. Kitui is 30,496 km2 and Nairobi is 696 km2.
    **A verification test needs the same design rigour as the ETL it checks.
    Before believing a failure, check the test.** And prefer tests that can
    only pass for one reason (mangrove geography, Nairobi leading by share)
    over tests that ask whether numbers look sensible.
18. **Do not probe a raster with a single pixel and a coordinate from
    memory.** Lamu Old Town, Kericho town and Uhuru Park all "failed" because
    the coordinate landed on a town centre or a park rather than the feature
    named. At 10 m, being 300 m out puts you in a different land cover
    entirely, and the test then measures the analyst's geography rather than
    the data. Summarise a neighbourhood instead: it tests the same thing and
    tolerates the imprecision actually present in the question.

### demographics.population COMPLETE (run 51)
- `demographics_population_worldpop_100m.tif` (55 MB COG) catalogued, AND the
  actual deliverable: 47 county + 1,425 ward rows in
  `demographics.population_stats`. Confidence 3.
- WorldPop 2020 **constrained** (maxar_v1), chosen because the unconstrained
  product spreads people across land with no buildings, which would place
  phantom residents beside a plot we are scoring.
- 1,425 wards processed in 14 seconds. **Wards captured 99.9% of the national
  raster total**, so the ward layer has almost no spatial gaps.

**MY REASONING ON UN-ADJUSTMENT WAS WRONG, corrected in the script header.**
I defaulted to the NON-UN-adjusted file believing it was the census-consistent
one. Measured:
    non-UN-adjusted : 55,201,278  (+16.1% vs 2019 census)
    UN-adjusted     : 53,771,300  (+13.0%)
    2019 KNBS census: 47,564,296
The non-adjusted file is NOT census-calibrated; it is WorldPop's own model and
it is FURTHER from the census. Difference between the two is only 2.7%, so
neither rescues us.

**County correlation 0.9123, and it is dominated by two counties:**
Mandera +209%, Garissa +86%, Turkana +34%; the other seventeen mostly within
20%. Both sides are contestable: WorldPop over-allocates in arid pastoral
areas where scattered manyattas and refugee settlements read as dense
structure, AND the 2019 census results for Mandera, Wajir and Garissa were
formally contested. Do not assert either is simply right.

**THE FIX IS ARCHITECTURAL, NOT A RESCALE.** KNBS is tier 1 in our catalogue
and WorldPop is tier 3. Admin-level population should come from the official
census table, with WorldPop supplying only the DISTRIBUTION inside each unit.
That is what dasymetric mapping is for. **Until KNBS census is loaded, treat
absolute population figures as indicative and prefer relative comparisons
("more people near plot A than B") over absolute claims.** Do NOT rescale the
grid to the census: that buries a real disagreement inside a number that then
looks authoritative.
**Ward codes: all 1,425 wards have NULL ward_code, so rows carry provisional
`LIP-W<id>`. These MUST be migrated when IEBC codes load. Search 'LIP-W'.**

### soils.soil_type COMPLETE (run 53)
- `soils_soil_type_soilgrids_250m.tif`, 3.7 MB COG, 3,886 x 4,892 px at
  ~232 m. SoilGrids v2.0 WRB most probable Reference Soil Group. Confidence 3.
- Kenya-clipped shares: Cambisols 21.42%, Luvisols 17.43%, Solonetz 14.03%,
  Leptosols 12.33%, **Vertisols 11.16%**, Acrisols 3.77%, Ferralsols 3.67%,
  Lixisols 3.54%, Andosols 3.54%, Nitisols 1.21%.

**RUN 52 FAILED AND THE FAILURE WAS THE POINT.** I asserted in the docstring
that SoilGrids is served in Interrupted Goode Homolosine, converted Kenya's
bounds to metres, and looked them up in the source grid. The endpoint actually
reports **EPSG:4326** at 172,800 x 67,200 px (1/480 degree, ~232 m). Metre
coordinates near 1,500,000 fall outside a raster whose axes run to 180, so the
window came out empty and the empty-window guard stopped the run.
This is lesson 10 (never assume a CRS, measure it) which I WROTE in etl_17 and
then did not apply. The script now asks the file, and because the source is
already lon/lat, stage B **clips instead of warping**, so class codes are never
resampled at all. The projected path and the interruption guard are retained
for ISRIC endpoints that still serve Homolosine.

**Legend verified by physics, not trusted.** Codes 0-29 alphabetical. The
script checks for soils that cannot occur in Kenya (Cryosols form in
permafrost; Albeluvisols, Podzols, Chernozems, Kastanozems are boreal or
temperate) and refuses to catalogue above 1%. Result: **0.000%**. If the
mapping were shifted one position, the common Kenyan groups beside them would
spill in and light it up.

### THE BEST VERIFICATION WE HAVE RUN: two producers, one reality
`verify_22_soiltype.py` cross-checks SoilGrids Vertisols against iSDA texture.
These are different organisations, different satellites, different methods,
and neither knows the other exists. A Vertisol is DEFINED by shrink-swell
clay, so the two must agree about where the heavy ground is.

    texture class      Vertisols   elsewhere
    Clay Loam              28.9%       15.0%     ~2x enriched
    Sandy Clay Loam        64.0%       58.6%
    Sandy Loam              1.8%       18.5%     ~10x DEPLETED
    mean texture class      5.32        6.03     +0.71 toward clay
    any clay-bearing       96.7%       78.8%     1.23x

**PASS.** The tenfold depletion of Sandy Loam under Vertisols is the decisive
number. There is no mechanism by which two independent products are wrong in
the same direction by accident.

**Caveat to carry into the product:** the shift is real but moderate, because
SoilGrids publishes the MOST PROBABLE class and most-probable classification
favours common classes over rare ones. That is why Cambisols, a
weakly-developed catch-all, takes 21% of Kenya and Nitisols only 1.21%.
Dependable for a strong signal like "Vertisol present"; not for fine
agricultural distinction on its own.
**Known miss: SoilGrids maps the Athi-Kapiti plains as Luvisols, not
Vertisols, on two separate probes.** Those plains are classic black cotton AND
they are where Nairobi peri-urban land selling is most active, i.e. exactly
our buyers. iSDA texture still reads Clay Loam there. **The enrichment engine
must treat black cotton risk as a signal from BOTH layers, never either
alone.**

### LESSON 19: I KEPT TELLING THE DATA WHAT IT SHOULD CONTAIN
Four verification tests "failed" this session while the layer was fine, always
the same root cause: the expectation was written before looking at the data.
  1. Rainfall: a rainfall threshold compared against an ASAL statistic that is
     defined by an aridity index including evapotranspiration.
  2. Land cover: bounding-box shares judged against country expectations, when
     38% of the box is not Kenya.
  3. Built-up: counties ranked by ABSOLUTE built area, which measures county
     size (Kitui 30,496 km2 vs Nairobi 696 km2). By SHARE, Nairobi leads at
     14.17%, nearly 3x the next county.
  4. Soil type: "heavy clay" defined as texture classes 1-3 from the class
     NAMES, when only ~5% of Kenya is in those classes and the national mean
     is 5.82. A threshold almost nothing meets cannot discriminate.
Plus five coordinate errors probing single pixels (Lamu town, Kericho town,
Uhuru Park, Chalbi fringe, a point inside Lake Turkana).

**The ETLs were careful because I kept asking the data what it contained. The
tests were careless because I kept telling the data what it should contain.**

RULES NOW IN FORCE:
  - **Print the background distribution BEFORE setting any threshold.**
  - Normalise before ranking: share, not total, unless size IS the question.
  - Clip to the country before comparing against country figures.
  - Never probe a raster with one pixel and a remembered coordinate; summarise
    a neighbourhood.
  - Prefer tests that can only pass for one reason (mangroves cannot grow
    inland; Vertisols cannot be sandy) over "do these numbers look sensible".
  - Before believing a failure, check the test.

### satellite.ndvi COMPLETE (run 54)
- `satellite_ndvi_s2geomedian_38m_2024.tif`, 1,400 MB COG, 23,566 x 29,666 px
  at ~38 m. Int16 scale 0.0001. Confidence 4.
- Source: DE Africa **gm_s2_annual** Sentinel-2 geomedian, **2024**, found via
  the STAC API (135 tiles), read at 1/4 resolution from the COG overviews.
  38.2 minutes for 1,210 MB. NDVI computed by us as (B08-B04)/(B08+B04).
- NDVI min -0.777, max 0.925, **mean 0.331**.
- Chose Sentinel-2 over DE Africa's own Landsat NDVI climatology on ISRIC...
  on DE AFRICA's own advice: their spec warns the 1984-2020 baseline is poor
  over equatorial Africa (sparse Landsat 5, persistent cloud) and should not
  be used where clear-observation counts are under ~30. Kenya IS equatorial
  Africa.
- STAC discovery instead of guessing a tile grid. After three hardcoded-layout
  failures this session, this one worked first time.
- Grid alignment solved in ADVANCE this time: canvas snapped to the 96 km tile
  grid with 480 px blocks (96,000 m / 40 m = 2,400 px, and 2,400 / 480 = 5), so
  no tile ever writes into a block another tile touched.
- Guard worth keeping: where both bands are zero the NDVI denominator is zero,
  and 0/0 means "no observation", NOT "no vegetation". Those become nodata.
  Getting it wrong would paint every gap as barren.

### VERIFICATION: the ordering test, and the hole NDVI was built to close
`verify_23_ndvi.py`. Two tests, deliberately sequenced so the first validates
the second: a MISPLACED NDVI layer would also show "unexpected greenness in
shrubland", for entirely the wrong reason.

**Test 1, mean NDVI by WorldCover class, PASSED with a perfect ordering:**

    Permanent water  -0.255
    Bare / sparse     0.094
    Grassland         0.280
    Shrubland         0.357
    Cropland          0.501
    Tree cover        0.662

Physics demands that ordering. Two organisations, different sensors, exact
agreement. Mangroves 0.598 and Herbaceous wetland 0.344 also land correctly.

**Test 2, the reason this layer exists.** Threshold DERIVED from the data: the
25th percentile of WorldCover's own cropland is NDVI 0.424.

    Shrubland  284,091 km2  ->  74,312 km2 (26.2%) as green as cropland
    Grassland  184,646 km2  ->  36,932 km2 (20.0%)
    WorldCover mapped cropland: 26,387 km2
    Shrub/grass as green as cropland: 111,245 km2 = 4.2x the mapped cropland

**Green does not prove cultivated** (wet rangeland and dense bush are green
too), so 111,245 km2 is an UPPER BOUND on missed farmland, not a measurement.
What it settles is that land cover alone cannot adjudicate farmability.
**PRODUCT RULE: never tell a buyer "not farmland" from land cover alone. Use
NDVI plus rainfall plus soil. Land cover describes the surface; it does not
adjudicate potential.**

**LIMITATION TO CARRY FORWARD: this is a SINGLE YEAR (2024), not a normal.**
Spot checks read green for dry places (Kitui shrubland 0.553, Maasai Mara
0.537), which is consistent with 2024 being a wet year in Kenya after the
2020-2023 drought. We applied 30-year averaging to rainfall for exactly this
reason and did not apply it here. The enrichment engine must NOT treat NDVI as
a stable baseline. A multi-year composite (median of several annual geomedians)
is the correct fix and should be a P2 follow-up.

### P1 STATUS: 23 of 27 COMPLETE, 4 OUTSTANDING
Checked against `02_data_catalogue/datasets.csv`, not memory.

DONE (23): admin.country, admin.counties, admin.wards, transport.roads,
utilities.water_points, social.education, social.health,
environment.protected_areas, environment.rivers, environment.riparian_buffers,
terrain.dem, terrain.slope, terrain.twi, climate.rainfall, soils.soil_type,
soils.ph, soils.texture, satellite.ndvi, satellite.landcover,
satellite.builtup, demographics.population, connectivity.towers.

OUTSTANDING (4):
1. **demographics.nightlights** (P1, VIIRS, zonal per ward). ACTIONABLE NOW.
   Free from the Earth Observation Group. The catalogue notes "trend is the
   development signal", so this wants several annual epochs, not one.
   This pairs directly with satellite.builtup for "is the area developing".
2. **hazards.flood** (P1, Geocode-derived). ACTIONABLE NOW and we already hold
   most of the inputs: the catalogue specifies HAND plus TWI proxy plus
   historic water. We have terrain.dem and terrain.twi; HAND (Height Above
   Nearest Drainage) is derivable from the DEM with pysheds, and JRC Global
   Surface Water supplies the historic water evidence. **Must be flagged as
   MODELLED, not measured.**
3. **connectivity.coverage**. CA maps are likely not redistributable. The
   catalogue already anticipates this: derive our own from connectivity.towers.
4. **utilities.power_distribution**. Externally blocked: Kenya Power data is
   marked no-redistribution and needs a formal request. Interim proxy is OSM
   power lines plus nightlights.

(land.parcels is P1 but is CLIENT data loaded at onboarding, so it is not ours
to fetch. Not counted as outstanding.)

### Next session
1. **demographics.nightlights** then **hazards.flood**: the two remaining P1
   items we can actually build. After those the database is genuinely complete
   apart from externally blocked sources.
2. Then the enrichment engine.
3. Blocking before ANY buyer-facing population number: load the official KNBS
   census (county and ward) and migrate the `LIP-W` provisional ward codes.
4. Enrichment must honour: built-up full cell = 8,606 m2 capped at 1.0; black
   cotton = Vertisols OR clay texture (SoilGrids misses the Athi plains);
   rainfall runs wet; WorldCover cropland under-detects; NDVI is a 2024
   snapshot, not a normal.
5. Add a `Digital Earth Africa` row to sources.csv (NDVI currently attributes
   to the Sentinel-2 row; DE Africa built the geomedian). Deferred only to
   avoid source_id churn mid-session.

---

## Session 6 (2026-08-10)

### hazards.flood COMPLETE (run 62) — after SEVEN failed attempts
- `hazards_flood_modelled_93m_2025.tif`, 17.2 MB COG, 9,644 x 12,158 px at
  ~93 m. 5 classes, 0 = nodata. Confidence 3. **MODELLED, not measured.**
- Kenya shares: Very low 64.23%, Low 9.83%, Moderate 7.30%, High 7.94%,
  **Very high 10.69% (107,162 km2)**.
- **First run where all seven landmarks are correct** on worst-class-within-1km:
  Budalangi / Kano / Tana delta / Garissa all reach Very high; Karen Low;
  Chalbi Moderate; Aberdares Very low.

### Runs 55-61: the same wrong answer arrived at four different ways
Every one of these catalogued or was stopped by the >15% Very high guard.
Recording them because the failure mode repeated even after being named.

| run | method | outcome |
|-----|--------|---------|
| 55 | Euclidean HAND, all OSM waterways | 40.8% Very high. Streams made everything "near drainage" |
| 56 | as above, negatives CLIPPED to 0 | 39.2%. The clip turned "river is across a divide" into "at river level" |
| 57 | rivers+waterbodies only, negatives rejected | 12.4%, catalogued, **WITHDRAWN**: Garissa read Low, Chalbi Very high |
| 59 | flow-routing HAND (correct method) | **29.2%, WORSE.** Filled closed basins |
| 61 | + fill exclusion, FILL_TOL 0.5 m | 25.7%. Fill was only 10.7% of the problem |
| 62 | + catchment-scaled hazard | 10.69%, all landmarks pass |

### THE ROOT CAUSE, which took five runs to see
Runs 55-61 all classified on **absolute HAND**: "2 m above drainage = Very
high", everywhere in Kenya. The etl_24 header actively defended this, arguing
"two metres above the river is dangerous in Turkana and in Kisumu alike".

**That sentence is false, and it was the bug.** Two metres above the Tana is
dangerous. Two metres above a 5 km2 ephemeral sand gully is not, because there
is no upstream catchment to deliver the water. Absolute HAND cannot tell them
apart, so calibration proved the constraints were irreconcilable:

    channels at  5 km2 : every landmark correct, 21% of Kenya at HAND <= 2 m
    channels at 30 km2 : 10.6% of Kenya, but Garissa never above Moderate

and nothing in between fixed both. **The knob was never the problem.**

### THE FIX: hazard scaled by the size of the river you drain to
Flood depth grows with discharge; discharge grows with catchment area. So each
cell is judged against a reference flood depth for the channel it ACTUALLY
drains to (available free: it is `acc` at the cell the downslope walk ends on):

    d(A) = D0 * (A / A0) ** B      D0 = 1.5 m, A0 = 1000 km2, B = 0.3
    hr   = HAND / d(A)             class from hr, not from bare metres

    A =      5 km2 -> d = 0.30 m   (a gully)
    A =    500 km2 -> d = 1.22 m
    A = 50,000 km2 -> d = 4.86 m   (the Tana)

**Plus a size floor, because division cannot discriminate at zero.** 9.4% of
Kenya sits within 1 cm of its channel, so hr ~ 0 regardless of catchment and
scaling alone still gave 13.8% Very high. The top class now also requires an
outlet catchment >= **10 km2**. That is the SMALLEST floor holding Very high
under 10% while keeping Garissa at Very high; 15/20/25/30 km2 all demote it to
High, and 100 km2+ to Moderate or Low.

### Method notes (etl_24_hazards_flood.py)
- HAND by **D8 flow routing** on the pysheds-conditioned DEM, not Euclidean
  nearest-neighbour. Non-negative by construction.
- The downslope walk is **pointer jumping** (`nxt = nxt[nxt]`, channels
  self-loop), ~11 passes over 117M cells. A per-cell walk does not finish.
- **OSM is demoted to validation only.** Channels come from accumulation
  (>= 5 km2), so coverage of the map no longer decides the hazard. OSM river
  cells matched: 34.6% exact, 65.7% within one cell (bank line vs thalweg).
- **Waterbodies excluded entirely.** OSM maps the Chalbi salt pan as a
  waterbody; in run 57 that seeded the network and made a desert Very high.
- **Filled ground carries no HAND** (FILL_TOL_M = 3 m). fill_depressions
  raises closed basins to spill level, which is right for routing and wrong as
  a surface to measure heights against. Those cells fall back to JRC + TWI,
  which is the honest description of a pan: wet when it rains, not a
  floodplain. 4.7% of Kenya.
- **Conditioning is CACHED** (`_cond/_fdir/_acc_93m.tif`). It costs 27 minutes
  and does not depend on any threshold. Without the cache, calibration is two
  guesses and a rationalisation.

### Verification
- `test_hand_routing.py` — synthetic 300x200 landscape with a KNOWN answer, 8
  checks, seconds to run. Includes the Garissa failure in miniature: a cell 15
  cells from valley B but draining 95 cells to valley A. Flow routing picks A;
  the withdrawn Euclidean method picks B and overstates safety by 52.5 m.
  **Also asserts no routing CYCLES**: pointer jumping converges on a 2-cycle
  (a->b, b->a becomes a->a, b->b in one pass), so it would report clean
  convergence while measuring against the wrong cell, invisibly, at 117M cells.
- `calibrate_channel_threshold.py` — sweeps the channel threshold, prints the
  whole curve. Writes nothing; it cannot ship anything.
- `calibrate_scaled_hazard.py` — sweeps D0 and the catchment floor.

### OPEN ITEMS on hazards.flood
1. **Very high 10.69% includes ~2% permanent water** (JRC >= 50%: Turkana,
   Victoria). Calling a lake surface "very high flood hazard" is a category
   error — nobody buys the lake bed — and it inflates the headline. Splitting
   permanent water into its own class puts Very high at 8.66%. **Recommended.**
2. **B = 0.3 is from the general depth-area literature, NOT fitted to Kenyan
   gauge records.** It is the weakest number in the layer. Revise when WRA
   gauge data is available. Recorded in the catalogue entry.
3. **Majority class is softer than worst-nearby**: Garissa majority Very low,
   Budalangi and Tana delta Moderate. A buyer gets the majority reading. For
   Garissa this is defensible (the town sits on a terrace above an incised
   Tana) but the enrichment engine should probably report the worst class
   within a radius, not the cell.
4. Closed basins (4.7% of Kenya) have no HAND at all. Defensible for a playa,
   but it is a coverage gap, not a zero.

### LESSON 20: I TUNED A KNOB FIVE TIMES BEFORE CHECKING THE MODEL
Runs 55, 56, 57, 59, 61 were all the same move: a number came out wrong, a
threshold got changed, the next run was judged on whether the answer looked
better. Four different thresholds, one unexamined assumption underneath.

What broke the loop was **making the wrong answer cheap to see**: caching the
27-minute conditioning so a candidate took 14 seconds, then sweeping the whole
range at once instead of picking a value. The sweep is what showed the
constraints were irreconcilable, which is a statement about the MODEL that no
single run can make.

**Rule: if you have changed the same constant twice, stop changing it. Sweep
it, and if no value satisfies the constraints, the model is wrong, not the
constant.**

### LESSON 21: A TEST THAT PROBES ONE CELL TESTS THE COORDINATE
The calibration first reported single-cell HAND. Budalangi read 11.4 m and
Garissa 16.4 m — both apparently disastrous, both wrong: the coordinates sit
on terraces. Read as worst-within-1km (which is what etl_24 actually uses) the
same run gave 0.0 m for both.

I nearly raised the channel threshold to "fix" landmarks that were never
broken. This is **lesson 18 from session 5, repeated** after being written
down. Extension: the verification must read the layer AT THE SAME RESOLUTION
THE PRODUCT DOES, or it is testing something the product never asks.

### LESSON 22: STATE THE CAUSE BEFORE THE FIX, THEN CHECK IT
Three explicit predictions this session, two wrong:
  - "Flow routing will fix it" -> 29.2%, WORSE than the method it replaced.
  - "Filled basins are the cause" -> only 10.7% of the low tail. Real, minor.
  - "The zero spike is a float32 casting bug of mine" -> no: 97.4% of cells at
    HAND = 0 are channel cells, exactly as designed. The cast was fine.
The diagnostics that disproved each one cost a few lines. **Write the
prediction down first; it is the only way a diagnostic can surprise you.**

### connectivity.coverage COMPLETE (run 69) — and the catalogue was wrong
- 37,122 rows in `connectivity.coverage`. Schema v1.4 applied.
- **The catalogue said CA maps were "likely not redistributable" and that we
  would derive coverage from towers. That was an ASSUMPTION, never tested,
  and it is wrong.** The CA runs a public ArcGIS Hub geoportal with open,
  queryable FeatureServer endpoints: 2G/3G/4G covered AND uncovered, per
  operator and combined, plus fibre routes and Safaricom transmitters.

| tech | operator | rows | conf | vintage |
|------|----------|------|------|---------|
| 2g | all | 9,274 | 3 | 2023-08-30 |
| 4g | all | 7,134 | 3 | 2023-08-30 |
| 4g | Safaricom | 10,357 | 2 | 2022-02-18 |
| 4g | Telkom | 10,357 | 2 | 2022-01-24 |

**IT IS NOT WHAT THE SCHEMA EXPECTED.** Not signal propagation contours:
SUBLOCATION polygons with a coverage PERCENTAGE. So v1.4 adds coverage_pct,
admin_level/name/code, ward_name, population, area, and source_layer rather
than bucketing a percentage into a signal_class nobody measured.
**PRODUCT RULE: "the sublocation containing this parcel is 64.9% 4G-covered",
NEVER "this parcel has 4G". Pair with distance-to-tower, which IS point-level.**

### THE CHECK THAT EARNED ITS KEEP: 3G and 4G were the same dataset
The only 3G layer carrying a percentage is named `..._3G_2022test`. Its
summary statistics were IDENTICAL to the 4G layer: same 7,134 features, same
99.5% median, same 12.0% at exactly 100%. Joined on the unique key, **99.9%
of rows agreed to six decimal places.** Two mobile networks do not differ
that little. The CA published one dataset under two technology names.

etl_25 now DELETES the weaker layer rather than warning about it, because a
warning in a log still leaves 4G figures serving under a 3G label.
**connectivity.coverage has NO 3g.** Unresolved and only the CA can answer:
if the survivor is the mislabelled one, what we call 4g may be 3g.

### OPEN ITEMS on connectivity.coverage
1. **LICENCE NOT DECLARED.** Every CA item has licenseInfo = null and
   accessInformation = null. Public download from a government portal is not
   a grant of commercial reuse. Loaded tier 1, `redistribution_allowed =
   FALSE`. **ACTION: write to info@ca.go.ke** for written terms AND to ask
   which of the 3G/4G layers is correctly labelled. One request to the
   regulator beats three to the operators.
2. **AIRTEL 4G IS NOT PUBLISHED** with a percentage, so per-operator 4G holds
   Safaricom and Telkom only. **Absence of Airtel is absence of DATA, not
   absence of coverage.** Any per-operator display must say so.
3. Vintages run Jan 2022 to Aug 2023 and are not comparable across layers.
   2G covers 9,274 polygons vs 4G's 7,134, so cross-technology national
   comparisons are invalid. Per-parcel lookup is fine.
4. 13,254 rows have invalid geometry as published (self-intersecting rings).
   Repaired with ST_MakeValid at query time; stored geometry left exactly as
   published for provenance.

### Verification (verify_25_coverage.py) — two producers, one reality
Same move as SoilGrids vs iSDA. OpenCellID's 142,279 crowdsourced cells exist
because handsets saw signal; the CA's percentages come from operator returns.
Neither producer knows the other.

    CA coverage band     towers per 1,000 km2
    under 20%                     4.0
    20-50%                       21.5
    50-80%                       29.9
    80-100%                     757.3
    exactly 100%              1,505.9

Monotonic across all five bands, 376x spread. Only 6.8% of sub-20%
sublocations contain any tower. ASAL counties 58.9% mean coverage vs 95.3%
elsewhere (36.4 point gap, 7,134 units). All six major towns at 90%+.
Safaricom 50.1% > Telkom 36.0%, as market share predicts.

**A pass supports ALIGNMENT and VINTAGE only.** It cannot confirm 4g is 4g,
and it validates no point-level claim.

### LESSON 23: MY TESTS KEEP ASSERTING WHERE MY ETLs ASK
Four times in one session I wrote an expectation before looking at the data,
and every one produced a confident wrong answer:
  1. **Garissa at 16.4 m** looked like a disastrous flood under-warning. The
     coordinate sits on a terrace; read as worst-within-1km it was 0.0 m.
  2. **`slcode` "duplicates"** looked like split geometry. slcode holds a
     NAME, and every Kenyan town has a sublocation called TOWNSHIP. On the
     real key every layer is exactly unique.
  3. **County aliases written from memory** (NAIROBI -> NAIROBI CITY, guessed
     hyphenations) took the unmatched rate from 1.7% to 65.7%. Deterministic
     normalisation fixed it; the guesses were the whole problem.
  4. **Lodwar and the Chalbi expected LOW coverage** and read 75.6% / 77.4%.
     Sublocations are drawn around HABITATION: at that unit size remoteness
     does not exist as a polygon. Replaced with an ASAL-vs-rest
     distributional test that my coordinate choice cannot game.

This is lesson 19 recurring after being written down, so state it as a rule:
**BEFORE ASSERTING WHAT A FIELD MEANS, QUERY IT. One query settled each of
the four above in seconds; each cost 20+ minutes by being assumed.**
And: **a redesigned test is not a relaxed test.** Dropping Lodwar because it
"failed" would have been fitting the test to the answer; replacing a
point-probe with a distributional comparison tests the same claim honestly.

### LESSON 24: CATCH THE RIGHT EXCEPTION, AND CACHE THE FETCH
Run 66 died on `http.client.IncompleteRead` — an HTTPException, NOT an
OSError — so eight carefully tuned retries never fired. Runs 64 and 66 each
threw away thousands of rows that had already arrived.
Now: catch HTTPException, page size cut 2,000 -> 500 (a 24 MB response is too
much for a link that blips; 6 MB survives), and **every page is cached to
disk** via .part-then-rename. Reruns are instant. This is session 5's
FETCH/REPROJECT separation applied to a flaky link rather than a slow one.

### demographics.nightlights COMPLETE (run 73) — the last buildable P1
- 7,345 rows in `demographics.nightlights_stats`: 47 counties + 1,422 of
  1,425 wards, five years (2015, 2019, 2022, 2023, 2024). Confidence 4.
- Five yearly COGs in `06_rasters/cog/demographics/`, ~500 m, catalogued.

**SOURCE CHANGED MID-BUILD. EOG's VNL is no longer usable programmatically.**
Written first against EOG VNL v2.2; EOG has moved OpenID access to paid
subscribers, so `eogauth.mines.edu` returns nginx 403 on every token endpoint
while `eogdata` returns 401. A free account no longer opens the API.

**Switched to NASA Black Marble VNP46A4**, and rejected Google Earth Engine:
  1. **LICENCE.** NASA Earth Science data carries no commercial restriction.
     **GEE's free tier is NONCOMMERCIAL ONLY** and this is a commercial
     product — it would have been the WDPA trap a fourth time.
  2. **SIZE.** VNL is one ~1.5 GB global file per year, untiled. VNP46A4 is
     tiled 10x10 deg: Kenya needs 4 tiles (h21v08, h22v08, h21v09, h22v09) at
     ~92 MB.
  3. **FIT.** Download -> COG -> catalogue -> zonal stats is the pattern every
     other raster follows. GEE moves computation off-machine.
  4. **CORRECTION.** VNP46A4 is BRDF-adjusted for lunar illumination,
     atmosphere, terrain and vegetation, which matters more than absolute
     radiance when the TREND is the signal.

**ArchiveSet is 5200, not 5000** (5000 holds VNP01/TLE_VGD, no Black Marble).
Subdataset `AllAngle_Composite_Snow_Free`, discovered from the file (26
available) rather than hardcoded. v2.0 stores radiance as FLOAT, changed from
v1.0 uint16 so gas flares above 6553.5 nW/cm2/sr stop saturating.

### LESSON 25: THE METRIC WAS WRONG, AND EVERY CHECK STILL PASSED
verify_26 passed every assertion while `trend_pct_yr` was unusable:

    median ward   33.19 %/yr  -> 11x brightening over nine years
    fastest ten   214-252 %/yr
    and they were Homa Bay, Migori, Kisii, Kakamega -- not the market

Cause: log-linear growth in `radiance_sum` with a 0.01 floor. **335 of 1,422
wards had a 2015 baseline of exactly zero**, so the metric was measuring how
dark a ward used to be. Percentage growth from a near-zero base is unbounded.

`calibrate_nightlight_trend.py` compared three candidates on whether their
top-ranked wards are places Kenyan land value actually moves:

| metric | top wards | verdict |
|--------|-----------|---------|
| log growth %/yr | Tembelio, Dedan Kimathi, Kochia | rural electrification |
| lit-area points/yr | all saturate at 100% lit and tie | **scores Ruai, Karen, Gitothua, Mihang'o at ZERO** — they were already fully lit in 2015 |
| **absolute radiance/yr** | **Ruai, Kitengela, Muthwani, Gatongora, Murera, Kalimoni, Gitothua, Mihang'o, Kinanie, Karen, Hindi (LAPSSET)** | **the Nairobi peri-urban land market** |

Top-50 rank overlap between log-growth and absolute was **0/50**. They are not
variants of one measure; they answer different questions.

**Schema v1.5**: `trend_radiance_yr` added (least-squares slope of
radiance_sum, absolute, no baseline floor needed because absolute change is
defined at zero). **`trend_pct_yr` is deliberately NULL**, with the reasoning
in the column comment so nobody repopulates it later.

**I predicted lit-area-points would win. It lost, to saturation** — a bounded
metric cannot discriminate above its bound, and the wards that matter were
already at the bound.

**Verification redesigned to be falsifiable.** The old version printed the
model's own top ten and asked whether they looked right; a ranking cannot
validate itself. verify_26 now NAMES eight peri-urban markets in the script,
chosen because any Kenyan agent would list them unprompted, and asserts they
reach the national top decile. **Result: 8 of 8, all above the 99.4th
percentile** (Muthwani 100.0, Ruai 99.9, Mihang'o 99.9).

Also passing: lit area rises 1.8% -> 97.3% across population-density
quintiles; Nairobi brightest county at 21.33; ASAL counties 0.007.

### CAVEATS on nightlights
- `trend_radiance_yr` is a SUM, so it scales with unit area. Never compare a
  large ward to a small one on it directly.
- Radiance is not linear in economic activity; VIIRS compresses bright cores.
- SNPP's DNB degraded over the series. v2.0 corrects but does not erase it.
- 3 of 1,425 wards return no data in any year (consistent, so trends are
  unaffected, but enrichment gets NULLs).
- The electrification signal is real and was discarded, not disproved. It
  could return as an explicit indicator with a baseline floor — never as the
  development signal.

### hazards.flood CORRECTED TWICE MORE (runs 75, 77)
**1. Permanent water is now class 6, not "Very high".** ~2 points of run 62's
10.69% was Lake Turkana and Victoria arriving via the JRC permanent-water
rule. A lake surface is not a flood hazard — nobody buys the lake bed. Class 6
sits above 5 in the raster because it overrides every hazard judgement, but
the catalogue states it is a LAND-COVER FACT, not a hazard level.

**2. LESSON 26: every "% of Kenya" in this script was "% of the bounding
box".** Run 75's class areas summed to **1,002,267 km2 against Kenya's
580,367** — 42% of what we classified was Indian Ocean, Ugandan and Tanzanian
Lake Victoria, and neighbouring land inside the padded bbox. GLO-30 gives the
ocean elevation 0 rather than nodata, so it passed the "is there land here"
test. **This is lesson 17 recurring for the third time.**

Fixed by rasterising `admin.country` and clipping ALL statistics. Computation
still uses the full grid, because flow routing must see across the border.

Two independent confirmations the clip is right:
- country mask **592,055 km2** vs official 580,367 (2.0% over, as expected
  from 93 m rasterisation plus inland water in the polygon)
- permanent water **12,210 km2** vs Kenya's ~11,227 km2 inland water
  (it was 27,202 before the clip)

**Final distribution (run 77), share of LAND excluding permanent water:**

    Very low  67.82%   Low 11.71%   Moderate 7.92%   High 5.61%
    Very high  6.93%   (40,204 km2)        Permanent water 12,210 km2

Down from 10.69%. I predicted the clip would RAISE the top class; it fell,
because the excluded area was mostly water and low-lying and had been
classifying high.

**Budalangi is the softest landmark**: majority Moderate, worst-nearby
Permanent water. Catchment scaling puts the Nzoia's Very-high threshold at
~3.2 m HAND there, so Moderate means the settlement sits 6-13 m above the
channel — defensible for a levee village, and Budalangi floods by DIKE
FAILURE, which HAND structurally cannot see. **Enrichment must surface
proximity-to-permanent-water as its own risk signal; class 6 is not benign.**

**OPEN:** `AMIN_TOP_KM2 = 10` was calibrated against the uncorrected
denominator. It still holds (all landmarks pass, Very high under 10%), but
there is now headroom to LOWER it and warn more, which this layer's stated
rule would favour. Re-run `calibrate_scaled_hazard.py` with the country clip
before deciding. **Confirmed by reading the file this session:
`calibrate_scaled_hazard.py` contains no country clip** — no `admin.country`
read, no `rasterize`, no `in_kenya` mask anywhere in it. The clip has to be
added to the calibrator BEFORE the sweep, or the re-calibration reproduces
exactly the denominator it is meant to correct.

### climate.rainfall RECENT + ANOMALY + DRIEST YEAR (etl_27, run 79)

Three new variables on the existing `climate.rainfall` dataset, all CHIRPS
v3.0, all written onto the 1991-2020 normal's own grid:

| variable | what it is | unit |
|----------|-----------|------|
| `rainfall_recent_mean` | mean annual total 2021-2025 | mm/yr |
| `rainfall_anomaly_pct` | that mean as % of the 1991-2020 normal | % of normal |
| `rainfall_driest_year_pct` | the DRIEST single year of the window as % of normal | % of normal |

**The 1991-2020 normal is NOT stale and was not replaced.** Njeri asked
whether a 2020 endpoint is out of date. For the question that layer answers —
"can I farm here" — it is not: 1991-2020 is the current WMO standard 30-year
normal and stays current until 2021-2050 replaces it. A three-year average
would be WORSE for that question, because it bakes in whichever drought or wet
cycle happened to land in the window. So this is a SECOND layer answering a
different question: not "what does this place get" but "what has it been like
lately".

**Computed on the normal's grid on purpose.** Each recent year is reprojected
onto the existing raster's exact transform, so the anomaly is a pixel-by-pixel
ratio with no resampling between numerator and denominator. That is the only
way the division is honest.

**Percent of normal, not millimetres below.** A 200 mm shortfall is
catastrophic in Turkana and unremarkable in Kericho. The ratio makes arid and
humid Kenya comparable; a millimetre deficit does not. Same reasoning as the
flood layer's catchment scaling — judge each place against its own reference,
not against a national constant.

**2026 is deliberately excluded.** CHIRPS v3 runs to mid-2026 and a part-year
total would read as a catastrophic drought. A partial year is not a dry year.
`MIN_YEARS = 3`: below three the "recent mean" is not a mean.

**Guards carried over rather than reinvented:** URL patterns are PROBED against
the same candidate list etl_18 uses (CHC has relocated these paths before);
CHIRPS `-9999` and anything above `MAX_SANE_MM = 15,000` become nodata, never
clipped; anomalies outside 10-400% of normal are rejected as grid or nodata
artefacts and the count is printed rather than swallowed.

### LESSON 27: A MEAN CAN HIDE A DROUGHT

2021-2025 contained both the worst Horn of Africa drought in forty years and
the 2023-24 floods. Averaged, Kenya reads about **107% of normal** — which is
arithmetically true and a poor description of what anyone lived through.

Against that same window, **68.9% of Kenya had at least one year under 75% of
normal, and 8.6% had a year under 50%.**

`rainfall_driest_year_pct` exists only because the mean looked fine. "In the
worst of the last five years this area got 61% of its normal rainfall" is
something a buyer can plan around; "this area has run at 107% of normal" tells
them nothing about the volatility they would actually be buying into.

**Rule: when a statistic is a mean over a window, publish the tail as well.
A window wide enough to be stable is wide enough to hide a disaster inside it.**

### LESSON 28: I BROKE RULE E1 ONE HOUR AFTER WRITING IT DOWN

Run 78 of etl_27 quoted every national figure over the PADDED BOX, not Kenya.
The give-away was the normal reading **712 mm** where etl_18 had recorded
Kenya-only as **681 mm** — the 712 figure is the box, including Indian Ocean,
Uganda, Tanzania, Ethiopia and Somalia.

This is lesson 26 from earlier in this same session, and checklist rule E1,
which was written into `PRE_LAUNCH_CHECKLIST.md` hours before run 78. **Writing
the rule down did not prevent the fourth occurrence.**

Fixed in run 79 by rasterising `admin.country` and masking every statistic.
etl_27 now prints BOTH numbers side by side — padded box and Kenya-only,
labelled `<- the honest denominator` — so the error cannot recur silently in
this script.

**A rule in a checklist is not a control. A rule enforced by the script's own
output is.**

### climate.rainfall EXTREMES (etl_28, run 80)

The largest missing input to the flood model. `hazards.flood` answers "if water
arrives, where does it go" — it has terrain, flow accumulation, catchment size
and observed water, and NO measure of how much water arrives. Budalangi
(1,800 mm/yr) and a Turkana floodplain (200 mm/yr) with identical HAND and
identical catchment currently get identical hazard.

| variable | what it is |
|----------|-----------|
| `rainfall_max5day_mean` | mean annual maximum 5-day rainfall, mm — "a wet spell here typically delivers X mm" |
| `rainfall_max5day_p90` | 90th percentile of the annual maxima — a rough 1-in-10-year wet spell |

**Annual totals cannot fill the gap: flooding responds to INTENSITY.** 900 mm
spread evenly over a year floods nothing; 300 mm in five days floods a
catchment.

**Why five days.** It is roughly how long a medium catchment takes to fill and
route water to its outlet, which is the mechanism a HAND-based layer models. A
single day's total mostly drives FLASH flooding, a different mechanism this
layer is not modelling anyway.

**p90 is explicitly NOT a fitted return period.** With ~16 years of record an
extreme-value fit would be false precision. Called "a rough 1-in-10-year wet
spell" and no more.

**Guards:** `MIN_PENTADS = 60` of 72 — a year below that is REJECTED, because
an annual maximum computed from a partial year is not an annual maximum;
`MIN_YEARS = 8`; 5-day totals above 2,000 mm rejected, never clipped; pentads
cached per file, so a dropped connection costs one pentad rather than the run.
`.gz` pentads are read in place through `/vsigzip/` rather than unpacked —
1,152 files decompressed to disk would double the footprint for nothing.

**Landmarks named in the script BEFORE looking** (lesson 23): Mombasa, Lamu,
Kericho, Kakamega and Nairobi should lead; Lodwar, Marsabit and Wajir should
trail. If the north leads, the grid is misaligned.

### THE VERSION SPLIT, AND WHY IT IS NOT A DEFECT

**CHIRPS v3.0 publishes no pentad product. Only v2.0 does.** The probe found
this; it was not assumed. So `climate.rainfall` now spans two CHIRPS versions:

    normal (1991-2020)      v3.0
    recent / anomaly / driest   v3.0
    max5day mean / p90      v2.0   <- pentads only exist in v2

v3 carries roughly twice the station observations over Africa, so the versions
are not identical. **Nothing divides across versions** — the anomaly is v3/v3,
and the extremes stand alone — so no computed value mixes lineages. But an
absolute v2 extreme and an absolute v3 total are not the same lineage, and that
belongs on the record rather than in a footnote.

**CHC ends v2 production after December 2026. Re-probe then** for a v3 pentad
or daily product. Recorded in `PRE_LAUNCH_CHECKLIST.md`.

### THE FIXED-PENTAD UNDER-ESTIMATE (state this wherever the layer is used)

CHIRPS pentads are FIXED 5-day blocks, 72 per year. A storm straddling a pentad
boundary is split between two blocks, so the fixed-pentad maximum
**UNDER-ESTIMATES a true rolling 5-day maximum by roughly 10-20%.**

Daily data would give a rolling maximum and is strictly better, but needs ~365
files per year against 72 — and on the connection that failed four different
ways building etl_25 and etl_26, five times the file count is five times the
failure surface. The trade was taken deliberately.

The under-estimate is **consistent across the whole country**, so it does not
distort the SPATIAL PATTERN, which is what a screening layer needs.
**Never quote these as design rainfall figures for engineering.**

### HOW THIS FEEDS hazards.flood (not yet wired in)

HAND says where water goes; max5day says how much arrives. Combine as
**susceptibility x forcing, kept as two explainable numbers.** Do NOT merge
them into a single score with invented weights: the whole reason the flood
layer survived seven failed runs is that every term in it can be pointed at and
defended separately.

### satellite.landcover — Impact Observatory annual (etl_29, run 81) — PARTIAL

**Yearly snapshots SHIP. The change layer DOES NOT. See the section below.**

**Why, when we already have WorldCover.** Njeri asked whether 2021 is too old,
and checking settled it: **ESA has published nothing after 2021.** v100 was
2020, v200 was 2021, and that is the end of the series. The concern was correct
and there is no ESA answer to it.

- **Source:** Impact Observatory / Microsoft / Esri, 10 m annual LULC, 9-class,
  Sentinel-2 basis. Years ingested **2017, 2023, 2024** (the script's
  `IO_YEARS` default also lists 2025; the handoff records three years, so 2025
  appears not to have been returned by the STAC query — **verify against
  `metadata.raster_catalog` before quoting the year list**).
- **Resampled to ~93 m**, the same 3-arcsec lattice `hazards.flood` and
  `satellite.builtup` use. Deliberate: the question this layer answers is asked
  per parcel, and holding four national 10 m mosaics is ~3.5 GB for a
  comparison a 93 m grid answers. **WorldCover remains the 10 m classification
  reference for "what is this exact spot".**
- **NEAREST on both the resample and the overviews** — lesson 15. Averaging
  class codes invents classes; the mean of Built (7) and Bare (8) is 7.5.

**LICENCE IS CLEAN, and that is worth saying out loud: CC BY 4.0, commercial
use permitted with attribution.** No letter, no negotiation, no pre-launch
blocker. Unlike WDPA (non-commercial), the CA coverage layers (no declared
licence at all) and Google Earth Engine's free tier (noncommercial only, which
would have been the WDPA trap a fourth time). Attribution string is written
onto every catalogue row.

**Access DISCOVERED, not constructed.** Public S3 bucket `io-10m-annual-lulc`
(us-west-2, no AWS account) plus a STAC 1.0.0 endpoint, and the script QUERIES
the STAC for which years and tiles exist over Kenya rather than building paths.
Direct application of rule E2 after six memory-asserted values failed earlier
in the session.

**The 9 classes** (3 and 6 unused): 1 Water, 2 Trees, 4 Flooded vegetation,
5 Crops, 7 Built area, 8 Bare ground, 9 Snow/ice, 10 Clouds, 11 Rangeland.
**IO "Rangeland" absorbs BOTH WorldCover's Shrubland AND Grassland**, so a
class-by-class comparison between the two products will always disagree, and
that disagreement is not an error.

### LESSON 29: THE REASON WE CHOSE THE DATASET IS THE PART THAT DOES NOT WORK

`landcover_change` — **DO NOT USE.** Change detection was the bigger prize and
the explicit justification in etl_29's own header: "this parcel was rangeland
in 2017 and built by 2024" is a stronger development signal than the
nightlights trend, because it is categorical and per-parcel rather than a
radiance sum over a ward. It is not available from this product.

**SUPERSEDED BY RUN 82 (country-clipped). The figures below are the real
Kenya shares; run 81's box shares are struck through and kept only so the
correction is traceable.**

    ~~Tree cover  13.58% -> 25.58%~~   ~~changed 23.05%~~   ~~Built 1.72 -> 2.59%~~

Run 82, clipped to `admin.country` (mask 592,333 km2, 102.1% of official —
and independently 0.05% from the flood layer's 592,055 km2 on the same
lattice, so the denominator is sound):

| class | 2017 | 2023 | 2024 |
|-------|------|------|------|
| Water | 2.07% | 2.17% | 2.26% |
| Trees | **10.98%** | **14.53%** | **21.93%** |
| Flooded vegetation | 0.02% | 0.03% | 0.06% |
| Crops | 8.22% | 8.83% | 8.83% |
| Built area | 2.23% | 2.92% | 3.34% |
| Bare ground | **5.00%** | **0.95%** | **0.77%** |
| Clouds | 0.03% | 0.02% | 0.01% |
| Rangeland | **71.45%** | **70.54%** | **62.78%** |

    changed class   21.76% of Kenya
    became BUILT     1.389%  (8,227 km2)
    2025 not published — STAC returned no items. Year list is 2017/2023/2024.

### LESSON 29a: THE DRIFT IS A STEP, NOT A SLOPE — AND THAT NAMES THE CAUSE

Run 81 could only say "tree cover nearly doubled, which is impossible". Three
clipped epochs say something much sharper: **the change is not spread across
the seven years. It is concentrated in single year-steps, and different classes
jump in different steps.**

    Trees      2017->2023  +3.55 pts over SIX years
               2023->2024  +7.40 pts over ONE year     <- 68% of the total
    Rangeland  2017->2023  -0.91 pts over six years
               2023->2024  -7.76 pts over one year
    Bare       2017->2023  -4.05 pts  (a 81% collapse)
               2023->2024  -0.18 pts

Two separate discontinuities, in two different class pairs, at two different
year boundaries:

1. **2017 -> 2023: Bare ground collapses into Trees, Crops and Built.**
   Losses (bare -4.05, rangeland -0.91) balance gains (trees +3.55, crops
   +0.61, built +0.69, water +0.10) to within 0.01 pt.
2. **2023 -> 2024: Rangeland converts almost purely to Trees.** Rangeland
   -7.76 against trees +7.40 and built +0.42. A near-perfect exchange between
   two classes and almost nothing else moving.

**Real land-cover change does not arrive as a step in one class pair while
every other class holds still.** Vegetation regrowth is gradual and touches
several classes at once. A model retrain moves one decision boundary at one
release, which is exactly this shape. **This is the classifier, and the
year-step tells you which release did it.**

### THE CONTROL THAT MAKES THE VERDICT SAFE: WATER

Water reads 2.07 / 2.17 / 2.26% across the three epochs against ESA
WorldCover's Kenya-clipped **2.13%**. Stable across all three years, and
agreeing with an independent producer.

That is the check that rules out our own pipeline. If the grid, the mask, the
NEAREST resampling or the clip were wrong, water would move too. It does not.
**The instability is class-specific and confined to the hard tree / rangeland /
bare boundary — which is precisely where a retrained classifier would move.**

### AND THE 2017 MAP AGREED WITH WORLDCOVER ON BARE GROUND

IO 2017 Bare = **5.00%**. WorldCover Bare/sparse = **4.55%**. Close.
IO 2024 Bare = **0.77%**.

So IO has drifted AWAY from a figure it once matched. The Chalbi and the
Turkana basin did not vegetate. This is the single clearest statement of the
problem: **the series disagrees with itself more than its first epoch
disagreed with an independent producer.**

### THE BUILT DIVERGENCE IS A DIFFERENT PROBLEM — DEFINITION, NOT DRIFT

Worth separating, because the handoff conflated them.

    IO Built 2017  2.23%      already ~7x WorldCover's 0.32%
    IO Built 2024  3.34%

**The gap is present at the baseline, before any drift.** That is a
DEFINITIONAL difference in what IO calls "Built area" versus WorldCover's
"Built-up", not evidence of retraining. It means the two built classes are not
comparable at all, in any year — a separate finding from the tree/rangeland
instability, and one that stands even for the yearly snapshots.

**`became BUILT` 8,227 km2 is the number that kills the change layer even as a
"lead".** Kenya's ENTIRE built stock is ~1,857 km2 by WorldCover and 3,054 km2
by GHSL. IO claims seven years of new construction equal to **4.4x
WorldCover's total stock, or 2.7x GHSL's.** A lead list that flags 8,227 km2
is not a lead list.

**Kenya's tree cover did not nearly double in seven years.** No deforestation
or afforestation programme of that magnitude occurred, and if it had it would
be the largest land-cover story in the country's history rather than a number
discovered in an ETL printout. IO Built at 1.72-2.59% against WorldCover's
0.32% is a **5-8x divergence** — far outside the GHSL-vs-WorldCover gap
(0.52% vs 0.32%) that session 5 established as the expected disagreement
between two producers measuring genuinely different things.

**This is classifier drift between model versions, not ground change.** IO
retrains its model and republishes the full back series; a boundary that moves
in the model moves in every year at once, and differencing two years measures
the model revision rather than the landscape.

**Action outstanding:** mark `variable = 'landcover_change'` as
`pending_review` or delete the catalogue row. etl_29 CATALOGUES it on success
(confidence 3), so it is live in `metadata.raster_catalog` right now and the
enrichment engine could pick it up.

**Keep the yearly snapshots.** They are internally consistent within a year and
they deliver the recency WorldCover cannot. What is lost is the comparison
BETWEEN years.

### THE ONE PLACE IO LOOKS BETTER THAN WORLDCOVER: CROPLAND

Not everything here is a defect, and this is worth acting on.

    IO Crops 2024        8.83%  =  51,246 km2
    WorldCover cropland  4.46%  =  26,387 km2
    NDVI upper bound on missed farmland   111,245 km2

Session 5 established that **WorldCover under-detects smallholder mosaic
farming**, which is most of Kenyan agriculture, and NDVI put an upper bound of
111,245 km2 on land as green as mapped cropland. IO's cropland lands squarely
between WorldCover's floor and that ceiling, and it is stable across epochs
(8.22 / 8.83 / 8.83 — the one class that does NOT jump).

So on the class where WorldCover is known to be weak, IO is both plausible and
steady. **Product rule D6 gains a third witness:** never say "not farmland"
from WorldCover alone — check NDVI, rainfall, soil AND the IO crops class.

**The general rule: a temporally consistent series is a property you must
verify, not one you get by downloading years from the same producer.** Annual
publication is not a time series. Before differencing any two epochs, check
whether the producer reprocesses history — and if the two endpoints disagree by
more than the phenomenon could physically have changed, believe the physics.

### LESSON 30: etl_29 HAS NO COUNTRY CLIP — RULE E1, FIFTH OCCURRENCE

Found by reading the file, not by running it. Every share etl_29 prints divides
by `(g > 0).sum()` — **the covered PADDED BBOX, not Kenya.** There is no
`admin.country` read and no `rasterize` call anywhere in the script; it takes
`ST_Extent(geom)` for a bounding box and never masks. `both`, `changed` and
`to_built` in the change block are unclipped for the same reason, so
"23.05% of Kenya changed class" is really 23.05% of the covered box.

etl_24, etl_27 and etl_28 all clip correctly. etl_29 was written in the same
session and does not.

**Consequence for the numbers above:** they are box shares, so they are not
comparable with WorldCover's Kenya-clipped 0.32%. Note the direction — ocean
and neighbouring territory inflate the denominator, so a correctly clipped IO
Built share would be **HIGHER** than 1.72-2.59%, making the divergence with
WorldCover **worse**, not better. The change-layer verdict stands and if
anything strengthens. But the specific figures are not Kenya figures and must
not be quoted as such.

**FIXED AND RE-RUN (run 82).** etl_29 now rasterises `admin.country`, masks
every share and change statistic, prints the box and Kenya figures side by
side, and **refuses to run** if the mask does not measure within 95-110% of
Kenya's 580,367 km2. `calibrate_scaled_hazard.py` got the same mask, cached to
`_kenya_mask_93m.tif` so only the first run needs the database.

**Measured effect of the clip:** built area 2024 went from 2.59% (box) to
3.34% (Kenya) — the correction moved the number UP by 29%, exactly the
direction predicted, because ocean and foreign land had been padding the
denominator. The pre-clip figures did not merely blur the IO/WorldCover
divergence, they understated it.

**Mask cross-validated:** 592,333 km2 here against the flood layer's 592,055
km2 on the same 3-arcsec lattice. Two scripts, two independent code paths,
0.05% apart.

### THE TRAP THIS FIX WALKED INTO — RE-CATALOGUING ON SUCCESS

Run 82 completed successfully and, inside its final transaction, **re-inserted
`landcover_change` at `status = 'active'`**, undoing the quarantine SQL.

etl_29 has no notion that one of its outputs is condemned. Any successful run
silently republishes it.

**This is not fixed by running the SQL again.** Every future etl_29 run
resurrects the row. Either the quarantine has to move INTO etl_29 (write the
change layer straight to `pending_review`, or stop writing it at all), or the
script must stop producing it. **Until that lands, the running order is
etl_29 FIRST, then the SQL — never the reverse.**

A data-fix script that a pipeline can overwrite is a reminder, not a control.
Same shape as rule E1: the fix has to live where the code is, not in a
document or a one-off statement beside it.

This is the fifth occurrence of the same error — land cover (s5), flood twice
(runs 62, 75), rainfall (run 78), land cover again (run 81). It has now
recurred twice AFTER being written into the checklist as rule E1.
**The fix is no longer a rule. It is a shared helper that every raster ETL
imports, so that clipping is what the code does by default and NOT clipping is
what takes effort.**

### SESSION 6 CLOSING STATE — P1 25 of 27

Rainfall recency and land cover recency, both listed as NOT started when this
section was first drafted, were completed in this same session (etl_27, etl_28,
etl_29 above). Superseded text removed rather than left to mislead.

**The data phase is effectively closed.** The two remaining P1 datasets are not
blocked on us:

1. `utilities.power_distribution` — Njeri has a Kenya Power GIS contact. **Ask
   for a DERIVED-USE licence, not the data.** Permission to store "nearest MV
   line: 340 m" without redistributing the network is far easier to approve
   inside a utility than a data release.
2. `land.parcels` — client data at onboarding. Not ours to fetch, and not
   counted as outstanding.

### Next session, in order

1. **Run `01_database/07_data_fix_landcover_change.sql`** (WRITTEN, NOT RUN —
   needs your local Postgres). Sets `landcover_change` to `pending_review`,
   prepends the reason to its `name` so a catalogue reader hits it first, and
   closes the orphan etl_29 run row as `failed`. Idempotent, prints before and
   after, and the orphan-run update is guarded three ways so it cannot close a
   job you started yourself. Lesson 29.
2. **Re-run etl_29** (CLIP ADDED, NOT RE-RUN). The yearly COGs are cached so it
   will not re-download; it needs the DB. Then replace the IO figures in lesson
   30 with the Kenya-clipped ones. **Still worth doing properly: extract the
   clip into a shared helper every raster ETL imports, so clipping is the
   default and skipping it takes effort.** Five occurrences say a rule is not
   enough.
3. **C1 IS ANSWERED — see the clipped sweep below.** `AMIN_TOP_KM2` cannot
   come down, for a structural reason, and the top class is wide for a cause
   the floor cannot reach. One product decision is open (Garissa).
4. **Two emails.** The CA (`info@ca.go.ke`): written licence terms AND which of
   the 3G/4G layers is correctly labelled — one request to the regulator beats
   three to the operators. Kenya Power via Njeri's contact: derived-use licence.
5. **Wire rainfall extremes into `hazards.flood` as a forcing term.** Keep it
   **susceptibility x forcing — two explainable numbers**, never merged into one
   score with invented weights.
6. **Then the enrichment engine.** This is the product, and it must honour the
   13 product rules in `PRE_LAUNCH_CHECKLIST.md` §D, including: built-up full
   cell 8,606 m2 capped at 1.0; black cotton = Vertisols OR clay texture
   (SoilGrids misses the Athi plains); rainfall runs wet; WorldCover cropland
   under-detects; NDVI is a 2024 snapshot, not a normal; coverage is a
   SUBLOCATION percentage, never "this parcel has 4G"; nightlights
   `trend_radiance_yr` is a SUM and does not compare across unit sizes;
   **flood hazard is MODELLED and should be read as worst-within-radius, not
   per cell**; proximity to permanent water is its own risk signal — class 6 is
   not benign.
7. **Blocking before any buyer-facing population number:** load the official
   KNBS census (county and ward) and migrate the `LIP-W` provisional ward codes.
8. **Start early, because it is structural, not a footnote:** OSM's ODbL
   share-alike touches roads, rivers and waterbodies. If it attaches to a
   derived database that is a product decision, not a licensing detail. Get a
   legal opinion BEFORE the enrichment engine hard-wires those layers in.

### HOUSEKEEPING

- **Orphan run row:** a Ctrl+C during etl_29 left a `metadata.etl_runs` row at
  `running`. Harmless — close it manually if you want the audit trail tidy.
- **Run numbers in this section are as reported at the end of session 6 and
  were NOT verified against `metadata.etl_runs`** (no database access when this
  was written up). Run 78 is inferred from etl_27's own source comment, which
  names it as the padded-box run. Confirm the mapping next time you are at the
  laptop.

### C1 RESOLVED: THE CLIPPED AMIN SWEEP (session 7)

Country mask 592,333 km2, 69M Kenyan cells against 117M in the padded box —
**41% of what the old sweep measured was not Kenya**, matching run 75's 42%.

    Very high needs A >=   Very high    High  Moderate     Low  Very low
                   0 km2       9.02%   3.84%     5.93%  11.78%    63.62%
                   3 km2       9.02%   3.84%     5.93%  11.78%    63.62%
                   5 km2       9.02%   3.84%     5.93%  11.78%    63.62%
                  10 km2       7.29%   5.57%     5.93%  11.78%    63.62%   <- shipped
                  15 km2       6.52%   6.34%     5.93%  11.78%    63.62%
                  30 km2       5.37%   5.08%     8.34%  11.78%    63.62%

(The ~5.8% not accounted for is `undefined`: closed basins carrying no HAND.
etl_24 fills these from JRC + TWI, which is why run 77's Moderate and Very low
read higher than the calibrator's. The two are consistent, not contradictory.)

### THE ANSWER TO C1: THERE IS NO HEADROOM, AND THE REASON IS STRUCTURAL

**0, 3 and 5 km2 return byte-identical results.** That is not a plateau in the
data, it is an identity: `CHANNEL_KM2 = 5`, so a channel only exists where
accumulation reaches 5 km2, so **every cell's outlet catchment is >= 5 km2 by
construction**. A floor at or below 5 cannot bind on anything.

So the entire lower half of the sweep was uninformative before it ran, and the
premise of C1 — "there is headroom to lower it and warn more" — **is not
available at all.** The only way to lower the effective floor is to lower
`CHANNEL_KM2` as well, which is the knob calibration already proved
irreconcilable back in run 57.

**And lowering it would not warn better anyway.** At floor 0-5, Very high is
9.02% against High at 3.84% — the top class is 2.3x the one below it, which is
the script's own rule 2 firing: a top class that wide is absorbing cells that
belong further down, not describing a more dangerous Kenya. More red pixels is
not more warning.

### THE TOP CLASS IS WIDE FOR A CAUSE THE FLOOR CANNOT REACH

No floor in the sweep produces Very high < High. The reason is in the hr
distribution, not the catchment floor:

    3.20% of Kenya sits at HAND = 0   -- of which 96.6% are CHANNEL CELLS
    1.45% more sits within 1 cm of it
    ------
    4.65% at hr ~ 0, against a Very high class of 9.02% at floor 0

**Over half the top class is ground at or within a centimetre of the channel,
and the great majority of that is the channel itself.** Channel cells are set
to HAND = 0 deliberately — they ARE the river.

This is the permanent-water question again, one level down. Run 75 split lake
surface out as class 6 because "nobody buys the lake bed". A seasonal river
channel is the same kind of object: **being in the watercourse is a land-cover
fact, not a flood hazard rating.** The riparian buffer layer already tells a
buyer they cannot build there, and for a stronger reason.

**The real lever is therefore the class boundaries or a channel class, NOT
`AMIN_TOP_KM2`.** Recorded rather than acted on: changing `MULT` re-classes the
whole country and needs its own calibration and its own landmark run.

### THE OPEN DECISION: DOES GARISSA NEED "VERY HIGH", OR IS "HIGH" ENOUGH?

    landmark              expected           10 km2        15 km2
    Budalangi, Nzoia      High/Very high     Very high     Very high
    Kano plains           High/Very high     Very high     Very high
    Tana delta            High/Very high     Very high     Very high
    Garissa on the Tana   High/Very high     Very high     High
    Nairobi Karen         Low/Very low       Very low      Very low
    Aberdares slopes      Very low           Very low      Very low
    Chalbi desert         Low/Very low       undefined     undefined

**The calibrator's stated test passes at BOTH values.** It asks for
"High/Very high" at Garissa, and 15 km2 delivers High. But run 62's reasoning
demanded Very high specifically, and picked 10 km2 as "the SMALLEST floor
holding Very high while keeping Garissa at Very high". **The script tests one
thing and the shipped value was chosen for another** — nobody noticed because
10 satisfies both.

    10 km2 : Garissa Very high, but Very high 7.29% vs High 5.57%  (1.31x)
    15 km2 : Garissa High,      and Very high 6.52% vs High 6.34%  (1.03x)

15 km2 is the most credible SHAPE the layer can reach. 10 km2 is the stronger
WARNING at the single landmark that has driven this layer since run 57 was
withdrawn for under-warning Garissa.

**RECOMMENDATION: keep 10 km2.** Nothing in the clipped sweep condemns it, the
difference in shape is 1.31x versus 1.03x on a class whose width is dominated
by the channel-cell spike rather than by the floor, and under-warning a Tana
town is the specific failure that already cost a withdrawn run. **But the
choice is now explicit and evidenced rather than inherited** — which is what
C1 was actually for.

**Chalbi reads `undefined` at every floor.** Not a regression and not a floor
problem: it is a closed basin carrying no HAND, and the calibrator has no
JRC + TWI fallback, so it cannot reproduce what etl_24 ships there. The
landmark row is untestable in this script and should say so rather than look
like a failure.

### LESSON 31: THE AUDIT TRAIL HAS BEEN WRONG SINCE 14 JULY

Running the quarantine SQL turned up 12 rows in `metadata.etl_runs` still at
`run_status = 'running'`: runs 1, 39, 42, 43, 44, 52, 55, 56, 58, 59, 60, 61 —
etl_01, etl_17 x4, etl_22, etl_24 x6. **None of them is etl_29**, which is what
the session 6 handoff said the single orphan was. The guard in the fix script
filtered on the pipeline name, matched nothing, and correctly changed nothing.

**Root cause, confirmed in the code.** Every ETL wraps its work in
`except Exception as exc:` to write `run_status = 'failed'`. The scripts'
own guards raise `SystemExit` — 96 occurrences across 10 files — and
**`SystemExit` inherits from `BaseException`, not `Exception`, so it goes
straight past the handler.** `KeyboardInterrupt` does the same.

    the deliberate safety guards are exactly the paths
    that fail to record their own failure

Run 52 is the proof: session 5 documents it as "RUN 52 FAILED AND THE FAILURE
WAS THE POINT", the empty-window guard at `etl_22:262` fired as designed, and
the row still reads `running` today. Same for the six flood runs the session 6
table documents as failures. Runs 58 and 60 appear in no table at all.

**Fix: DONE AND PROVEN.**

- `03_etl/patch_etl_failure_logging.py` changed the handler to
  `except BaseException as exc:` across **29 scripts** (12 others have no run
  logging and were left alone). The trailing `raise` is unchanged, so Ctrl+C
  still interrupts and `sys.exit()` still exits — the only difference is that
  the row closes on the way out. `.bak` kept beside every file; all 41 files
  compile.
- `01_database/08_reconcile_orphan_etl_runs.sql` closed all 12 rows, each with
  its own documented reason. Runs 58 and 60 are marked UNDOCUMENTED rather
  than given an invented cause. Tally afterwards: 39 failed, 43 success, zero
  running.

**PROVEN, not assumed — run 84.** The first attempt to demonstrate it failed
to demonstrate anything: etl_27 was re-run to Ctrl+C it, but every CHIRPS file
was cached so it finished in seconds and logged `success`. **A test that cannot
reach the failure path is not a test** (rule E4, again).

Second attempt forced the actual guard deterministically — `EXTREME_YEARS` set
to two years against etl_28's `MIN_YEARS = 8`, chosen because that check sits
INSIDE the try block, after the run row is opened:

    run 84 | etl_28_rainfall_extremes | failed |
    Only 2 usable year(s); need 8 before an average maximum means anything

The guard's own message, in `error_message`, on a row that closed itself.
That is the whole bug, demonstrated in thirty seconds.

**The wider point, and it is the same one as rule E1 and the etl_29
re-cataloguing trap:** a control that lives beside the code instead of inside
its failure path is not a control. Three separate instances this session.

---

## Session 7 (2026-08-14) — CORRECTION PASS. No new datasets.

The goal was not to build anything. It was to make the database **true**, and
to stop chasing things that do not pay.

### THE SCOPE RULE THAT CAME OUT OF IT (Njeri)

> This is a product for land people **buy and sell**. Places where they do
> not — Chalbi, closed basins, deep ASAL rangeland — are not worth contorting
> the model for.

This is the most useful thing decided this session, and it is retroactive.
**The Chalbi row in the flood calibrator read as a FAILURE for two sessions
and pulled effort toward terrain with almost no transactions on it**, while
the constants it influenced govern Garissa and the Nairobi peri-urban belt,
where a wrong answer is a refund. Landmarks in
`calibrate_scaled_hazard.py` now carry an explicit `binding` flag, and Chalbi
is marked non-binding: reported, never allowed to choose a constant.

Generalised into the checklist header: **an item is only blocking if it can
produce a wrong answer on a parcel a client would actually transact.** Several
C-items are now marked ACCEPTED rather than left open, which is not the same
as ignoring them — it is refusing to let them block a launch.

### WHAT WAS CORRECTED

| # | Was | Now |
|---|-----|-----|
| 1 | IO land cover shares were padded-box shares | Clipped. Run 82. Built 2024 moved 2.59% → **3.34%** — the correction moved it UP 29%, so the pre-clip figures had *understated* the divergence that condemned the change layer |
| 2 | `landcover_change` live at `active` | `pending_review`, **written that way by etl_29 itself** |
| 3 | 12 `etl_runs` rows stuck at `running`, oldest a month | Reconciled, each with its own documented reason; 58 and 60 marked undocumented rather than given an invented cause |
| 4 | Every ETL's own guards bypassed their failure logger | `except BaseException` across 29 scripts. **Proven by run 84**, not assumed |
| 5 | `sources.csv` missing Impact Observatory and DE Africa; VIIRS row pointing at the abandoned EOG endpoint | All three fixed |
| 6 | `AMIN_TOP_KM2` inherited from a 42%-too-large denominator | Re-swept clipped. **Kept at 10, now evidenced rather than inherited** |
| 7 | `DATA_INVENTORY.md` silently three sessions stale | Marked superseded, with its false statements listed |
| 8 | Calibrator swept floors that cannot bind | Refuses them, and says why |

### WHAT IS PAUSED, DELIBERATELY

- **`landcover_change`** — quarantined, not deleted. The yearly snapshots ship.
- **Channel cells inflating the flood top class** (C10) — real, but the layer
  **over**-warns there, and the fix re-classes the whole country. Not blocking.
- **Closed basins / Chalbi** (C14) — accepted under the scope rule.
- **`trend_pct_yr`** — still deliberately NULL.
- **`DATA_INVENTORY.md`** — rewrite deferred until the enrichment engine
  settles, since that is what a client-facing inventory should describe.

### THE ONE PATTERN BEHIND THREE SEPARATE BUGS

Rule E1 (clip to the country) was written down, then broken twice more.
The `landcover_change` quarantine was applied by SQL, then undone by the next
successful run. The failure logger was carefully written and never fired for
the guards that actually stop these scripts.

**Every one of them is the same mistake: the control lived beside the code
instead of inside it.** A checklist row, a one-off UPDATE, an `except` clause
that does not catch what actually gets raised. The fixes this session all move
the control INTO the failure path — scripts that refuse to run on a bad mask,
a pipeline that writes its own quarantine, a handler that catches what is
really thrown.

    A rule you have to remember is a reminder.
    A rule the code cannot proceed without is a control.

### LESSON 32: THE DATABASE COULD NOT BE REBUILT FROM ITS OWN SQL FILES

Found by pulling a thread. Schema v1.6 reported eight rainfall columns where
it had created six, so two existed that no file made. Grepping `01_database`
for them returned nothing. Then:

**`02_schema_update_v1.1.sql` contained a three-line SELECT counting roads by
county and class** — the scratch query session 2 used to check road
distribution. The migration had been overwritten and lost, and nothing
noticed, because the changes were already applied to the running database and
everything worked.

What was actually missing from the recipe, recovered via
`pg_dump --schema-only`:

| | in the files | in the database |
|---|---|---|
| `land.parcels.listing_status` | 4 states | **10** — deposit_paid, coming_soon, under_survey, future_phase, cancelled, hidden |
| `land.parcels` | — | `sold_date`, `sold_price_kes` |
| status audit | — | `log_listing_status_change()` + `trg_log_listing_status`, writes to parcel_history and stamps sold_date |
| `land.parcels` index | — | `parcels_listing_idx` |
| `clients.companies` | — | `marketplace_opt_in` |
| `analytics.parcel_intelligence` | — | 7 composition/range columns |

**Nothing was broken and no data was wrong.** The database was correct. It
simply was not REPRODUCIBLE — and session 4's hosting plan ("migration is copy
the files and update one column") assumes the files ARE the schema. Rebuilding
on managed Postgres would have produced a database missing six sales statuses,
a trigger and seven columns, and the failure would have surfaced later, on a
client's data, with no obvious cause.

**The seven lost columns are better design than what v1.6 added.** A parcel is
not a point: a 50-acre plot spans many raster cells, and one value under it
hides what matters. "Elevation 1,840 m" says nothing about a plot running from
1,780 m to 1,910 m across a ravine. Each column pairs with a single-value one —
dominant class or mean for scoring, full distribution for the report.
`flood_risk_breakdown` is what makes rule D2 *reportable*: "9% of this parcel
is High" rather than one word.

Only `soil_composition` kept its comment. It is preserved verbatim; the other
six carry comments written in session 7 and explicitly marked RECONSTRUCTED,
because they were inferred from column names rather than known.

**Fixed by rewriting `02_schema_update_v1.1.sql` from the live database**,
idempotently, so it belongs in the recipe at step 2 rather than bolted on at
the end. Verified: 10 statuses, trigger present, 7 of 7 columns documented.

**RULE: the schema's source of truth was the running database, and nothing
was checking.** `pg_dump --schema-only` after any schema change, diffed
against the last snapshot, takes ten seconds and is the only thing that would
have caught this. Now checklist rule E10.

**Honest limit:** this was found by chasing two odd column names.
`land.parcels`, `clients.companies` and `analytics.parcel_intelligence` were
checked because that is where the trail led. **The rest of the schema has not
been diffed against the snapshot.** `_live_schema_snapshot.sql` is now in
`01_database/` and is the reference for doing that properly.

### STATE AT CLOSE

**P1: 25 of 27.** Counted from `datasets.csv`, not recalled. The two remaining
are not build tasks:

- `utilities.power_distribution` — Kenya Power **derived-use** licence
- `land.parcels` — arrives with the client at onboarding

**There is no ETL left to write.** The data phase is closed. What stands
between here and a sellable product is the enrichment engine, the five legal
clearances, and the third-party data behind C3/C4 (KNBS census, IEBC ward
codes) — none of which is a download.

### LICENSING WORKED THROUGH (session 7) — see LICENSING_OPTIONS_MEMO.md

No code. The output is a decision document and a materially changed contact
order.

**The share-alike exposure is three tiers, not one.** `riparian_buffers` is
HIGH — derived geometry, unambiguously a database, and it is the
differentiator. Raw `roads`/`rivers`/`waterbodies` are MEDIUM, because
**share-alike triggers on distribution, not possession**; holding OSM to
compute things is not conveyance. `parcel_intelligence` is LOW: computed
values containing no OSM data, closest to the geocoding guideline's Indirect
Hit.

**You cannot pay your way out of OSM.** OSMF sells no exemption. Comply or
replace. **OpenCellID you CAN** — Unwired Labs sell commercial licences, so
A3 may close for money rather than engineering.

**Roads cannot realistically be replaced** (nothing matches 730,006 national
segments), so they are the irreducible core of the legal question. **Rivers
can be** — which removes the HIGH exposure entirely.

### THE SPECIFICATION CHECK THAT REVERSED A RECOMMENDATION

The obvious river replacement was HydroSHEDS/HydroRIVERS: free for commercial
use, already in `sources.csv`, listed as our own backup source. Then reading
its spec: **HydroRIVERS only includes rivers with a catchment of at least
10 km²**, at 15 arc-second (~500 m) resolution.

Our riparian widths are 30 m for rivers and **6 m for streams** — and streams
are exactly what a 10 km² cutoff deletes. Swapping to it would have silently
removed most small-watercourse buffers: **a worse product failure than the
licensing exposure it was meant to fix.**

Better candidate, already on disk: **our own DEM-derived channel network**.
`etl_24` cuts channels from Copernicus GLO-30 at **≥ 5 km²** — denser than
HydroRIVERS, 93 m rather than 500 m, commercially cleared, cached in
`_acc_93m.tif`, and the threshold is ours to tune. Same demote-OSM-to-
validation pattern the flood layer already uses.

**A LEGAL QUESTION HIDES IN THAT THRESHOLD.** A riparian reserve under EMCA
attaches to a real watercourse. Set accumulation too low and we buffer
ephemeral gullies — telling a buyer their land is unbuildable when it carries
no reserve at all. That error direction is worse than missing a buffer.
Choose conservatively, document it, and re-examine confidence 3 rather than
inheriting it.

**Read the licence spec before adopting the licence-safe option.** Free and
permissive does not mean fit for the purpose it is being swapped into.

### WRA MOVED FROM LAST CONTACT TO SECOND

Ranked last when it was only about gauge data. It is actually **one request
against three blockers**: the authoritative river network that is the clean
exit from A4, the perennial/seasonal distinction `river_class` has held NULL
since session 2, and the gauge records for the flood exponent (B2).

Connecting the licensing thread to the accuracy thread is what surfaced it —
neither list showed it alone.

### IMAGERY: DO NOT BUY YET

Basemap, satellite and street view are three different questions. A rendered
tile is the textbook Produced Work, so **self-rendering from OSM is clean and
free**. Google's free tier covers a pilot's report volume. The real constraint
is not price: **Street View barely covers rural Kenya**, which is the market —
check five plots in the pilot counties before designing the feature at all.
Mapillary is not the escape route; it is CC-BY-SA, share-alike again.

One trap for this product specifically: Google Maps Platform restricts caching,
storing and printed output, and our deliverable is **a PDF we sell**.
Self-rendered OSM tiles avoid it.

### THE DECISION THAT BLOCKS THE LAWYER, AND IT IS NJERI'S

**What does a pilot client actually receive?** PDF, rendered images, an API of
values, an API of geometry, or a bulk export. The first three are almost
certainly Produced Works; the last two are shipping a database. **No lawyer can
answer the share-alike question before this is stated**, and asking early buys
an expensive "it depends". Logged as checklist B4.

### THE STANDING INSTRUCTION, RESTATED BECAUSE IT WAS BROKEN AGAIN

Six values were asserted from memory in session 6 and every one was wrong:
`metadata.sources` columns, `admin.counties.name`, county name aliases,
`slcode` semantics, EOG's OAuth secret, the LAADS ArchiveSet. Each cost a
failed run; each was settled in seconds by reading the source.

**Query it, don't recall it.** And: **a verification that prints the model's
own output is not a test — name the expected answers before choosing the
metric.**

This applies to the handoff documents too. The session 6 handoff stated that
PROGRESS.md was written up only through `connectivity.coverage` and that
nightlights, the trend calibration, schema v1.5 and flood runs 75/77 were
missing entirely. **They were already written up in full.** The handoff was
itself composed from memory, and the only genuinely missing sections were
rainfall and IO land cover. Reading the file first would have settled it —
which is the same lesson, applied to our own documentation.

---

### SUPERSEDED NOTE (kept so the reasoning is traceable)
1. **satellite.ndvi** was the last P1 raster. Decision taken: DE Africa
   Sentinel-2 annual geomedian (gm_s2_annual), read at reduced resolution from
   the COG overviews, NDVI computed from red and NIR ourselves. Sentinel-2 era
   avoids the equatorial sparsity that makes DE Africa's own Landsat NDVI
   climatology unreliable over Kenya (their docs warn against using it where
   clear-observation counts are under ~30, which is much of equatorial
   Africa). NDVI also answers the WorldCover cropland under-detection.
2. Then the data phase is COMPLETE and the enrichment engine starts.
3. Blocking before any buyer-facing population number: load the official KNBS
   census (county and ward) and migrate the LIP-W ward codes.
4. Enrichment must honour: built-up full cell = 8,606 m2 capped at 1.0;
   black cotton = Vertisols OR clay texture; rainfall runs wet; WorldCover
   cropland under-detects.
3. After the rasters: the enrichment engine (sample every layer per parcel at
   upload), then suitability scoring.
4. Still open from earlier sessions: health pharmacies (only 9 loaded), health
   ward-match at 82%, complete 1,450-ward file if found (load as v2), NULL
   county checks on coastal/border points, formatted xlsx catalogue.
5. Licensing before commercial launch is unchanged: OSM ODbL and OpenCellID
   CC-BY-SA are share-alike; WDPA is non-commercial so use KWS for the paid
   product. Cleared: Copernicus GLO-30, iSDAsoil CC-BY-4.0, CHIRPS public
   domain.

---

## Session 7 (continued, 2026-08-18) — PHASE 3 STARTS. THE PRODUCT EXISTS.

Written up in session 8 from the files, not from the handoff. Every figure
below is traceable to `05_enrichment/` or to the run output it came from; the
one number that is NOT re-confirmed is flagged where it appears.

Everything before this was assembling inputs. This is the first code in the
project whose output a client would pay for: for each parcel, sample every
relevant layer under and around the FOOTPRINT and write one row to
`analytics.parcel_intelligence`.

### WHAT WAS BUILT

| File | What it is |
|---|---|
| `05_enrichment/01_create_test_parcels.sql` | 12 landmark parcels at places six sessions of testing already validated, each carrying its expected answer in `land.parcels.test_expectation`. **Written before the engine.** |
| `05_enrichment/02_inspect_sample_parcels.py` | CRS and file inspection of the client's own exports |
| `05_enrichment/03_load_client_parcels.py` | Loads real geometry from `OAK GROVE.kmz`; deliberately refuses `THIKA ALL.csv` |
| `05_enrichment/enrich_01_engine.py` | The engine, `v0.1.0-slice` |
| `05_enrichment/verify_01_enrichment.py` | The expectations restated as executable assertions, plus geometry and coverage checks |
| `01_database/09_schema_update_v1.6.sql` | `parcel_intelligence` reconciled with what was actually built |
| `01_database/10_schema_update_v1.7.sql` | `flood_nearby_pct` |

**Result of the last recorded run: 22 passed, 0 failed, 1 known gap.**
**That count predates the two verification fixes described under LESSON 36
and has not been re-confirmed. Re-run `verify_01_enrichment.py` before
quoting it anywhere.**

### WHY A VERTICAL SLICE AND NOT TWENTY LAYERS

Four layer families — roads, flood, soils, rainfall — but covered
**completely**: run logging, composition and range columns, per-field
confidence, per-field source lineage, and the product rules that apply to
each. The hard parts are the ones that are hard to retrofit.

Same move that worked for the raster ETLs: get the pattern right once on a
narrow cut, then repeat it. Adding a layer is now a `sample_*` function, a
line in the call list, and an assertion.

### FOOTPRINT, NOT CENTROID — AND THE COLUMNS THAT MAKE IT REPORTABLE

Lesson 18, and lesson 21 which repeated it after it was written down. A
50-acre plot does not have AN elevation; it has a range, and **the range is
the buildability signal**. "Elevation 1,840 m" says nothing about a plot
running from 1,780 m to 1,910 m across a ravine.

This is what the seven composition/range columns recovered by LESSON 32 are
for, and it is why they are better design than the single-value columns v1.6
added. `flood_risk_breakdown` is what makes rule D2 *reportable*: "9% of this
parcel is High" rather than one word.

Every composition also carries its **n_pixels**, because a percentage without
its sample size invites false confidence. Karen is 8,093 m² sampled at 30 m:
**nine pixels.** "33.3% Clay" from nine pixels is three pixels, and three
pixels is noise wearing a decimal point.

### LESSON 33: RULE D2 WAS OBEYED LITERALLY AND DEFEATED IN SUBSTANCE

Rule D2 says: report the worst flood class within ~1 km, never the single
pixel. It was implemented exactly as written — maximum over any class present
in the buffer — and **run 1 of the engine returned `very_high` for 11 of 12
parcels, including TEST-KAREN-01**, which is 100% `very_low` on its own
footprint and is prime Nairobi residential land.

The cause is C10, arriving in the product for the first time. Channel cells
are set to HAND = 0 deliberately — they ARE the river — and therefore
classify Very high. **There is a channel within 1 km of almost anywhere in
Kenya.** So "worst nearby" evaluated to `very_high` everywhere.

    A rule that fires on every parcel distinguishes nothing.
    It is not a warning; it is a constant.

**The obvious repair failed too.** Requiring the class to occupy a meaningful
share of the neighbourhood looks like it should separate the cases. It cannot:

    Karen    1 km buffer   4.31% very_high   <- prime residential
    Garissa  1 km buffer   4.48% very_high   <- the town that withdrew run 57

Nearly identical numbers, opposite meanings, because the channel network is a
similar fraction of the area everywhere. **No threshold on that number
separates them, at any value.** Rule E6 territory: the quantity was wrong, not
the cut-off.

**THE SIGNAL WAS ON THE LAND ALL ALONG.** Garissa's own footprint is 25%
`very_high` while its DOMINANT class is `low`. Reporting the dominant class
buried a quarter of the parcel; reporting the neighbourhood maximum flagged
the whole country. Both were wrong, in opposite directions, and the fix is
neither: **the worst class covering a MATERIAL SHARE OF THE PARCEL sets
`flood_risk_class`** (`PARCEL_MIN_PCT = 10.0` — 10% of a plot is a corner you
cannot build on, which is worth saying; 2% is a pixel on the boundary, which
is not).

Nearby is kept, as **context with a baseline**, never as the headline.
`flood_nearby_pct` is the share of the surroundings in High or Very high,
reported against `NATIONAL_HIGH_PLUS_PCT = 12.5` — Kenya's own figure from the
run 77 country-clipped distribution (5.61 + 6.93). That is what makes the
number readable: a neighbourhood at 4% is **below the national average and
warns of nothing**, while a floodplain reading several times the baseline is
saying something. (Note for whoever tunes this: the explanatory comment in
`layer_flood` reasons against 6.93% — very high alone — while the constant it
sits beside is 12.5% — High **plus** Very high, which is what
`flood_nearby_pct` actually measures. The code is right and the comment's
arithmetic is against the wrong denominator.)

A national baseline turns a raw percentage into a statement. Without it,
every share looks alarming, which is the same failure as before wearing a
decimal point.

### LESSON 34: BOTH DISCRIMINATORS POINTED THE WRONG WAY (D7 REVERSED)

Rule D7 says black cotton risk requires BOTH SoilGrids Vertisols AND iSDA clay
texture, because SoilGrids misses the Athi-Kapiti plains — exactly where
Nairobi peri-urban selling is most active. Three formulations were tried and
**measured**, not argued:

| | formulation | result |
|---|---|---|
| 1 | Vertisols OR clay texture (classes 1–5) | flagged **Karen** (Nitisols, deep red coffee soil) and the **Aberdares** (Andosols, volcanic) |
| 2 | Vertisols OR clay texture (classes 1–2) | **lost the Athi-Kapiti case** — the one case rule D7 exists for |
| 3 | Vertisols OR (clay AND flat ground) | still lost Athi, still flagged Karen |

The measurements say why, and they are decisive:

    parcel   soil       texture     clay%   slope
    Athi     Luvisols   Clay Loam   < 30    2.94 deg   <- IS black cotton
    Karen    Nitisols   Clay Loam   >= 30   1.04 deg   <- IS NOT

**BOTH DISCRIMINATORS POINT THE WRONG WAY.** Texture says Karen is the clayer
of the two. Slope says Karen is the flatter. Adding a third signal did not
help because the third signal disagrees as well.

The reason is not a bad threshold, it is a category error in the model:
**texture measures how MUCH clay is present; black cotton is about WHICH
clay.** Smectite shrinks and swells; the kaolinite in Nitisols does not.
Both soils read clay-rich, and no layer we hold distinguishes the mineral.

Rule E6 — *if you have changed the same constant twice, stop; sweep it, and if
no value satisfies the constraints the model is wrong* — three formulations is
past that line. **Reverted to the Vertisols arm alone**, with the miss carried
as a named gap in `field_sources` rather than papered over:

> `'none'` does NOT mean 'no black cotton'. Where this reads `none` on flat
> peri-urban land around Nairobi, the report must say the check is
> **INCONCLUSIVE — never that the ground is safe.**

Logged as checklist **C16**. A verdict that is wrong on prime Nairobi land is
worse than an honest absence of one.

**Rule D7 as written is currently unimplementable and the checklist now says
so.** The rule was right about the failure mode and wrong about the remedy.

### THE FIRST REAL CLIENT FILE FOUND THREE THINGS SYNTHETIC SQUARES COULD NOT

The landmark parcels test whether the engine gets KNOWN answers right. Real
geometry tests whether it survives contact. `OAK GROVE.kmz` — 13 rings drawn
by whoever prepared the scheme — found three things in one load.

**1. PLOT-950 arrived self-intersecting.** `ST_MakeValid` repaired it and the
area went **2.10 → 8.50 acres**. The readings then showed what the repair
really cost:

    slope          14.38 deg   every neighbour in the scheme reads 1.35-4.63
    flood          31% very_high   neighbours are 100% very_low

**The repair did not just change the acreage. It changed which ground was
measured** — the polygon spread into a valley that is not part of the plot,
and the engine dutifully produced a flood warning for land the buyer is not
buying. Loaded at confidence 3 with a do-not-quote note; it needs the mutation
drawing before anything computed on it is shown to anyone.

*A repair that succeeds is not a repair that is correct.* `ST_MakeValid`
picked one reading of an ambiguous polygon; nothing in the success tells you
it picked the buyer's reading.

**2. Five "rings" were LineStrings** — paths and boundary lines drawn in
Google Earth, zero area, collinear points. An earlier filter at 0.001 acres
(≈4 m²) let PLOT-501 and PLOT-502 through at "0.00 acres" — 17 and 20 points
enclosing nothing. Threshold raised to 0.01 acres (≈40 m²), on the ground that
**no Kenyan land parcel is 40 m²**.

**3. PLOT-1069 and PLOT-1070 are `ST_Equals`.** Two plot numbers, one polygon.

### LESSON 35: THE DUPLICATE-GEOMETRY CHECK IS A PRODUCT, NOT A CHORE

In a Kenyan subdivision, two references sharing one geometry is either a
drafting duplicate or **the same ground allocated twice**. Selling one plot to
two buyers is a known failure in this market. A platform that silently
enriches both **bills for the error rather than catching it**.

So this is not a data-quality nuisance to be cleaned up before the real work.
It is the real work: catching "this plot has been sold twice" at upload is
something nobody else in this market offers, and it falls out of geometry we
already have to validate anyway.

**A validation that a client would pay to be told about is a feature.** Look
at the other load-time rejections in that light before writing any of them off
as plumbing.

### THE CSV THAT WAS DELIBERATELY NOT LOADED

`THIKA ALL.csv` holds 1,715 survey beacons with no topology. Checking the
first few points settles it: **a1, a6 and a5 are collinear** — the distance
a1→a6 plus a6→a5 equals a1→a5 to within a decimetre. Those are points ALONG a
boundary, not the corners of a plot. Consecutive groups of four are not
parcels, and nothing in the file says which beacon belongs to which plot.

Reconstructing polygons from it would be **inventing geometry and then selling
analysis computed on it**. The topology has to come from the client — a DXF, a
shapefile, or the mutation drawing.

The CRS was settled by **asking the surveyor** (Arc 1960 / UTM 37S,
EPSG:21037) and is recorded on every row as an assertion from the surveyor, in
provenance, so that if it is ever wrong the error is discoverable and every
affected parcel identifiable.

### LESSON 36: BEFORE BELIEVING A FAILURE, CHECK THE TEST

Five things went wrong in this work. **Three of them were in the verification,
not the thing verified.**

| Test | What it actually measured |
|---|---|
| Centroid-to-centroid CRS check | Returned an identical 272 m for two datums ~315 m apart. The KMZ and the CSV cover different subsets; the extent mismatch swamped the signal. |
| Nearest-beacon-to-corner CRS check | Returned 25.7 m and 17.2 m — which is simply the **mean nearest-neighbour distance in a cloud of 1,715 points over 127.6 ha** (one point per ~27 m). It was measuring point density. |
| Beacon containment | Cannot work as written: survey beacons sit **ON** boundaries, and `ST_Contains` excludes the boundary. |
| Neighbour-divergence check | Flagged TEST-ABERDARES-01 for a steep slope against its "project median". Its project is *Flood validation* — landmarks deliberately scattered across Kenya **because** they differ. Aberdares is supposed to be steep; it passed that very assertion two sections earlier. |
| Overlap check | Reported adjacent plots sharing a boundary as overlaps. That is what a subdivision **is**. |

The last two are fixed in the code and are why the verify run must be
repeated: divergence now **measures** contiguity (`ST_MaxDistance` over the
project, 10 km) instead of assuming project = subdivision on contiguous land,
and shared boundaries under 0.5% of area are counted, not printed.

The pattern in the first three is one thing: **each was a test that could not
fail cleanly.** A metric that returns a plausible number for both the right
and the wrong answer is not evidence. Rule E4 said "name the expected answers
before choosing the metric"; the sharper form is **name what the metric would
read if the thing were broken, and check that it differs from what it reads if
the thing is fine.**

And noise in a verification report is itself a defect: adjacent-boundary
"findings" are how a real finding — PLOT-1069/1070 — gets skimmed past.

### THE CONTROLS THAT LIVE INSIDE THE ENGINE

Continuing the session pattern (*a rule you have to remember is a reminder; a
rule the code cannot proceed without is a control*):

- **Raster paths are never hardcoded.** Every layer is looked up in
  `metadata.raster_catalog` by `variable`, and the row supplies path,
  confidence and the `raster_id` that goes into `field_sources`. Re-run a
  raster, re-catalogue it, and the engine follows it with no edit here.
- **`WHERE status = 'active'` in that lookup is what quarantines a condemned
  layer.** `landcover_change` sits at `pending_review` and therefore never
  reaches the engine — **with no special case written in the engine.** E9,
  applied at the point of use rather than the point of production.
- **`except BaseException`** around the run loop, so a `SystemExit` guard
  closes its own `enrichment_runs` row. E8, built in from the first version
  rather than patched in a month later.
- **Supersede, never delete.** A new enrichment marks the previous row
  `superseded` and increments `version`, inside one transaction.
- **The expectations were written before the engine existed** and live in a
  column of `land.parcels`. `verify_01_enrichment.py` restates them as
  assertions that fail a run — *prose in a column is a reminder; an assertion
  that fails is a control.*
- **Known gaps are counted separately from passes.** The Athi-Kapiti case is
  reported as a GAP, never as a PASS, because **a known limitation dressed as
  a pass is how a limitation quietly becomes a claim** — and never as a
  failure either, because nothing is broken. If it ever changes, the script
  says the gap has MOVED and to re-read C16 before assuming it is fixed.

### THREE DEFECTS FOUND BY READING THE CODE IN SESSION 8

Found while writing this up, none of them from a run:

**1. Two constants document controls that are not in the code path.**
`NEARBY_MIN_PCT = 2.0` and `FLAT_SLOPE_DEG = 3.0` each carry several lines of
justification and **neither is referenced anywhere else in the file.** They are
fossils of the two abandoned approaches in LESSONS 33 and 34. Harmless today,
and exactly the shape of thing that gets read later as a description of what
the engine does. Either wire them in or delete them — a comment that describes
a control that does not exist is worse than no comment.

**2. `cat.get("texture")` is a dead lookup.** `etl_17_isda_soils.py` catalogues
the texture raster under `variable = 'texture_class'`, never `'texture'`. The
engine tries `'texture'` first and falls through, so it works — by the
fallback, not by the lookup. Query it, don't recall it: the catalogue said
`texture_class` all along.

**3. `variable = 'nightlights'` is not unique in the catalogue.**
`etl_26_nightlights.py` writes **one row per year**, all under the same
`variable`. `load_catalogue()` keeps only the newest `raster_id` per variable,
so `cat['nightlights']` silently resolves to *whichever year was catalogued
last* — a choice nothing states and nothing tests. **Do not sample nightlights
from the raster catalogue.** The `nightlights_*` columns in
`parcel_intelligence` are ward-level figures and must come from
`demographics.nightlights_stats`, which is keyed properly by
`admin_level`/`admin_code`/`period`. Contrast `etl_29`, which does this right:
`landcover_io_2017`, `landcover_io_2023`, `landcover_io_2024` are three
distinct variables.

### WHAT THE ENGINE DOES NOT YET COVER

Not defects — not written yet. In product-value order: NDVI, land cover
(WorldCover and IO), built-up, population, nightlights, mobile coverage,
riparian buffers, protected areas, elevation/TWI, schools, health facilities,
water points, towers.

Each needs its product rules carried with it, which is the part that does not
survive being left to later: D4 and D5 for coverage, D6 for land cover, D8 for
built-up, D9 for population, D10 and D13 for nightlights, C6 for NDVI, C7 for
the three wards with no nightlights, C8 for health facilities at ward
centroid, C3 for population.

### OPEN AFTER THIS WORK

| Item | State |
|---|---|
| **C16** black cotton at Athi-Kapiti | Unresolvable with SoilGrids + iSDA + slope. `none` there is **inconclusive**, never "safe". |
| **PLOT-950** | Confidence 3, do-not-quote. Needs the mutation drawing. |
| **PLOT-1069 / PLOT-1070** | Identical geometry. A client upload must reject this, not enrich both. |
| **Re-run `verify_01_enrichment.py`** | Two verification fixes landed after the last recorded run. The 22/0/1 figure is not current. |
| **Dead constants, dead lookup, nightlights collision** | The three defects above. |

---

## Session 9 (2026-08-20) — THE ENRICHMENT ENGINE COVERS EVERY BUILT LAYER

Started at `22 passed / 0 failed / 1 gap` on four layer families. Ended at
**31 passed / 0 failed / 1 gap** on eleven. Every column with a dataset behind
it is now populated; what remains NULL has no data, not a missing sampler.

Njeri ran every command. The engine was extended in batches, verified after
each, and each batch is below with what it found rather than what it added.

### THE THREE CODE DEFECTS, CLEARED FIRST

Cleared before any new layer, because one of them was a prerequisite.

| | Was | Now |
|---|---|---|
| 1 | `NEARBY_MIN_PCT` and `FLAT_SLOPE_DEG` carried long justifying comments and were **referenced nowhere** | Deleted, with a tombstone recording that both approaches were **measured and rejected** — not merely abandoned. Karen 4.31% vs Garissa 4.48%; Karen 1.04° vs Athi 2.94°. Checklist E13 |
| 2 | The `layer_flood` comment reasoned against **6.93%** (Very high alone) while the constant beside it is **12.5%** (High + Very high, which is what the column measures) | Corrected, and re-anchored on measured values — TEST-KANO-01 at 51%, TEST-TANADELTA-01 at 44% |
| 3 | `cat['nightlights']` resolved to *whichever year was catalogued last* | `load_catalogue` now **counts collisions and reports them**. Confirmed at runtime: `nightlights: 5 active rows; kept raster_id 65, year 2024`, and **nothing else collides** |

**The verifier returned the identical count afterwards, which was the test.**
Nothing referenced the deleted constants, so an unchanged result proved they
were dead. A changed one would have proved they were not.

Defect 3 mattered because it was about to become wrong. Nightlights was the
next-but-one layer to be added, and it is now read from
`demographics.nightlights_stats` — never sampled from the catalogue.

### WHAT WAS ADDED, AND IN WHAT ORDER

| Batch | Columns | Rules carried with them |
|---|---|---|
| NDVI, land cover, built-up | 7 | C6, D6, C9, C13, D8 |
| Riparian, protected areas, rivers, amenities | 9 | A1, A4, B2, C8 |
| Population, nightlights, coverage, towers | 11 | C3, C4, C7, D4, D5, D9–D13, A2, A3 |

`built_up_pct_1km` got **its own radius constant** rather than reusing
`FLOOD_RADIUS_M`, though both are 1,000 m today. Two unrelated quantities
sharing one constant means changing the flood radius silently redefines a
column whose name says 1 km. The engine checks the constant against the
column name and complains if they part company.

### LESSON 37: A METRIC THAT REFUSES IS WORTH MORE THAN ONE THAT COPES

Three layers now decline to write rather than guess, and each refusal is
recorded with the raw value so the fault stays discoverable:

- **NDVI outside [-1, 1]** — a COG with a missing scale tag returns stored
  Int16, so NDVI reads 2100 instead of 0.21. That *looks like data*. The
  engine writes nothing and names the probable cause.
- **Built-up over 100%** — capped, with the pre-cap figure recorded and a
  warning printed. Rule D8's general form: sum the square metres, divide by
  the **true geography area** from PostGIS, then cap. Counting cells and
  multiplying by a nominal size is exactly how the 8,548 error happens.
- **Coverage below 0.01%** — see the sliver finding below.

The alternative in each case is a silently rescaled number, which is the
confident wrong answer this project exists to avoid.

### LESSON 38: TWO PRODUCERS THAT DISAGREE ARE MORE USEFUL THAN ONE THAT DOESN'T

WorldCover and Impact Observatory are both written, side by side, and never
reconciled into a single "land cover" word. IO's *Rangeland* absorbs
WorldCover's *Shrubland* **and** *Grassland*, so collapsing them would be
inventing agreement the products do not have.

The first run showed why it matters:

| Parcel | WorldCover | IO |
|---|---|---|
| TEST-BUDALANGI-01 | Cropland 43.8%, **Built-up 0.08%** | **Built** |
| TEST-KANO-01 | Grassland 81.6% | **Crops** |
| TEST-ABERDARES-01 | Grassland 72.6% | **Trees** |

Budalangi is the sharp one: **IO calls a rural floodplain village *Built*
where WorldCover measures built-up at 0.08%** — a factor of several hundred,
not a definitional shading. It matches the national figure already in this
log (IO Built 2024 at 3.34% against WorldCover's 0.3–1.5%) but landing it on
one parcel makes the consequence concrete: **IO's Built class must never be
shown to a buyer as "this area is built up".** Kano is the mirror image,
where IO's *Crops* is the better answer on irrigated land — also already
recorded here as IO's one advantage.

### LESSON 39: 0 m IS NOT A SMALL DISTANCE, IT IS CONTAINMENT

Found by a **failed assertion that was wrong twice over.**

The ordering `dist_primary_school_m: Tana delta > Karen` failed — delta 0 m
against Karen 741 m. Two errors, and the second outlived the first:

1. **Karen is Nairobi's lowest-density residential area.** Big plots, few
   schools per km². The premise was about cities in general; the parcel is
   the specific exception.
2. **0 m means a school lies INSIDE the 50-acre delta parcel.** Ordering by
   distance silently treats "there is a school on this land" as the extreme
   of "nearby", and those are different kinds of fact.

The claim attached to the test — *"if this inverts the nearest-neighbour
search is wrong, not the data"* — was an overclaim, and it is what made the
failure look alarming. The search was demonstrably fine: Kitengela 4,656 m,
Aberdares 10,008 m, Athi 3,200 m, Tana **secondary** 14,140 m. And Kakamega
independently read protected area 0 m, river 0 m and 99.87% tree cover —
three layers agreeing it sits inside Kakamega Forest.

**A test that cannot fail cleanly is not a test.** Replaced with hospitals,
where the feature is rare enough that remoteness genuinely dominates and a
large rural parcel cannot contain one by accident.

The finding that survived is worth more than the assertion was. Rule **D18**:
`dist_river_m = 0` means a watercourse crosses the plot; `dist_protected_area_m
= 0` means the parcel intersects a gazetted area, which is a stop-work
finding, not a proximity score.

### C8 SHOWED UP PER-PARCEL, AND THE ENGINE NOW DETECTS IT

`dist_hospital_m` and `dist_clinic_m` came back **identical on 6 of 20
parcels** — 1312, 1391, 1335, 1465, 2015, 834. Two different facility types
at the same metre is not coincidence; it is several facilities collapsed onto
one ward centroid. The engine now detects the equality at run time and records
that the two must not be quoted as separate distances.

### PLOT-950 NOW HAS SIX INDEPENDENT ACCUSERS

| | PLOT-950 | its OAK GROVE siblings |
|---|---|---|
| slope | 14.38° | 1.35–4.63° |
| flood | 31% `very_high` | 100% `very_low` |
| land cover | Tree cover 83.8% | Shrubland ~100% |
| NDVI | 0.783 | ~0.61 |
| river | **0 m — a watercourse crosses it** | 353–458 m |
| riparian buffer | **inside** | none inside |
| coverage polygon | 88.3008955781909 | 88.30089662557684 |

Only the first was ever checked. Five more layers, none looking for it, all
say the repaired polygon sits on ground that is not the plot. C17 is no longer
a hypothesis.

### `in_protected_area` IS CURRENTLY UNSELLABLE

Three parcels read `True` — Aberdares, Kakamega, Tana delta — and **19 of 20
protected-area answers came from WDPA**, which is non-commercial. Land inside
a gazetted area typically cannot be sold at all, so this is among the highest-
consequence fields in the report, and it is the one carrying the A1 exposure.
The KWS letter unblocks it.

This is visible because the engine now resolves **licence lineage per field**
from `metadata.sources` at run time rather than hardcoding it, and the
verifier prints an inventory:

    dist_any_road_m      OpenStreetMap/Geofabrik   ODbL-1.0                20/20
    dist_river_m         OpenStreetMap/Geofabrik   ODbL-1.0                20/20
    dist_tower_m         OpenCellID                CC-BY-SA-4.0            20/20
    in_protected_area    WDPA                      no commercial redistrib 19/20
    in_riparian_buffer   OpenStreetMap/Geofabrik   ODbL-1.0                 4/20
    coverage_2g/4g_pct   Communications Authority  NOT DECLARED            20/20

That table is the answer to "which numbers in this report came from where",
computed from the data rather than from memory. It is what a lawyer or an
acquirer will actually ask for.

### LESSON 40: THE CA DUPLICATION HAS RECURRED — AND THE DUPLICATE IS NOT THE PROBLEM

`coverage_4g_pct_safaricom` and `coverage_4g_pct_telkom` returned **identical
values to full float precision on every parcel where both were present** —
6 of 6, including 88.30089662557684 and 99.99999964919046.

Checked across the whole layer:

    safaricom_4G_2022   10,357 rows
    Telkom_4G           10,357 rows
    ST_Equals pairs     10,357   <- a 1:1 geometric match on every row
    mean |difference|   < 5e-7 percentage points

Two operators running different networks do not agree to seven decimal places
on ten thousand polygons. These are **two separately-named services on the CA
geoportal**, fetched independently by etl_25 — so the duplication is in what
the CA published, not in how we loaded it.

**THE DUPLICATE IS NOT THE PROBLEM. THE ATTRIBUTION IS.** Deleting one copy
leaves a column named after an operator whose network may not be the one
measured — which is precisely B1's original danger, where keeping the
mislabelled layer would have meant *"what we call 4G is really 3G"*.

Consequence, logged as **D17**: **do not ship per-operator 4G at all, not one
column and not both.** The combined layer (`operator='all'`, 7,134 rows,
90.08% mean) is unaffected and is what a report quotes.

Not part of the ask, and worth stating so it does not muddy the letter: the
per-operator layers average 36.04% against the combined 90.08%, which is what
one operator versus all three should look like. The row counts also differ —
10,357 against 7,134 — so the per-operator layers are a **different admin
cut**, not a subdivision. That is rule D12 harder than previously stated: not
just different vintages, different geography.

### LESSON 41: I JOINED ON A KEY THIS CODEBASE SAYS IS NOT A KEY

The first attempt to settle the operator question ran:

    JOIN connectivity.coverage b ON a.admin_name = b.admin_name

and returned **20,963 pairs from layers holding 7,134 rows** — a threefold
fan-out — with an uninterpretable 8.2% identical. The join was comparing every
sublocation against every *other* sublocation sharing a name.

`etl_25_ca_coverage.py` warns about exactly this, in a comment read earlier in
the same session:

> **THERE IS NO CODE FIELD. "slcode" LOOKS LIKE ONE AND IS NOT.** … It repeats
> because slcode holds a NAME … Nearly every Kenyan town has a sublocation
> called TOWNSHIP … So admin_code is written NULL. Inventing a code here, or
> trusting slcode as one, would give every TOWNSHIP in Kenya the same
> identifier and **let a later join fan out silently across counties.**

Rule E2 again, and the sharper form of it: **the trap was documented, in the
file, and read — and still walked into.** A row count that does not match the
source layer is the cheapest possible check that a join is wrong, and it was
available before the percentage was believed. **Check the denominator before
reading the ratio.**

The corrected query, matching on `ST_Equals(geom)`, is what produced the
figures above. The bad query had already been written into the engine's own
`field_sources` note as a "settle it" instruction — it was about to become a
control that misleads whoever runs it next — and was replaced along with the
reason `admin_name` must never be joined on.

### THE SLIVER

Telkom 4G returned **6.8e-07%** and **3.5e-07%** on two parcels: the centroid
clipping a hairline overlap between adjacent polygons. That is not a small
number, it is a geometry accident wearing a decimal point, and a report
printing "Telkom: 0.0000007%" has stated an operator percentage that was never
measured. Anything under 0.01% is now refused, raw value retained. Rule D19.

### WHAT WENT RIGHT, AND IS WORTH THE SAME ATTENTION AS WHAT DID NOT

Ruai's `nightlights_trend_radiance_yr` came back **416.18**, the highest in the
set, against a `test_expectation` written before this layer existed saying
Ruai *"ranked TOP of the absolute-radiance trend and 99.9th percentile in
verify_26"*. **An independent pipeline reproducing an earlier pipeline's
ranking** is the strongest evidence yet that the ward join is correct — and
the ward join is the part most likely to be silently wrong, because
`COALESCE(ward_code, 'LIP-W'||id)` has to match what etl_21 and etl_26 built.

Kakamega did the same for land cover: `Tree cover`, NDVI 0.817, 99.87%
single-class composition, against a prose expectation naming all three.

### ORDERINGS, AND WHY THEY BEAT THRESHOLDS

Six orderings now run. An absolute threshold on a modelled layer is a guess
wearing a decimal point — "NDVI above 0.5" depends on the year, the sensor and
the compositing, and when it fails you cannot tell whether the engine broke or
the number was always wrong. **An inverted order has one explanation.** An
ordering also fails loudly when a layer returns a constant, which a one-sided
threshold passes in silence.

    ndvi_mean       KAKAMEGA 0.817  >  LODWAR 0.143
    ndvi_mean       KERICHO 0.423   >  GARISSA 0.335
    built_up_pct    KAREN 8.82      >  TANADELTA 0.58
    dist_hospital   TANADELTA 23826 >  KAREN 3088
    pop_density     KAREN 878.67    >  TANADELTA 40.86
    nightlights     RUAI 10.46      >  TANADELTA 0.0014

The population and nightlights pairs are rule D9 made executable: "more people
near A than B" is the kind of statement this product is entitled to make, so
those are the ones that must hold. The absolute figures are not census-
calibrated (C3) and are not asserted anywhere.

### STATE AT CLOSE

**62 of 79 intelligence columns populated.** The 17 remaining have no dataset
behind them — no aspect raster, no temperature or solar layer, no zoning, no
sewer or fibre network, no landslide model, and Kenya Power still blocked on
A5. None is a missing sampler.

**Still open and unchanged:** C16 (black cotton at Athi-Kapiti), C17
(PLOT-950 — now with six independent signals), the PLOT-1069/1070 duplicate,
and the five unsent letters. **Newly open:** B1b and D17.

**Next:** suitability scoring, `analytics.suitability_scores`. The
`score_breakdown` jsonb is the product — a score without its components is a
number nobody can argue with, which in this market is a liability.

---

## Session 10 (2026-08-21) — PHASE 4 SCORING, AND THE FIRST BUYER-FACING DESIGN

Phase 4 built and verified: **71 checks passing, 0 failed, 4 of 20 parcels
correctly refused a score.** Two buyer-facing mockups built against real
enriched values, in `04_docs/mockups/`.

Njeri ran every command.

### THE THREE RULES THE SCORING MODEL IS BUILT ON

Written down first because they are the part worth keeping if the weights are
all rewritten later.

**1. The breakdown is the product; the score is the index to it.** A buyer
told "62/100" can only accept or reject it. A buyer told "62, and here is the
flood class, the slope, the soil, and what each contributed" can DISAGREE WITH
US — and a number a client can check is the only kind worth selling. So
`score_breakdown` carries, per score: every component, its raw value, its
renormalised weight, the points it contributed, the confidence, the caveats
that must be shown beside it, and anything that was missing.

**2. A BLOCKING FINDING IS NOT A LOW SCORE.** Land inside a gazetted protected
area is not "12/100 residential". It is not for sale, and scoring it 12 invites
somebody to rank it against a 15 and conclude it is merely worse. The same
holds for a parcel whose boundary we do not trust: every number would describe
the wrong ground. Those get NULL and a stated reason.

Four of twenty were refused on the first run — Aberdares, Kakamega and Tana
delta inside protected areas, PLOT-950 on boundary confidence. **Refusing to
answer is the product working**, and it is the same instinct that made the
enrichment engine refuse an NDVI value with a missing scale tag.

**3. Missing inputs cost confidence and never score mid.** A component with no
data is dropped, the remaining weights are renormalised, the omission is named,
and confidence falls. Substituting a neutral 0.5 would let an absence
masquerade as an average.

That rule bites immediately and correctly on C16: `black_cotton_risk = 'none'`
on flat ground near Nairobi is scored as UNKNOWN, not as good news. **It fires
on Karen as well as Athi**, which is right — C16 exists precisely because those
two are indistinguishable to the layers we hold.

**Weights are a product judgement and are labelled as one on every row.**
Nothing is calibrated against sale prices; we have none. They are opinions
about what a Kenyan buyer values, written where they can be argued with.

### LESSON 42: THE WEIGHT WAS NOT TOO LOW — THE SHAPE WAS WRONG

The first run gave TEST-LODWAR-01 a residential score of **54 while its flood
class was VERY HIGH**. The arithmetic was correct: flood carries 0.28 of the
residential weight, so it can only ever remove 28 points, and good road access
and coverage earned the rest back.

The obvious move was to raise the weight. **That would have been the E6
mistake** — tuning a constant when the model is what is wrong.

A buyer looking for a homesite does not trade flood risk against mobile
coverage. Past a point the hazard decides the answer and the other components
stop mattering. **That is a CEILING, not a bigger addend.** Caps now fire, the
uncapped figure stays in the breakdown so the cap can be argued with, and the
result reads correctly:

    TEST-KANO-01     residential 57.5 -> 35   agricultural 89
    TEST-LODWAR-01   residential 54.3 -> 35   agricultural 19
    TEST-GARISSA-01  residential 59.9 -> 35   commercial 50

Kano landing at 89 agricultural with residential capped is the shape working:
prime irrigated floodplain that you farm and do not build on. **9 of the 64
scores computed were capped**, so this is doing real work, not decorating.

### LESSON 43: THE CHECK FAILED, THE CHECK WAS RIGHT, AND FIXING IT MADE IT STRONGER

`verify_02_suitability.py` section B — "the components must reconstruct the
score" — failed on six scores. Every one of them capped.

It was right to fail. A capped score's components sum to the UNCAPPED figure,
because a cap is a separate stated operation and not a contribution. **The
check was written before caps existed and I did not update it when I added
them.** That is my defect, not a flaw in the rule.

The repair is the interesting part. The check now verifies BOTH halves —
components must reconstruct `uncapped_score`, AND the published score must
equal the tightest ceiling that fired. **That is stronger than the original,
not relaxed: it would now catch a cap applied at the wrong value, which the
first version could not see at all.**

Two of the three orderings also SKIPPED, because I had chosen Kakamega and Tana
delta — parcels the model correctly blocks. An ordering that depends on a
blocked parcel can never run. Re-pointed at Karen/Lodwar and Kano/Lodwar.

> A failing check is worth more than a passing one, but only if you find out
> which of the two things it compares was wrong.

### `overall_score` IS THE BEST OF THE FOUR, NOT THEIR MEAN

Land is bought for a purpose. The Kano parcel scores 89 to farm and 35 to build
on; averaging those produces a number describing no buyer. The overall figure
is the highest of the four and the breakdown names which use it refers to.

### THE BUYER-FACING DESIGN — TWO PASSES, AND THE FIRST ONE WAS WRONG

The first mockup was rejected by Njeri in one sentence: **too technical.** It
was right to reject. It showed NDVI values, soil pH numbers, "share of the
parcel footprint in each class", percentages against a national baseline,
night-light radiance, a log-scaled distance axis, and a table headed "two
independent producers".

Every one of those is a thing this build log is proud of, and **not one of them
is a thing a land buyer can act on.**

The rewrite (`04_docs/mockups/buyer_report_plain.html`) keeps the same data and
changes what is said about it:

| Was | Became |
|---|---|
| `dist_primary_school_m 741` | "7 min walk · 741 m away" |
| `NDVI 0.428`, `rainfall 587 mm` | "Rain is low — you would need a borehole for anything beyond drought-hardy crops" |
| `black_cotton_risk: none` (C16) | "We can't tell you yet. Get a soil test before you agree a building budget." |
| confidence bars | "We're confident about this" / "Treat this as a rough guide" |
| caveats as small print | a numbered **Before you pay** checklist |

**The caveats became instructions, and that is the whole trick.** "Modelled,
not measured" is a disclaimer. "Ask neighbours how high the water came in the
last big rains — they will know better than any map" is advice, and it carries
the same limitation.

The second mockup (`landiq_plot_detail.html`) follows Njeri's own design
direction: marketplace layout, map as hero, suitability score visible rather
than buried, content split across Overview / Suitability / Amenities / Risks /
Network / Legal instead of every layer on one screen.

### LESSON 44: THE UI ASKED FOR FOUR FIELDS WE CANNOT SOURCE

The design direction included a Key Insights panel with **Title Status:
Verified**, **Electricity Access: Yes (200 m)**, **Land Use Zone: Residential**
and **Internet: 4G/5G Good**. Checked against the schema:

| Field | What we actually hold |
|---|---|
| Title status | **Nothing.** `land.parcels` has no title column at all |
| Electricity | OSM power lines only. KPLC blocked on A5; the engine already flags that a large distance there is usually a mapping gap |
| Land use zone | `land.zoning` is empty. County planning data is not downloadable |
| 5G | Does not exist in our data. 4G does, as a SUBLOCATION percentage (D4) |

**Title is the dangerous one.** In this market it is the claim a buyer trusts
most and the one most likely to end in court, and we do not search the registry.

They are shown as **"Not yet checked"** with what each is waiting on. That
reads better than expected: the gaps become a visible roadmap, and *"we do not
search the Lands registry — your advocate must"* is a trust signal rather than
a weakness. The Legal tab is entirely honest limits and is arguably the most
persuasive tab on the page.

**Logged as D20:** never display a field the platform does not source. A blank
labelled "Not yet checked" is a product. A plausible-looking value is a
liability.

### THE DELIVERY ARCHITECTURE, DECIDED

How the platform reaches a client's website, settled by the licensing question
rather than the engineering one:

| Model | What the client receives | ODbL exposure |
|---|---|---|
| **Embed widget** (script/iframe) | Nothing — it renders from our server into their page | **Lowest** |
| REST API of values | Numbers, no geometry | Low–medium |
| API of geometry / bulk export | A database | **Highest — this is conveyance** |

**The embed widget wins.** Two lines in the client's page; everything else
served by us and rendered server-side, which is exactly what B4 already
committed to — *ship values and pictures, never geometry*. It also means the
API key is a revocation switch, the ODbL attribution is baked into what we
render rather than left to their developer, and *"the client never received the
database"* is a defensible sentence.

**Consequence: no bespoke integration per client.** If we are doing custom work
per customer we are a consultancy, not a product.

**The one real handshake is plot identity.** Their site calls it "Plot 457";
our database calls it `parcel_ref`. That mapping is agreed at onboarding and it
is where the conversation with their developer actually happens — not the embed
code. Getting it wrong serves the wrong plot's analysis to a buyer, which is
the worst failure this product has.

### STATE AT CLOSE

- **Phases 1–4 complete.** Data, enrichment (62 of 79 columns, 31 assertions),
  scoring (71 checks), and a defined buyer-facing shape.
- **Phase 5 (delivery) has a defined shape** and is not started.
- **The long pole is legal.** A1 and A5 block fields the LandIQ page currently
  shows holes for. The KWS letter is the cheapest high-value move on the board
  — it closes A1 *and* fixes the coarse-boundary risk that had Kakamega blocked.

**Newly open:** B5 (title — Njeri's decision), B6 (county zoning), D20.

**Two observations worth carrying forward.** The seven OAK GROVE plots all
score 94–98 residential; neighbours should be similar, but that tight a band at
the top means the model is not discriminating between plots in one scheme,
which is exactly the comparison a buyer in that scheme is making. And Kakamega
is blocked on a WDPA boundary, which is coarse — on a real client parcel near a
park edge that could refuse saleable land.

---

## Session 11 (2026-08-24) — DELIVERY HARDENING, LANDMARKS, AND ONE MISTAKE IN FOUR COSTUMES

**43 checks passing, 0 failed, 1 known gap.** Six new source tables holding
14,221 rows, twelve new intelligence columns, two migrations, twelve new
assertions, and a buyer-facing page built on nothing but measured values.

Njeri ran every command.

The session divides cleanly in two. The morning was spent reading what Phase 5
actually produced — four PDFs and one API response — and fixing what reading
them exposed. The afternoon built the landmarks layer. **Both halves taught the
same thing**, which is why Lesson 48 is the one worth keeping if the rest is
forgotten.

### WHAT READING FOUR PDFs FOUND THAT VERIFICATION DID NOT

`verify_01` was green. `verify_02` was green. Twenty PDFs generated without
error. Then four of them were read end to end, and every one carried a defect
no assertion was ever going to catch, because each was a defect of MEANING
rather than of value.

**PLOT-950 contradicted itself on a single page.** A red panel at the top said

> Every score would be computed on ground we are not confident is the plot.

and four lines below it, the report asserted

> On the plot itself: river.

Both statements were generated correctly. The second is the more dangerous, and
the reason is worth stating precisely: **a distance survives a bad boundary and
containment does not.** A hospital 1.6 km from roughly-there is 1.6 km from
actually-there. But "a river crosses this land" is a claim made ENTIRELY out of
the boundary — the one thing the panel above had just disowned. It is also, of
the two, the claim a buyer would act on. Containment now downgrades to
proximity when the boundary is untrusted, the distance list carries the caveat,
and a MEASURED acreage is suppressed on the same reasoning while a
CLIENT-STATED one survives, because that is their claim and we are only
repeating it.

**Three smaller ones, same reading.** "98 / 100 — Good best suited to
residential use" had no punctuation between the band and the clause, because
two renderers were each composing half a sentence; neither writes sentences
now. "On the plot itself: main road. Not nearby — on the land." read as a
fragment somebody forgot to finish. And Athi Plains led its **What is nearby**
list with

    River          2 min walk      161 m away

ranked first because the list sorts by distance and 161 m is the smallest
number on the page. Under that heading it reads as a selling point. It is a
riparian setback and a flood path. Distance alone cannot tell an amenity from a
constraint, so the kind is now declared rather than inferred, and features sort
last under their own note.

**And the plot size was missing from all twenty reports** — see Lesson 49,
which is about how I nearly explained that wrongly.

### LESSON 45: THE CAP HAD TO SURVIVE THE SKIM

TEST-KANO-01 printed, across the top of its report:

> **89 / 100 — Good**   best suited to agricultural use

on a plot the model had **capped at 35 for residential** because a large part of
it sits in the highest flood categories. Everything needed to see that was on
the page. The flood question said "Yes, it floods". The note said the overall
figure is the best of the four. Lesson 42 had already established that a cap is
a different KIND of statement from a low score.

None of it helps. **The overwhelming majority of people opening a report on a
plot intend to build on it**, they read the big number first, and "89 / 100 —
Good" is what they carry away from a page whose own model says do not build
here. A distinction that exists only in the database is not a distinction the
product has.

Capped uses are now named beside the headline. The cap's own reason string is
NOT reproduced — those are written for the breakdown and read like model
internals — because the four questions below already say why in plain words.

**And the first version of that fix was itself wrong**, which is the more
useful half. It picked the capped use with the LOWEST score. On Kano three uses
were capped, so it printed:

> We do not recommend this plot for **holding as an investment** — it scores 32
> out of 100 for that.

True, and useless. Kano floods. The sentence a buyer needed was about BUILDING,
and sorting by number buried it behind a market opinion nobody opened the
report for. **"Lowest number" and "worst consequence" are different questions**,
and the paragraph promised the second while the code answered the first.
Selection is now by consequence in a fixed order — residential, commercial,
agricultural — and investment never leads it. A weak investment score costs
money slowly; a house on a floodplain is a different category of wrong.

### LESSON 46: ONE MESSAGE OUTWARD, EVERY REASON IN THE LOG

The embed API refused a key that was correct. The response said:

> Unknown, revoked or expired API key.

The key hashed correctly, was not revoked, had not expired, and owned all twenty
parcels. **All three things the message named were false.** The company behind
it had `is_active = false`, and four separate conditions had been folded into
one `WHERE` clause, so a failure of any of them produced a message naming the
other three. Finding out which took a seven-column diagnostic query.

The response is right to be vague. Telling an unauthenticated caller "that key
is real but the account is suspended" confirms which keys exist — a probing
oracle. **The LOG has no reason to be vague, and that is the whole fix.** The
checks are made separately and named, the `HTTPException` body is byte-identical
in every case, and the reason prints to the server window. A client's developer
on the phone would otherwise spend an afternoon regenerating a key that was
never the problem.

> Hide the difference from the caller. Never hide it from yourself.

### LESSON 47: THE BUYER PAGE TOOK THREE PASSES, AND THE CLIENT WAS RIGHT TWICE

Session 10 had already rejected one mockup as too technical. This session the
same thing happened twice more, and both corrections were the client's.

The first pass built an honest analysis page with a **What we do not check**
section — title, zoning, electricity, valuation — six items with who to ask for
each. It is the most defensible page in the build. Njeri's response:

> all this details cannot go to the client side... that should be in our later
> stage after getting clients

**She is right, and the distinction is a product one, not a moral one.** The
limits are a SALES asset in the conversation with the seller, where they prove
we know what we do not know. On a listing page in front of a buyer they are a
wall of disclaimers between that person and the plot. Same content, opposite
effect, decided entirely by who is reading. The limits now live in the seller
pitch and the PDF; the listing page carries one sentence.

Her spec for what a buyer actually wants, verbatim: satellite image and street
view, directions, soil type, rainfall in simple terms not figures, distances to
amenities, famous landmarks nearby, **and the status of surrounding plots**.

Three findings came out of building it:

**The satellite image was never actually blocked.** B4 kept imagery out of the
PDF because Google's terms are strict about tiles inside a document we sell. A
web page is a different licence — the Maps JavaScript API and Street View
embeds are exactly that product. And drawing the plot boundary over the tile is
clean, because that boundary is **the seller's own survey data**, not ours and
not OSM's. It conveys nothing. B4 was read as "no imagery" when what it decided
was "no imagery in the PDF".

**The availability panel is the strongest sales feature on the page and we
cannot fill it.** All eight OAK GROVE plots read `listing_status = 'available'`
and every `price_kes` is NULL. "3 of 7 sold" was my placeholder and the data
says otherwise. This is not a code gap — it is a **second onboarding handshake**,
and unlike the `parcel_ref` mapping it has to keep happening after go-live.
Logged as D24.

**Four columns of imagined precision came off the page.** No invented price, no
fabricated sold/deposit statuses, and `dist_airport_m` removed entirely — see
below.

### LESSON 48: THE QUERY WAS RIGHT AND THE ANSWER WAS STILL WRONG

**This is the session's lesson.** Four defects, four different layers, one
shape. In every case the SQL was correct, the join was correct, the distance was
correct to the metre — and the answer was wrong, because the column was
answering the question NEXT TO the one a buyer was asking.

**1. `Shekiko Airport (disused)`.** TEST-TANADELTA-01's nearest airport, 7.5 km,
correctly measured. A disused airstrip is not somewhere anyone can fly into, and
a listing page offering it as "your nearest airport" is a false promise made in
the source's own words. Geometry cannot tell a live facility from a dead one.
**OSM said so in the NAME**, so a name filter can find it — deliberately narrow,
matching those words in parentheses or as whole words, so a genuine "Former
Presidents Road" survives. Tana Delta moved to Witu Airstrip at 19.9 km: 12 km
worse, and true.

**2. `GSU Airstrip`, on all eight OAK GROVE plots, 6.9 km.** Fully operational.
A General Service Unit airstrip no land buyer will ever fly from. **Nothing in
the name, the geometry or the tags says so** — a filter could never find this
one, because the defect is not in the data at all. It is in the question:
*nearest airport* and *where would I fly from* are the same question only where
every airport takes passengers.

The repair was NOT to exclude airstrips. `domestic` is inferred by name — an
airport is `international` if it says so and `domestic` otherwise — so
`domestic` is a DEFAULT, not a finding, and it is full of bush strips
indistinguishable from GSU. Filtering on it would trade a visibly wrong answer
for an invisibly wrong one. `international` is the one class we verify: four
facilities, each named so by its operator. That got its own column pair, and it
is what buyers see. `dist_airport_m` is unchanged and must be labelled
**airstrip** on any page — the difference is the entire point.

**3. A village is not a town centre.** `admin.places` holds 9,323 rows and 8,679
are villages. Measuring `dist_town_centre_m` to the nearest place of any kind
would put almost every parcel in Kenya a few hundred metres from a "town
centre" — the column would measure **OSM's tagging density, not a buyer's
access to a town**. Restricted to city / town / national_capital: 436 rows. The
same trap as C8, where health facilities stack on ward centroids.

**4. A named major road must be FURTHER than the paved road.** `dist_paved_road_m`
takes the nearest good-class road whether or not anyone named it;
`dist_major_road_m` requires a name, because a buyer cannot orient by an
unnamed trunk road. It is a strict subset, so it can only ever be larger. That
is now a verifier invariant — and the only assertion in the file that needs no
knowledge of Kenya at all, which is exactly why it is worth having.

> A filter can catch a fact the source admits about itself.
> It cannot catch a question that was subtly wrong.
> Only reading the answers out loud catches that.

Logged as D23 and E14. It is the direct descendant of D20 — that rule says never
display a field we do not source; this one says **a field we DO source can still
be the wrong answer**, and no amount of verification will say so.

### LESSON 49: I WROTE THE CAUSE BEFORE I CHECKED IT

All twenty PDFs printed no acreage. Not a wrong figure — the line was simply
absent, because the subtitle renders `size · project` and collapsed silently
when size came back None.

My explanation was that `SELECT p.area_sqm, ... i.*` names a column and then
splats a table holding one of the same name; a result row is keyed BY NAME, so
the duplicate collapses and the last one wins. It is a real bug shape. It
matched the symptom exactly. It is the third cousin of the `admin_name` join
that fanned out threefold and the raster catalogue serving whichever
`nightlights` row came back first. **I wrote the comment before I checked.**

It is not what happened. `analytics.parcel_intelligence` has 86 columns and
`area_sqm` is not one of them; the only name it shares with `land.parcels` is
`parcel_id`. Nothing was shadowed. **`land.parcels.area_sqm` is simply NULL** —
nullable, unpopulated at load, while `geom` is NOT NULL and had the answer all
along. Size now comes from `ST_Area(geom::geography)`, labelled *(our
measurement)*, with the client's stated figure winning when present.

**Rule E2 does not stop applying because the guess is a good one.** A confident
wrong cause, written into a comment, outlives the bug it misdescribes. The
aliasing went in anyway — for `parcel_id`, which IS shared, and which on a
parcel with no intelligence row would have written a null key into
`reports.reports`. The real bug was sitting one column over from the one I
invented.

### THE LANDMARKS BUILD

Six tables from OSM layers already on disk — nothing downloaded, and no licence
letter needed, because what we publish is a DISTANCE and a NAME.

| Table | Rows | |
|---|---|---|
| `admin.places` | 9,323 | new table; there had never been anywhere to measure "distance to town centre" FROM |
| `transport.airports` | 255 | 4 international, 246 domestic, 5 airstrips |
| `transport.bus_stops` | 1,082 | every transport stop, not just buses — see E15 |
| `transport.railways` | 750 | |
| `social.markets` | 2,205 | confidence 2; county registers are the primary |
| `social.public_services` | 606 | |

**One script, not six**, because all six are the same three steps against the
same file set and six scripts would be six copies of one bug. The SPECS table is
the only thing written six times.

**The preflight is the part worth keeping.** The first run loaded 9,323 places
and then died on row one of the next table: `transport.airports.facility_type`
is CHECK-constrained to international / domestic / airstrip and the spec said
`airport`. I had invented the vocabulary from what OSM calls things instead of
reading the schema that has to accept them — E2 again, on a constraint sitting
in a snapshot I had already opened twice that day. The repair is not to be more
careful. **The script now reads the real constraints out of `pg_constraint` and
runs in two passes** — read and classify everything, validate every produced
value, and only then load. A mismatch names all offenders at once and loads
nothing, instead of leaving the database in a state no single run produced.

Two smaller traps, both worth the words:

**`(n or "")` does nothing here.** A missing name arrives from pandas as `NaN`,
`NaN` is a float, and **floats are truthy** — so `or` never fires and
`NaN.lower()` raises. Coercion is by `isinstance`. The second half of that fix
matters more: the unnamed-row drop now runs BEFORE classification, so the
name-based classifier never sees a missing name rather than being hardened
against one.

**Parsing a CHECK constraint by splitting on commas is silently wrong.**
Elements come back as `'domestic'::text`, so `strip("'")` leaves
`domestic'::text` — the trailing character is `t`, not a quote — and the
validator would then reject every value INCLUDING the correct ones. Quoted
literals are pulled with a regex, tested against both real constraint strings
before shipping.

### STATE AT CLOSE

- **Phases 1–4 complete. Phase 5 built and hardened**, not yet exercised end to
  end against a live client site.
- **43 assertions**, up from 31. Section G is new: five landmark IDENTITIES —
  Karen→Wilson, Ruai→JKIA, Lodwar→Lodwar, Garissa→Garissa, Kericho→Kericho —
  and five invariants. The identities are a different KIND of assertion from
  everything above them: those check a modelled number against a documented
  expectation, these check a name against a fact about Kenya that no model
  produced.
- **The buyer page carries nothing invented.** No price, because there is none.
  Eight plots all available, because that is what the seller's records say.
- **The long pole is still legal**, and it grew by one: **WASREB Majidata** is
  the national georeferenced water and sewer network system under Water Act 2016
  s.111 — exactly `dist_water_line_m` and `dist_sewer_m`. Buried mains mean OSM
  has nothing, so it is a letter or it is nothing. Logged as B7 and bundled with
  the KWS batch.

**Newly open:** B7, D23, D24, E14, E15.

**Still the cheapest high-value move on the board:** the KWS letter. It closes
A1 and fixes the coarse-boundary risk that has Kakamega blocked, and it has been
the answer to this question for four sessions.

---

## Session 11 (2026-08-24) — DELIVERY HARDENING, LANDMARKS, AND ONE MISTAKE IN FOUR COSTUMES

**43 checks passing, 0 failed, 1 known gap.** Six new source tables holding
14,221 rows, twelve new intelligence columns, two migrations, twelve new
assertions, and a buyer-facing page built on nothing but measured values.

Njeri ran every command.

The session divides cleanly in two. The morning was spent reading what Phase 5
actually produced — four PDFs and one API response — and fixing what reading
them exposed. The afternoon built the landmarks layer. **Both halves taught the
same thing**, which is why Lesson 48 is the one worth keeping if the rest is
forgotten.

### WHAT READING FOUR PDFs FOUND THAT VERIFICATION DID NOT

`verify_01` was green. `verify_02` was green. Twenty PDFs generated without
error. Then four of them were read end to end, and every one carried a defect
no assertion was ever going to catch, because each was a defect of MEANING
rather than of value.

**PLOT-950 contradicted itself on a single page.** A red panel at the top said

> Every score would be computed on ground we are not confident is the plot.

and four lines below it, the report asserted

> On the plot itself: river.

Both statements were generated correctly. The second is the more dangerous, and
the reason is worth stating precisely: **a distance survives a bad boundary and
containment does not.** A hospital 1.6 km from roughly-there is 1.6 km from
actually-there. But "a river crosses this land" is a claim made ENTIRELY out of
the boundary — the one thing the panel above had just disowned. It is also, of
the two, the claim a buyer would act on. Containment now downgrades to
proximity when the boundary is untrusted, the distance list carries the caveat,
and a MEASURED acreage is suppressed on the same reasoning while a
CLIENT-STATED one survives, because that is their claim and we are only
repeating it.

**Three smaller ones, same reading.** "98 / 100 — Good best suited to
residential use" had no punctuation between the band and the clause, because
two renderers were each composing half a sentence; neither writes sentences
now. "On the plot itself: main road. Not nearby — on the land." read as a
fragment somebody forgot to finish. And Athi Plains led its **What is nearby**
list with

    River          2 min walk      161 m away

ranked first because the list sorts by distance and 161 m is the smallest
number on the page. Under that heading it reads as a selling point. It is a
riparian setback and a flood path. Distance alone cannot tell an amenity from a
constraint, so the kind is now declared rather than inferred, and features sort
last under their own note.

**And the plot size was missing from all twenty reports** — see Lesson 49,
which is about how I nearly explained that wrongly.

### LESSON 45: THE CAP HAD TO SURVIVE THE SKIM

TEST-KANO-01 printed, across the top of its report:

> **89 / 100 — Good**   best suited to agricultural use

on a plot the model had **capped at 35 for residential** because a large part of
it sits in the highest flood categories. Everything needed to see that was on
the page. The flood question said "Yes, it floods". The note said the overall
figure is the best of the four. Lesson 42 had already established that a cap is
a different KIND of statement from a low score.

None of it helps. **The overwhelming majority of people opening a report on a
plot intend to build on it**, they read the big number first, and "89 / 100 —
Good" is what they carry away from a page whose own model says do not build
here. A distinction that exists only in the database is not a distinction the
product has.

Capped uses are now named beside the headline. The cap's own reason string is
NOT reproduced — those are written for the breakdown and read like model
internals — because the four questions below already say why in plain words.

**And the first version of that fix was itself wrong**, which is the more
useful half. It picked the capped use with the LOWEST score. On Kano three uses
were capped, so it printed:

> We do not recommend this plot for **holding as an investment** — it scores 32
> out of 100 for that.

True, and useless. Kano floods. The sentence a buyer needed was about BUILDING,
and sorting by number buried it behind a market opinion nobody opened the
report for. **"Lowest number" and "worst consequence" are different questions**,
and the paragraph promised the second while the code answered the first.
Selection is now by consequence in a fixed order — residential, commercial,
agricultural — and investment never leads it. A weak investment score costs
money slowly; a house on a floodplain is a different category of wrong.

### LESSON 46: ONE MESSAGE OUTWARD, EVERY REASON IN THE LOG

The embed API refused a key that was correct. The response said:

> Unknown, revoked or expired API key.

The key hashed correctly, was not revoked, had not expired, and owned all twenty
parcels. **All three things the message named were false.** The company behind
it had `is_active = false`, and four separate conditions had been folded into
one `WHERE` clause, so a failure of any of them produced a message naming the
other three. Finding out which took a seven-column diagnostic query.

The response is right to be vague. Telling an unauthenticated caller "that key
is real but the account is suspended" confirms which keys exist — a probing
oracle. **The LOG has no reason to be vague, and that is the whole fix.** The
checks are made separately and named, the `HTTPException` body is byte-identical
in every case, and the reason prints to the server window. A client's developer
on the phone would otherwise spend an afternoon regenerating a key that was
never the problem.

> Hide the difference from the caller. Never hide it from yourself.

### LESSON 47: THE BUYER PAGE TOOK THREE PASSES, AND THE CLIENT WAS RIGHT TWICE

Session 10 had already rejected one mockup as too technical. This session the
same thing happened twice more, and both corrections were the client's.

The first pass built an honest analysis page with a **What we do not check**
section — title, zoning, electricity, valuation — six items with who to ask for
each. It is the most defensible page in the build. Njeri's response:

> all this details cannot go to the client side... that should be in our later
> stage after getting clients

**She is right, and the distinction is a product one, not a moral one.** The
limits are a SALES asset in the conversation with the seller, where they prove
we know what we do not know. On a listing page in front of a buyer they are a
wall of disclaimers between that person and the plot. Same content, opposite
effect, decided entirely by who is reading. The limits now live in the seller
pitch and the PDF; the listing page carries one sentence.

Her spec for what a buyer actually wants, verbatim: satellite image and street
view, directions, soil type, rainfall in simple terms not figures, distances to
amenities, famous landmarks nearby, **and the status of surrounding plots**.

Three findings came out of building it:

**The satellite image was never actually blocked.** B4 kept imagery out of the
PDF because Google's terms are strict about tiles inside a document we sell. A
web page is a different licence — the Maps JavaScript API and Street View
embeds are exactly that product. And drawing the plot boundary over the tile is
clean, because that boundary is **the seller's own survey data**, not ours and
not OSM's. It conveys nothing. B4 was read as "no imagery" when what it decided
was "no imagery in the PDF".

**The availability panel is the strongest sales feature on the page and we
cannot fill it.** All eight OAK GROVE plots read `listing_status = 'available'`
and every `price_kes` is NULL. "3 of 7 sold" was my placeholder and the data
says otherwise. This is not a code gap — it is a **second onboarding handshake**,
and unlike the `parcel_ref` mapping it has to keep happening after go-live.
Logged as D24.

**Four columns of imagined precision came off the page.** No invented price, no
fabricated sold/deposit statuses, and `dist_airport_m` removed entirely — see
below.

### LESSON 48: THE QUERY WAS RIGHT AND THE ANSWER WAS STILL WRONG

**This is the session's lesson.** Four defects, four different layers, one
shape. In every case the SQL was correct, the join was correct, the distance was
correct to the metre — and the answer was wrong, because the column was
answering the question NEXT TO the one a buyer was asking.

**1. `Shekiko Airport (disused)`.** TEST-TANADELTA-01's nearest airport, 7.5 km,
correctly measured. A disused airstrip is not somewhere anyone can fly into, and
a listing page offering it as "your nearest airport" is a false promise made in
the source's own words. Geometry cannot tell a live facility from a dead one.
**OSM said so in the NAME**, so a name filter can find it — deliberately narrow,
matching those words in parentheses or as whole words, so a genuine "Former
Presidents Road" survives. Tana Delta moved to Witu Airstrip at 19.9 km: 12 km
worse, and true.

**2. `GSU Airstrip`, on all eight OAK GROVE plots, 6.9 km.** Fully operational.
A General Service Unit airstrip no land buyer will ever fly from. **Nothing in
the name, the geometry or the tags says so** — a filter could never find this
one, because the defect is not in the data at all. It is in the question:
*nearest airport* and *where would I fly from* are the same question only where
every airport takes passengers.

The repair was NOT to exclude airstrips. `domestic` is inferred by name — an
airport is `international` if it says so and `domestic` otherwise — so
`domestic` is a DEFAULT, not a finding, and it is full of bush strips
indistinguishable from GSU. Filtering on it would trade a visibly wrong answer
for an invisibly wrong one. `international` is the one class we verify: four
facilities, each named so by its operator. That got its own column pair, and it
is what buyers see. `dist_airport_m` is unchanged and must be labelled
**airstrip** on any page — the difference is the entire point.

**3. A village is not a town centre.** `admin.places` holds 9,323 rows and 8,679
are villages. Measuring `dist_town_centre_m` to the nearest place of any kind
would put almost every parcel in Kenya a few hundred metres from a "town
centre" — the column would measure **OSM's tagging density, not a buyer's
access to a town**. Restricted to city / town / national_capital: 436 rows. The
same trap as C8, where health facilities stack on ward centroids.

**4. A named major road must be FURTHER than the paved road.** `dist_paved_road_m`
takes the nearest good-class road whether or not anyone named it;
`dist_major_road_m` requires a name, because a buyer cannot orient by an
unnamed trunk road. It is a strict subset, so it can only ever be larger. That
is now a verifier invariant — and the only assertion in the file that needs no
knowledge of Kenya at all, which is exactly why it is worth having.

> A filter can catch a fact the source admits about itself.
> It cannot catch a question that was subtly wrong.
> Only reading the answers out loud catches that.

Logged as D23 and E14. It is the direct descendant of D20 — that rule says never
display a field we do not source; this one says **a field we DO source can still
be the wrong answer**, and no amount of verification will say so.

### LESSON 49: I WROTE THE CAUSE BEFORE I CHECKED IT

All twenty PDFs printed no acreage. Not a wrong figure — the line was simply
absent, because the subtitle renders `size · project` and collapsed silently
when size came back None.

My explanation was that `SELECT p.area_sqm, ... i.*` names a column and then
splats a table holding one of the same name; a result row is keyed BY NAME, so
the duplicate collapses and the last one wins. It is a real bug shape. It
matched the symptom exactly. It is the third cousin of the `admin_name` join
that fanned out threefold and the raster catalogue serving whichever
`nightlights` row came back first. **I wrote the comment before I checked.**

It is not what happened. `analytics.parcel_intelligence` has 86 columns and
`area_sqm` is not one of them; the only name it shares with `land.parcels` is
`parcel_id`. Nothing was shadowed. **`land.parcels.area_sqm` is simply NULL** —
nullable, unpopulated at load, while `geom` is NOT NULL and had the answer all
along. Size now comes from `ST_Area(geom::geography)`, labelled *(our
measurement)*, with the client's stated figure winning when present.

**Rule E2 does not stop applying because the guess is a good one.** A confident
wrong cause, written into a comment, outlives the bug it misdescribes. The
aliasing went in anyway — for `parcel_id`, which IS shared, and which on a
parcel with no intelligence row would have written a null key into
`reports.reports`. The real bug was sitting one column over from the one I
invented.

### THE LANDMARKS BUILD

Six tables from OSM layers already on disk — nothing downloaded, and no licence
letter needed, because what we publish is a DISTANCE and a NAME.

| Table | Rows | |
|---|---|---|
| `admin.places` | 9,323 | new table; there had never been anywhere to measure "distance to town centre" FROM |
| `transport.airports` | 255 | 4 international, 246 domestic, 5 airstrips |
| `transport.bus_stops` | 1,082 | every transport stop, not just buses — see E15 |
| `transport.railways` | 750 | |
| `social.markets` | 2,205 | confidence 2; county registers are the primary |
| `social.public_services` | 606 | |

**One script, not six**, because all six are the same three steps against the
same file set and six scripts would be six copies of one bug. The SPECS table is
the only thing written six times.

**The preflight is the part worth keeping.** The first run loaded 9,323 places
and then died on row one of the next table: `transport.airports.facility_type`
is CHECK-constrained to international / domestic / airstrip and the spec said
`airport`. I had invented the vocabulary from what OSM calls things instead of
reading the schema that has to accept them — E2 again, on a constraint sitting
in a snapshot I had already opened twice that day. The repair is not to be more
careful. **The script now reads the real constraints out of `pg_constraint` and
runs in two passes** — read and classify everything, validate every produced
value, and only then load. A mismatch names all offenders at once and loads
nothing, instead of leaving the database in a state no single run produced.

Two smaller traps, both worth the words:

**`(n or "")` does nothing here.** A missing name arrives from pandas as `NaN`,
`NaN` is a float, and **floats are truthy** — so `or` never fires and
`NaN.lower()` raises. Coercion is by `isinstance`. The second half of that fix
matters more: the unnamed-row drop now runs BEFORE classification, so the
name-based classifier never sees a missing name rather than being hardened
against one.

**Parsing a CHECK constraint by splitting on commas is silently wrong.**
Elements come back as `'domestic'::text`, so `strip("'")` leaves
`domestic'::text` — the trailing character is `t`, not a quote — and the
validator would then reject every value INCLUDING the correct ones. Quoted
literals are pulled with a regex, tested against both real constraint strings
before shipping.

### STATE AT CLOSE

- **Phases 1–4 complete. Phase 5 built and hardened**, not yet exercised end to
  end against a live client site.
- **43 assertions**, up from 31. Section G is new: five landmark IDENTITIES —
  Karen→Wilson, Ruai→JKIA, Lodwar→Lodwar, Garissa→Garissa, Kericho→Kericho —
  and five invariants. The identities are a different KIND of assertion from
  everything above them: those check a modelled number against a documented
  expectation, these check a name against a fact about Kenya that no model
  produced.
- **The buyer page carries nothing invented.** No price, because there is none.
  Eight plots all available, because that is what the seller's records say.
- **The long pole is still legal**, and it grew by one: **WASREB Majidata** is
  the national georeferenced water and sewer network system under Water Act 2016
  s.111 — exactly `dist_water_line_m` and `dist_sewer_m`. Buried mains mean OSM
  has nothing, so it is a letter or it is nothing. Logged as B7 and bundled with
  the KWS batch.

**Newly open:** B7, D23, D24, E14, E15.

**Still the cheapest high-value move on the board:** the KWS letter. It closes
A1 and fixes the coarse-boundary risk that has Kakamega blocked, and it has been
the answer to this question for four sessions.

---

## Session 11 (2026-08-24) — DELIVERY HARDENING, LANDMARKS, AND ONE MISTAKE IN FOUR COSTUMES

**43 checks passing, 0 failed, 1 known gap.** Six new source tables holding
14,221 rows, twelve new intelligence columns, two migrations, twelve new
assertions, and a buyer-facing page built on nothing but measured values.

Njeri ran every command.

The session divides cleanly in two. The morning was spent reading what Phase 5
actually produced — four PDFs and one API response — and fixing what reading
them exposed. The afternoon built the landmarks layer. **Both halves taught the
same thing**, which is why Lesson 48 is the one worth keeping if the rest is
forgotten.

### WHAT READING FOUR PDFs FOUND THAT VERIFICATION DID NOT

`verify_01` was green. `verify_02` was green. Twenty PDFs generated without
error. Then four of them were read end to end, and every one carried a defect
no assertion was ever going to catch, because each was a defect of MEANING
rather than of value.

**PLOT-950 contradicted itself on a single page.** A red panel at the top said

> Every score would be computed on ground we are not confident is the plot.

and four lines below it, the report asserted

> On the plot itself: river.

Both statements were generated correctly. The second is the more dangerous, and
the reason is worth stating precisely: **a distance survives a bad boundary and
containment does not.** A hospital 1.6 km from roughly-there is 1.6 km from
actually-there. But "a river crosses this land" is a claim made ENTIRELY out of
the boundary — the one thing the panel above had just disowned. It is also, of
the two, the claim a buyer would act on. Containment now downgrades to
proximity when the boundary is untrusted, the distance list carries the caveat,
and a MEASURED acreage is suppressed on the same reasoning while a
CLIENT-STATED one survives, because that is their claim and we are only
repeating it.

**Three smaller ones, same reading.** "98 / 100 — Good best suited to
residential use" had no punctuation between the band and the clause, because
two renderers were each composing half a sentence; neither writes sentences
now. "On the plot itself: main road. Not nearby — on the land." read as a
fragment somebody forgot to finish. And Athi Plains led its **What is nearby**
list with

    River          2 min walk      161 m away

ranked first because the list sorts by distance and 161 m is the smallest
number on the page. Under that heading it reads as a selling point. It is a
riparian setback and a flood path. Distance alone cannot tell an amenity from a
constraint, so the kind is now declared rather than inferred, and features sort
last under their own note.

**And the plot size was missing from all twenty reports** — see Lesson 49,
which is about how I nearly explained that wrongly.

### LESSON 45: THE CAP HAD TO SURVIVE THE SKIM

TEST-KANO-01 printed, across the top of its report:

> **89 / 100 — Good**   best suited to agricultural use

on a plot the model had **capped at 35 for residential** because a large part of
it sits in the highest flood categories. Everything needed to see that was on
the page. The flood question said "Yes, it floods". The note said the overall
figure is the best of the four. Lesson 42 had already established that a cap is
a different KIND of statement from a low score.

None of it helps. **The overwhelming majority of people opening a report on a
plot intend to build on it**, they read the big number first, and "89 / 100 —
Good" is what they carry away from a page whose own model says do not build
here. A distinction that exists only in the database is not a distinction the
product has.

Capped uses are now named beside the headline. The cap's own reason string is
NOT reproduced — those are written for the breakdown and read like model
internals — because the four questions below already say why in plain words.

**And the first version of that fix was itself wrong**, which is the more
useful half. It picked the capped use with the LOWEST score. On Kano three uses
were capped, so it printed:

> We do not recommend this plot for **holding as an investment** — it scores 32
> out of 100 for that.

True, and useless. Kano floods. The sentence a buyer needed was about BUILDING,
and sorting by number buried it behind a market opinion nobody opened the
report for. **"Lowest number" and "worst consequence" are different questions**,
and the paragraph promised the second while the code answered the first.
Selection is now by consequence in a fixed order — residential, commercial,
agricultural — and investment never leads it. A weak investment score costs
money slowly; a house on a floodplain is a different category of wrong.

### LESSON 46: ONE MESSAGE OUTWARD, EVERY REASON IN THE LOG

The embed API refused a key that was correct. The response said:

> Unknown, revoked or expired API key.

The key hashed correctly, was not revoked, had not expired, and owned all twenty
parcels. **All three things the message named were false.** The company behind
it had `is_active = false`, and four separate conditions had been folded into
one `WHERE` clause, so a failure of any of them produced a message naming the
other three. Finding out which took a seven-column diagnostic query.

The response is right to be vague. Telling an unauthenticated caller "that key
is real but the account is suspended" confirms which keys exist — a probing
oracle. **The LOG has no reason to be vague, and that is the whole fix.** The
checks are made separately and named, the `HTTPException` body is byte-identical
in every case, and the reason prints to the server window. A client's developer
on the phone would otherwise spend an afternoon regenerating a key that was
never the problem.

> Hide the difference from the caller. Never hide it from yourself.

### LESSON 47: THE BUYER PAGE TOOK THREE PASSES, AND THE CLIENT WAS RIGHT TWICE

Session 10 had already rejected one mockup as too technical. This session the
same thing happened twice more, and both corrections were the client's.

The first pass built an honest analysis page with a **What we do not check**
section — title, zoning, electricity, valuation — six items with who to ask for
each. It is the most defensible page in the build. Njeri's response:

> all this details cannot go to the client side... that should be in our later
> stage after getting clients

**She is right, and the distinction is a product one, not a moral one.** The
limits are a SALES asset in the conversation with the seller, where they prove
we know what we do not know. On a listing page in front of a buyer they are a
wall of disclaimers between that person and the plot. Same content, opposite
effect, decided entirely by who is reading. The limits now live in the seller
pitch and the PDF; the listing page carries one sentence.

Her spec for what a buyer actually wants, verbatim: satellite image and street
view, directions, soil type, rainfall in simple terms not figures, distances to
amenities, famous landmarks nearby, **and the status of surrounding plots**.

Three findings came out of building it:

**The satellite image was never actually blocked.** B4 kept imagery out of the
PDF because Google's terms are strict about tiles inside a document we sell. A
web page is a different licence — the Maps JavaScript API and Street View
embeds are exactly that product. And drawing the plot boundary over the tile is
clean, because that boundary is **the seller's own survey data**, not ours and
not OSM's. It conveys nothing. B4 was read as "no imagery" when what it decided
was "no imagery in the PDF".

**The availability panel is the strongest sales feature on the page and we
cannot fill it.** All eight OAK GROVE plots read `listing_status = 'available'`
and every `price_kes` is NULL. "3 of 7 sold" was my placeholder and the data
says otherwise. This is not a code gap — it is a **second onboarding handshake**,
and unlike the `parcel_ref` mapping it has to keep happening after go-live.
Logged as D24.

**Four columns of imagined precision came off the page.** No invented price, no
fabricated sold/deposit statuses, and `dist_airport_m` removed entirely — see
below.

### LESSON 48: THE QUERY WAS RIGHT AND THE ANSWER WAS STILL WRONG

**This is the session's lesson.** Four defects, four different layers, one
shape. In every case the SQL was correct, the join was correct, the distance was
correct to the metre — and the answer was wrong, because the column was
answering the question NEXT TO the one a buyer was asking.

**1. `Shekiko Airport (disused)`.** TEST-TANADELTA-01's nearest airport, 7.5 km,
correctly measured. A disused airstrip is not somewhere anyone can fly into, and
a listing page offering it as "your nearest airport" is a false promise made in
the source's own words. Geometry cannot tell a live facility from a dead one.
**OSM said so in the NAME**, so a name filter can find it — deliberately narrow,
matching those words in parentheses or as whole words, so a genuine "Former
Presidents Road" survives. Tana Delta moved to Witu Airstrip at 19.9 km: 12 km
worse, and true.

**2. `GSU Airstrip`, on all eight OAK GROVE plots, 6.9 km.** Fully operational.
A General Service Unit airstrip no land buyer will ever fly from. **Nothing in
the name, the geometry or the tags says so** — a filter could never find this
one, because the defect is not in the data at all. It is in the question:
*nearest airport* and *where would I fly from* are the same question only where
every airport takes passengers.

The repair was NOT to exclude airstrips. `domestic` is inferred by name — an
airport is `international` if it says so and `domestic` otherwise — so
`domestic` is a DEFAULT, not a finding, and it is full of bush strips
indistinguishable from GSU. Filtering on it would trade a visibly wrong answer
for an invisibly wrong one. `international` is the one class we verify: four
facilities, each named so by its operator. That got its own column pair, and it
is what buyers see. `dist_airport_m` is unchanged and must be labelled
**airstrip** on any page — the difference is the entire point.

**3. A village is not a town centre.** `admin.places` holds 9,323 rows and 8,679
are villages. Measuring `dist_town_centre_m` to the nearest place of any kind
would put almost every parcel in Kenya a few hundred metres from a "town
centre" — the column would measure **OSM's tagging density, not a buyer's
access to a town**. Restricted to city / town / national_capital: 436 rows. The
same trap as C8, where health facilities stack on ward centroids.

**4. A named major road must be FURTHER than the paved road.** `dist_paved_road_m`
takes the nearest good-class road whether or not anyone named it;
`dist_major_road_m` requires a name, because a buyer cannot orient by an
unnamed trunk road. It is a strict subset, so it can only ever be larger. That
is now a verifier invariant — and the only assertion in the file that needs no
knowledge of Kenya at all, which is exactly why it is worth having.

> A filter can catch a fact the source admits about itself.
> It cannot catch a question that was subtly wrong.
> Only reading the answers out loud catches that.

Logged as D23 and E14. It is the direct descendant of D20 — that rule says never
display a field we do not source; this one says **a field we DO source can still
be the wrong answer**, and no amount of verification will say so.

### LESSON 49: I WROTE THE CAUSE BEFORE I CHECKED IT

All twenty PDFs printed no acreage. Not a wrong figure — the line was simply
absent, because the subtitle renders `size · project` and collapsed silently
when size came back None.

My explanation was that `SELECT p.area_sqm, ... i.*` names a column and then
splats a table holding one of the same name; a result row is keyed BY NAME, so
the duplicate collapses and the last one wins. It is a real bug shape. It
matched the symptom exactly. It is the third cousin of the `admin_name` join
that fanned out threefold and the raster catalogue serving whichever
`nightlights` row came back first. **I wrote the comment before I checked.**

It is not what happened. `analytics.parcel_intelligence` has 86 columns and
`area_sqm` is not one of them; the only name it shares with `land.parcels` is
`parcel_id`. Nothing was shadowed. **`land.parcels.area_sqm` is simply NULL** —
nullable, unpopulated at load, while `geom` is NOT NULL and had the answer all
along. Size now comes from `ST_Area(geom::geography)`, labelled *(our
measurement)*, with the client's stated figure winning when present.

**Rule E2 does not stop applying because the guess is a good one.** A confident
wrong cause, written into a comment, outlives the bug it misdescribes. The
aliasing went in anyway — for `parcel_id`, which IS shared, and which on a
parcel with no intelligence row would have written a null key into
`reports.reports`. The real bug was sitting one column over from the one I
invented.

### THE LANDMARKS BUILD

Six tables from OSM layers already on disk — nothing downloaded, and no licence
letter needed, because what we publish is a DISTANCE and a NAME.

| Table | Rows | |
|---|---|---|
| `admin.places` | 9,323 | new table; there had never been anywhere to measure "distance to town centre" FROM |
| `transport.airports` | 255 | 4 international, 246 domestic, 5 airstrips |
| `transport.bus_stops` | 1,082 | every transport stop, not just buses — see E15 |
| `transport.railways` | 750 | |
| `social.markets` | 2,205 | confidence 2; county registers are the primary |
| `social.public_services` | 606 | |

**One script, not six**, because all six are the same three steps against the
same file set and six scripts would be six copies of one bug. The SPECS table is
the only thing written six times.

**The preflight is the part worth keeping.** The first run loaded 9,323 places
and then died on row one of the next table: `transport.airports.facility_type`
is CHECK-constrained to international / domestic / airstrip and the spec said
`airport`. I had invented the vocabulary from what OSM calls things instead of
reading the schema that has to accept them — E2 again, on a constraint sitting
in a snapshot I had already opened twice that day. The repair is not to be more
careful. **The script now reads the real constraints out of `pg_constraint` and
runs in two passes** — read and classify everything, validate every produced
value, and only then load. A mismatch names all offenders at once and loads
nothing, instead of leaving the database in a state no single run produced.

Two smaller traps, both worth the words:

**`(n or "")` does nothing here.** A missing name arrives from pandas as `NaN`,
`NaN` is a float, and **floats are truthy** — so `or` never fires and
`NaN.lower()` raises. Coercion is by `isinstance`. The second half of that fix
matters more: the unnamed-row drop now runs BEFORE classification, so the
name-based classifier never sees a missing name rather than being hardened
against one.

**Parsing a CHECK constraint by splitting on commas is silently wrong.**
Elements come back as `'domestic'::text`, so `strip("'")` leaves
`domestic'::text` — the trailing character is `t`, not a quote — and the
validator would then reject every value INCLUDING the correct ones. Quoted
literals are pulled with a regex, tested against both real constraint strings
before shipping.

### STATE AT CLOSE

- **Phases 1–4 complete. Phase 5 built and hardened**, not yet exercised end to
  end against a live client site.
- **43 assertions**, up from 31. Section G is new: five landmark IDENTITIES —
  Karen→Wilson, Ruai→JKIA, Lodwar→Lodwar, Garissa→Garissa, Kericho→Kericho —
  and five invariants. The identities are a different KIND of assertion from
  everything above them: those check a modelled number against a documented
  expectation, these check a name against a fact about Kenya that no model
  produced.
- **The buyer page carries nothing invented.** No price, because there is none.
  Eight plots all available, because that is what the seller's records say.
- **The long pole is still legal**, and it grew by one: **WASREB Majidata** is
  the national georeferenced water and sewer network system under Water Act 2016
  s.111 — exactly `dist_water_line_m` and `dist_sewer_m`. Buried mains mean OSM
  has nothing, so it is a letter or it is nothing. Logged as B7 and bundled with
  the KWS batch.

**Newly open:** B7, D23, D24, E14, E15.

**Still the cheapest high-value move on the board:** the KWS letter. It closes
A1 and fixes the coarse-boundary risk that has Kakamega blocked, and it has been
the answer to this question for four sessions.

---

## Session 11b — THE PRODUCT MODEL, WRITTEN DOWN AT LAST

This entry exists because a check of the repository found something worse
than a bug. **The two-phase business model was not recorded anywhere.**
Eleven sessions, 30 ETL pipelines, 114 assertions, five drafted letters — and
the single decision that determines what every one of them is FOR lived only
in conversation. The only trace of it in the whole build was one column,
`clients.companies.marketplace_opt_in`, added in session 1 and never
explained.

It surfaced the way undocumented decisions always do: I built the wrong thing
confidently. The embed widget was rendering the buyer's REPORT — the four
questions, the flood warning, the "before you pay" checklist — onto a
SELLER'S website, and it took Njeri saying so to catch it.

### THE TWO PRODUCTS

**PHASE 1 — SELL ENRICHMENT OF THE SELLER'S OWN PARCELS.** This is what we
sell now. The customer is a land-selling company. The widget goes on THEIR
website, describing land THEY own, to a buyer THEY are courting. It presents
what the land IS: size, soil, rainfall, access, amenities, landmarks, network,
and which other plots in the scheme are still open.

**PHASE 2 — THE GEOCODE MARKETPLACE**, once there are clients. We own the
page. The BUYER is the reader. This is where the unbiased half lives: the
suitability verdict, the flood warning, the protected-area refusal, the
recommendation, the "before you pay" checklist. `marketplace_opt_in` is the
flag a client sets to appear there.

### WHY THE JUDGEMENTS DO NOT GO ON THE SELLER'S PAGE

Njeri's reason, in her words: *a seller will always want the best for
themselves.* That is not a criticism — **it is what a seller is for**. Asking
their website to host an argument against their own sale is asking for
something no client will keep.

There is a second reason, and it is the one that protects the product rather
than the relationship. **A client who can see the analysis on their own page
will ask us to soften it.** Not maliciously; they will have a plot with a
`very_high` flood class and a buyer on the phone. And the moment we soften it
once, the analysis is worth nothing ANYWHERE — including on the marketplace,
where it is the entire product. The split is not diplomacy. It is the only
arrangement in which the verdict stays worth having.

    Facts go where the seller is the customer.
    Judgements go where we own the page and the buyer is the reader.
    Nothing is falsified in either place: a fact is simply not a verdict.

### WHAT CHANGED IN THE CODE

`report_content.build_listing()` is the Phase 1 view, beside `build_report()`
which stays the Phase 2 / PDF view. Both read the SAME enrichment row, in the
same module, for the reason that module exists: the day the widget and the
report disagree about a flood class, a client stops trusting both.

They are two functions and not one function with a flag, deliberately. A
boolean invites one view to drift into the other.

**THE PLOT SIZE IS THE SELLER'S FIGURE.** Not `ST_Area` of the boundary. They
surveyed it, they are selling it, they are the customer, and quietly replacing
their acreage with our measurement of their own plot is a survey finding
delivered as a typo. If they supplied no size, the field is simply absent. The
geometry-derived figure stays in the PDF, where the reader is the buyer and an
independent measurement is exactly the point.

**A BLOCKED PARCEL LOSES ITS SCORE AND GAINS NOTHING ELSE.** No red panel, no
stated reason, no "Not rated" badge a buyer would read as a warning. The
absence is the whole treatment. Why a plot cannot be scored is a conversation
for us and the seller, not something to print on their listing in front of
their buyer.

### THE ONE RULE THAT DOES NOT MOVE

**We do not print a claim we cannot source.** No title status, no zoning, no
electricity connection, no per-operator coverage. On a SELLER'S page this
matters MORE, not less: a "Title Verified" badge on the page of the person
selling the land is the most dangerous thing this product could render, and it
is dangerous *precisely because it benefits them*. D20 and D23 apply on both
pages without exception, and B5 stays open until Njeri decides it.

### ALSO THIS SESSION

**`v1.js` exists.** The whole architecture had always been "two lines in the
client's page", and the second line pointed at a file that had never been
written. With it: a `/v1.js` route, and CORS — without which the browser
blocks every response and the widget renders nothing on a real client domain.
Proven end to end against a deliberately ugly stand-in page built with none of
our styles, because a widget that only looks right on a page we designed is a
demo, not an embed.

**LESSON 50: `False`, `NULL` AND `NOT FOUND` ARE THREE ANSWERS, AND I SHIPPED
TWO BUGS TREATING THEM AS TWO.**

Deferring A1 meant WDPA — non-commercial — could no longer answer
`in_protected_area`. Switching to commercially usable sources broke the
product twice in one hour, in opposite directions:

1. The OSM protected-areas layer covers little of Kenya, so the query returned
   nothing for Aberdares, Kakamega and Tana Delta — and the code read *nothing
   found* as **not in a park**. Three national parks became saleable land.
   `False` is exactly the value that lets a parcel be scored, priced and
   listed.

2. The repair checked "did WDPA return a row" instead of "does WDPA say
   INSIDE". The search radius is tens of kilometres and there is a park within
   that of most of Nairobi, so **nineteen of twenty parcels blocked**,
   including Karen and every OAK GROVE plot. The product was dead.

Both failures are the same failure. The question has three answers — inside /
not inside / cannot tell — and I twice wrote code that could only express two,
reading "did the query return a row" as though it meant "is the parcel
inside". The state machine is now written out explicitly rather than inferred:

    commercial source answered          -> use it, note if WDPA disagrees
    silent, and WDPA says INSIDE        -> UNRESOLVED (NULL), block the score
    silent, and WDPA says near or none  -> False, and that IS an answer

And `blocking()` now fails CLOSED: anything other than a confident `False`
stops the score, because `if r.get("in_protected_area")` treats `None` and
`False` identically — correct Python, wrong product.

**The price of deferring A1, stated plainly:** `dist_protected_area_m` is now
NULL on most parcels, because that number came from data we cannot publish.
The boolean still answers, scoring is unaffected, and it returns the day KWS
lands. Three parcels remain unsellable until then — and that is the real
argument for the KWS letter. A1 is not licence housekeeping; it is the
difference between refusing to rate land and rating it.

### STATE AT CLOSE

- **43 enrichment assertions + 71 scoring checks, 0 failed.** Four parcels
  correctly blocked: three protected-area-unresolved, one boundary.
- **The widget works on a third-party page.** Phase 1 is renderable end to end.
- **Still not built:** a server (it runs on one laptop), rate limiting,
  billing, upload rejection gates, the Google Maps key for satellite and
  Street View.
- **A1 downgraded** to a later improvement by Njeri's decision, with the
  consequences above made safe rather than ignored. **A2 (CA) reported as
  cleared** — get the written confirmation on file, per the standing rule that
  a verbal go-ahead is not an answer to an acquirer. **A5 (Kenya Power)
  awaiting data.**
