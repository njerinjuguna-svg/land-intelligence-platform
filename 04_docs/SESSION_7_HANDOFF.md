# Session 7 Handoff — Land Intelligence Platform (Kenya)

**Date: 2026-08-18. Paste this into the new session.**

---

## 0. HOW TO USE THIS DOCUMENT

**The session 6 handoff was written from memory and was wrong.** It claimed
PROGRESS.md was missing nightlights, the trend calibration, schema v1.5 and
flood runs 75/77. All were already there in full. Acting on that cost the
first hour of session 7.

**So this is a map, not a source.** Open the file before acting on any claim
in it. Authoritative, in order:

1. `04_docs/PROGRESS.md` — the build log, ~2,400 lines, sessions 1–7
2. `04_docs/PRE_LAUNCH_CHECKLIST.md` — what blocks selling (A/B/C/D/E sections)
3. `01_database/_live_schema_snapshot.sql` — what the database actually is
4. `02_data_catalogue/datasets.csv` — the dataset list and priorities

### HOW TO WORK IN THIS PROJECT — read before touching anything

**The first agent to read the previous version of this handoff treated the
"next steps" list as a work order and edited 18 files unprompted.** The content
turned out to be accurate, but nobody could check anything in between. That was
the document's fault. Correcting it here:

- **Section 6 is a MENU. Nothing in it is authorised.** Propose, then wait.
- **One item at a time.** Make it, run it, check it, then start the next. Three
  of session 7's bugs were caught only because changes were small enough to
  attribute.
- **`PROGRESS.md` and `PRE_LAUNCH_CHECKLIST.md` are the durable record.** Do
  not append without asking. They are what Njeri hands to a lawyer, a client or
  an acquirer.
- **`enrich_01_engine.py` is VERIFIED.** Do not rewrite it wholesale. Extend it
  one layer at a time and re-run the verifier after each.
- **Njeri runs the commands.** Show the change, explain it, hand over the
  command. There is no database access from the agent side.

---

## 1. WHAT THIS PROJECT IS

A national land intelligence database for Kenya. A land-selling company uploads
parcels; the platform assesses each against physical and regulatory factors and
produces a written assessment for the buyer.

**Four buyer questions** drive the whole catalogue: *Can I build here? Can I
farm here? Is the land safe? Is the area developing?* — plus *what surrounds
the parcel, how accessible is it, are schools/hospitals/water/internet nearby.*

**Delivery format, decided session 7:** the PDF report is **analysis only, no
images**. Imagery lives on the seller's platform, where a buyer wants
directions or Street View. This decision removes every imagery licensing
question from the deliverable.

### Folder layout

```
01_database/      schema + migrations + the live snapshot
02_data_catalogue/ sources.csv, datasets.csv (48 sources, 74 datasets)
03_etl/           etl_01..etl_29, verify_*, calibrate_*, patch_*, venv
04_docs/          PROGRESS, CHECKLIST, memo, correspondence, handoffs
05_enrichment/    the engine, test parcels, loader, verifier   <- NEW s7
06_rasters/cog/   the raster store (pointers in metadata.raster_catalog)
```

**Architecture rule:** rasters NEVER go into PostGIS. They live as COGs on
disk; `metadata.raster_catalog` holds a pointer, checksum, confidence and
status. **The file is the data; the catalogue row is the truth about it.** This
is why moving to cloud storage later is "copy the files, update one column".

---

## 2. STATE OF THE DATABASE — P1 25 of 27

### Built and loaded (vector, in PostGIS)

| Layer | Count | Source | Conf |
|---|---|---|---|
| `admin.country` | 1 | dissolved counties | 4 |
| `admin.counties` | 47 | HDX COD-AB | 4 |
| `admin.subcounties` | 290 | HDX | 4 |
| `admin.wards` | **1,425 of 1,450** | Kenya wards shapefile | 3 |
| `transport.roads` | 730,006 | OSM/Geofabrik | 3–4 |
| `environment.rivers` | 46,529 | OSM | 3 |
| `environment.waterbodies` | 14,945 | OSM | 3 |
| `environment.riparian_buffers` | 41,862 | **ours, derived** | 3 |
| `environment.protected_areas` | 349 | WDPA | 4 |
| `utilities.water_points` | 21,953 | WPDx | 3 |
| `social.education` | 37,930 | MoE/World Bank | 4 |
| `social.health` | 12,403 | KMHFL | **2 — ward centroid** |
| `connectivity.towers` | 142,279 | OpenCellID | 2 |
| `connectivity.coverage` | 37,122 | CA geoportal | 2–3 |
| `demographics.population_stats` | 47 + 1,425 | WorldPop zonal | 3 |
| `demographics.nightlights_stats` | 7,345 | NASA Black Marble zonal | 4 |

### Built and catalogued (raster — 21 active rows)

`elevation`, `slope`, `twi`, `ph`, `texture_class`, `soil_type`, `rainfall`,
`rainfall_recent_mean`, `rainfall_anomaly_pct`, `rainfall_driest_year_pct`,
`rainfall_max5day_mean`, `rainfall_max5day_p90`, `ndvi`, `landcover`,
`landcover_io_2017`, `landcover_io_2023`, `landcover_io_2024`, `builtup`,
`population`, `nightlights`, `flood_hazard`

Plus `landcover_change` at **`pending_review`** — quarantined, see §4.

### The two missing P1 datasets — neither is a build task

| Dataset | Blocker |
|---|---|
| `utilities.power_distribution` | Kenya Power derived-use licence. Letter drafted, not sent. |
| `land.parcels` | Client data, arrives at onboarding. Not ours to fetch. |

**There is no ETL left to write.**

---

## 3. STATE OF THE ENRICHMENT ENGINE — Phase 3, roughly a third built

`05_enrichment/enrich_01_engine.py`, version `0.1.0-slice`.

**Verified:** 22 assertions passed, 0 failed, 1 known gap, on 20 parcels — 12
synthetic landmarks and 8 real client plots. **NOTE: that count predates two
verification fixes and has not been re-confirmed. Re-run before quoting it.**

### What it fills today (~24 columns)

- **Roads** — `dist_any_road_m`, `dist_paved_road_m` (PostGIS geography)
- **Flood** — `flood_risk_class`, `flood_risk_class_cell`,
  `flood_risk_breakdown`, `flood_search_radius_m`, `flood_nearby_pct`,
  `dist_permanent_water_m`, `flood_forcing_max5day_mm`
- **Soils** — `soil_type`, `soil_ph`, `soil_texture`, `soil_composition`,
  `black_cotton_risk`
- **Terrain** — `slope_mean_pct`
- **Rainfall** — normal, min, max, recent, anomaly, driest-year, max5day mean
  and p90
- **Provenance** — `field_confidence`, `field_sources` (jsonb, per field)

### Design decisions that must survive

- **Footprint, never centroid.** Every layer is clipped to the polygon. A
  50-acre plot does not have *an* elevation.
- **The catalogue is the truth about a file.** Rasters are looked up by
  `variable` with `status = 'active'` — which is why `landcover_change` is
  excluded automatically, with no special case in the engine.
- **Compositions carry `n_pixels`.** Karen is nine pixels at 30 m; a percentage
  without its sample size invites false confidence.
- **Supersede, never delete.** Re-running marks the old row `superseded` and
  writes a new version.
- **`except BaseException`** in the run handler.

### What is left to add — and everything here has its data already built

| Column(s) | Source | Notes |
|---|---|---|
| `elevation_mean_m`, `elevation_min_m`, `elevation_max_m` | `elevation` raster | The range IS the buildability signal |
| `twi_mean` | `twi` raster | |
| `ndvi_mean`, `ndvi_year` | `ndvi` raster | C6: single year 2024, not a normal |
| `landcover_class_worldcover`, `landcover_composition` | `landcover` | D6 applies |
| `landcover_class_io`, `landcover_io_year` | `landcover_io_2024` | Never compare class-by-class with WorldCover |
| `built_up_pct_1km` | `builtup` | **D8: full cell = 8,606 m², cap at 1.0** |
| `pop_density_km2` | `population` | **D9: set `pop_is_census_calibrated = false`** |
| `nightlights_trend_radiance_yr`, `_radiance_mean`, `_admin_unit` | `demographics.nightlights_stats` (**vector zonal, not raster**) | D10, D11 |
| `coverage_2g_pct`, `coverage_4g_pct`, per-operator, `coverage_admin_*`, `coverage_vintage` | `connectivity.coverage` (vector) | **D4, D5, D12** |
| `dist_tower_m` | `connectivity.towers` | The point-level half of D4 |
| `in_riparian_buffer` | `environment.riparian_buffers` | High product value |
| `in_protected_area`, `dist_protected_area_m` | `environment.protected_areas` | **A1: WDPA is non-commercial** |
| `dist_river_m` | `environment.rivers` | ODbL — keep swappable |
| `dist_primary_school_m`, `dist_secondary_school_m` | `social.education` | |
| `dist_hospital_m`, `dist_clinic_m` | `social.health` | **C8: ward centroid, not GPS** |
| `dist_water_point_m` | `utilities.water_points` | |

**Awaiting data — leave NULL, already documented in the column comments:**
`dist_power_line_m`, `dist_transformer_m`, `dist_sewer_m`, `dist_water_line_m`,
`zoning_class`, `landslide_risk_class`, `in_wetland`, `aspect_dominant`,
`soil_drainage`, `soil_depth_class`, `soil_fertility`, `temp_mean_c`,
`solar_kwh_m2_day`, `dist_bus_stop_m`, `dist_market_m`, `dist_police_m`,
`dist_fiber_m`, `dist_town_centre_m`, `travel_time_town_min`

### Three known code defects — all minor, none blocking

1. `NEARBY_MIN_PCT` and `FLAT_SLOPE_DEG` are **dead constants** carrying long
   comments describing controls that no longer run. Fossils of two abandoned
   approaches. Delete or wire in. (Checklist E13.)
2. The comment in `layer_flood` reasons against **6.93%** (Very high alone)
   while the constant beside it is **12.5%** (High + Very high, which is what
   `flood_nearby_pct` measures). The code is right; the comment's arithmetic is
   against the wrong denominator.
3. **`cat['nightlights']` is ambiguous.** `etl_26` writes one catalogue row per
   year, and `load_catalogue` keeps the highest `raster_id` — so it silently
   means "whichever year was catalogued last". Harmless today because
   nightlights is not in the slice; **must be fixed before adding it.** Same
   latent issue applies to `landcover_io_*`.

---

## 4. BROKEN, PAUSED, OR NOT SHIPPABLE

| Item | State and why |
|---|---|
| `landcover_change` | **Quarantined at `pending_review` by etl_29 itself.** IO is not temporally consistent — the class shifts arrive as steps at single year boundaries while Water stays stable against WorldCover. Yearly snapshots ship; the change layer does not. |
| Black cotton at Athi-Kapiti | **C16, blocking.** Cannot be determined from SoilGrids + iSDA + slope. `none` there must be reported as **INCONCLUSIVE**, never "safe". |
| Channel cells in the flood top class | **C10.** Over half of Very high is the watercourse itself. The layer over-warns, so not urgent. Fix is `MULT` boundaries or a channel class — both re-class the country. |
| Closed basins / Chalbi | **C14, accepted.** Non-binding in the calibrator under the scope rule. |
| PLOT-950 | Self-intersecting as supplied; repair changed area 2.10 → **8.50 acres** and moved the polygon onto ground that is not the plot. Loaded at confidence 3 with a do-not-quote note. Needs the mutation drawing. |
| PLOT-1069 / PLOT-1070 | **`ST_Equals` — two plot numbers, one polygon.** Either a drafting duplicate or the same ground allocated twice. |
| `THIKA ALL.csv` | **Deliberately not loaded.** 1,715 beacons with no topology; a1/a6/a5 are collinear, so consecutive points are boundary runs not plot corners. Needs a DXF, shapefile or mutation drawing. |
| `trend_pct_yr` | Deliberately NULL. Do not repopulate. |
| `DATA_INVENTORY.md` | Marked superseded. Rewrite when enrichment settles. |

---

## 5. WHAT REMAINS TO A SELLABLE PRODUCT

### Phase 3 — enrichment engine *(started, ~1/3)*
Add the layers in §3. Mechanical: a `sample_*` function, a line in the call
list, an assertion in the verifier. **One at a time, verify after each.**

### Phase 4 — suitability scoring *(not started)*
`analytics.suitability_scores` exists in the schema: residential,
agricultural, commercial, investment, overall, plus `score_breakdown` jsonb.
**The breakdown is the product** — a score without its components is a number
nobody can argue with, which in this market is a liability.

### Phase 5 — delivery *(not started)*
REST API, PDF reports (`reports.reports` table exists), admin portal, buyer
dashboard. Architectural rule already set: **ship values and pictures, never
geometry**; render overlays server-side; deep-link to Google Maps for
directions and Street View.

### Phase 6 — legal clearances *(1 of 6 letters sent)*

| # | To | Unblocks | Status |
|---|---|---|---|
| 1 | Communications Authority | **A2** + B1 + possibly A3 | **SENT 2026-08-18.** Phoned first, told verbally no licence needed. **A2 stays open until written confirmation.** |
| 2 | WRA | B2 + the ODbL exit + `river_class` | **Njeri attending in person. Take the printed letter.** |
| 3 | Kenya Power | A5 + a missing P1 | Drafted |
| 4 | KNBS | C3 population | Drafted |
| 5 | IEBC | C4 ward codes | Drafted |
| 6 | KWS | **A1**, replaces non-commercial WDPA | Drafted |
| — | Kenyan IP lawyer | A3, A4 share-alike | Brief complete in `LICENSING_OPTIONS_MEMO.md` §7 |
| — | Unwired Labs | A3 | Commercial enquiry — **you CAN pay your way out of OpenCellID**, unlike OSM |

### Phase 7 — hosting *(decided in principle, not executed)*
Cloudflare R2 or S3 af-south-1 for rasters (~10–15 GB); DigitalOcean/Supabase
or RDS af-south-1 for Postgres. **Do not migrate until the full
`_live_schema_snapshot.sql` has been diffed against the versioned files** —
session 7 only checked the three tables the trail led to.

### Accuracy debt — `PRE_LAUNCH_CHECKLIST.md` §C, 17 items
Blocking before selling: **C3** (population +16% nationally, +209% Mandera),
**C4** (all 1,425 wards on provisional `LIP-W` codes), **C16** (black cotton).
The rest are documented limitations with stated handling.

---

## 6. CANDIDATE NEXT STEPS — a menu, nothing here is authorised

*(Ordered by dependency, not priority. Propose one; wait.)*

1. **Re-run `verify_01_enrichment.py`.** Two fixes landed after the last run:
   neighbour-divergence now requires spatial contiguity (it falsely flagged
   TEST-ABERDARES-01, whose "project" is landmarks scattered across Kenya), and
   adjacent boundaries no longer report as overlaps.
2. **Extend the engine, one layer at a time.** Suggested order by product
   value: NDVI → land cover → built-up → riparian buffer → population →
   nightlights → coverage + towers → protected areas → amenity distances.
   **Fix defect 3 in §3 before nightlights or IO land cover.**
3. Clear the three code defects in §3 (20 minutes, cosmetic).
4. Suitability scoring, once enough layers are in.
5. Send the remaining letters; chase the CA reply; send the lawyer brief.
6. Diff the full schema snapshot before any cloud work.

---

## 7. RULES THAT MUST SURVIVE

**Query it, don't recall it.** Six values were asserted from memory in session
6 and every one was wrong. The session 6 handoff itself was wrong. This is the
most-broken rule in the project.

**A control that lives beside the code is not a control.** Four separate
session-7 bugs were this shape: rule E1 written down then broken twice more; a
quarantine applied by SQL and undone by the next pipeline run; a failure logger
that never fired for the guards that stop these scripts; a schema whose real
source of truth was the running database while the files rotted.

> A rule you have to remember is a reminder.
> A rule the code cannot proceed without is a control.

**Before believing a failure, check the test.** Three of session 7's bugs were
in the verification, not the thing verified.

**If you have changed the same constant twice, stop.** Sweep it. If no value
satisfies the constraints, the model is wrong, not the constant. Applied to
rule D7 after three formulations.

**Clip to the country before quoting any national statistic.** Five
occurrences. Every raster script now prints both denominators and refuses to
run on a bad mask.

**The scope rule (Njeri, session 7):** this is a product for land people **buy
and sell**. Chalbi, closed basins and deep ASAL rangeland are not worth
contorting the model for. An item is only blocking if it can produce a wrong
answer on a parcel a client would actually transact.

**Snapshot the schema after any change** and diff it. `pg_dump --schema-only`.
Ten seconds, and the only thing that would have caught the lost v1.1 migration.
