# LAND INTELLIGENCE PLATFORM — DATA INVENTORY
### What is in the database, where it came from, and why we have it

> # ⚠️ SUPERSEDED — DO NOT USE AS A STATUS REPORT
>
> **Last updated: end of Session 4. It is now session 7 and this file is three
> sessions stale.** It is kept because sections 0 (how the database is
> physically organised), 2.1–2.4 (why each early layer exists) and 4 (the
> streaming problem) are still the clearest explanations we have written of
> those topics. **Everything it says about STATUS is wrong.**
>
> Known-false statements in the text below:
>
> - `soils.ph` "needs rerun" — **fixed in session 5, runs 46/47.**
> - `climate.rainfall` "not built yet" / "script ready" — **built in session 5
>   (run 48), and extended in session 6 with recent, anomaly, driest-year and
>   max-5-day layers.**
> - "Still missing: rainfall, soil taxonomy, vegetation/NDVI, land cover,
>   built-up, population" — **all six are built.**
> - "P1: 23 of 27" and the 5–8 session estimate — **P1 is 25 of 27**, and the
>   two remaining are not build tasks: `utilities.power_distribution` waits on
>   a Kenya Power derived-use licence, `land.parcels` arrives with the client.
> - The licensing summary omits everything cleared or opened since session 4.
>
> **For current status use, in this order:**
> `PROGRESS.md` (the build log, authoritative) → `PRE_LAUNCH_CHECKLIST.md`
> (what blocks selling) → `02_data_catalogue/datasets.csv` (the dataset list).
>
> Rewrite this file only when the enrichment engine settles, since that is
> what a client-facing inventory should describe. Until then a clearly
> labelled stale document is safer than a hastily refreshed one.

---

## 0. HOW THE DATABASE IS PHYSICALLY ORGANISED

Your "database" is actually **two things working together**:

**(A) PostgreSQL + PostGIS** (`land_intelligence_kenya`) holds all the **vector**
data: points, lines and polygons. Roads, schools, rivers, boundaries. These are
rows in tables you can query with SQL.

**(B) Files on disk** (`06_rasters/cog/...`) hold all the **raster** data: grids
of pixels. Elevation, slope, soil, rainfall. These are NEVER put inside
PostgreSQL, because a national grid is gigabytes and would cripple the database.

**What connects them:** the table `metadata.raster_catalog`. For every raster
file there is one row saying: what it is, what units, where the file lives
(`storage_url`), its footprint, its checksum, its source, and its confidence.

> **The rule:** the file is the data, the catalogue row is the truth about it.
> Never use a raster that is not catalogued, never catalogue a file that is not
> there. Because the catalogue only stores a *pointer*, moving all rasters to
> cloud storage later is a copy-the-files-and-update-one-column job.

Everything, vector or raster, carries the same provenance columns: `source_id`,
`source_date`, `confidence` (1-5), `version`, `status`. That is what lets the
product honestly say "we know this, and here is how well we know it".

---

## 1. WHAT IS IN THE DATABASE RIGHT NOW

### 1A. VECTOR LAYERS (in PostGIS) — all complete, all national

| Layer | What it is | Count | Source | Confidence |
|---|---|---|---|---|
| `admin.counties` | 47 counties | 47 | HDX COD-AB | 4 |
| `admin.subcounties` | Sub-counties | 290 | HDX COD-AB | 4 |
| `admin.wards` | Wards | 1,425 of 1,450 | Kenya wards shapefile | 3 (incomplete) |
| `admin.country` | National outline | 1 | Derived (dissolved counties) | 4 |
| `transport.roads` | Road network | 730,006 | OSM / Geofabrik | 3-4 |
| `environment.rivers` | Rivers and streams | 46,529 | OSM / Geofabrik | 3 |
| `environment.waterbodies` | Lakes and ponds | 14,945 | OSM / Geofabrik | 3 |
| `environment.protected_areas` | Parks, reserves | 349 | WDPA (UNEP-WCMC) | 4 |
| `environment.riparian_buffers` | Legal river setbacks | 41,862 | **Ours (derived)** | 3 |
| `utilities.water_points` | Boreholes, kiosks, springs | 21,953 | WPDx | 3 |
| `social.health` | Health facilities | 12,403 | KMHFL (openAFRICA) | 2 (ward centroid) |
| `social.education` | Schools | 37,930 | MoE via World Bank/KODI | 4 |
| `connectivity.towers` | Cell towers | 142,279 | OpenCellID | 2 (crowdsourced) |

### 1B. RASTER LAYERS (files + catalogue rows)

| Layer | File | Size | Resolution | Source | Status |
|---|---|---|---|---|---|
| `terrain.dem` | `terrain_dem_copernicus_glo30_2021.tif` | 3,507 MB | 30 m | Copernicus GLO-30 | DONE |
| `terrain.slope` | `terrain_slope_derived_glo30_2021.tif` | 1,984 MB | 30 m | **Ours (from DEM)** | DONE |
| `terrain.twi` | `terrain_twi_derived_glo30_90m.tif` | 254 MB | 90 m | **Ours (from DEM)** | DONE |
| `soils.texture` | `soils_texture_class_isda_30m.tif` | 114 MB | 30 m | iSDAsoil | DONE |
| `soils.ph` | `soils_ph_isda_30m.tif` | 487 MB | 30 m | iSDAsoil | **needs rerun** |
| `climate.rainfall` | (not built yet) | — | 5 km | CHIRPS | script ready |

---

## 2. WHAT WE BUILT THIS SESSION, AND WHY

### 2.1 Riparian buffers (`etl_12`) — 41,862 polygons

**What:** a polygon along every river and stream marking the legally protected
strip of land beside it.

**Why:** in Kenya the land next to a watercourse is a *riparian reserve*. It is
public land. You cannot build a permanent structure, cultivate it, or fence it.
So if a parcel overlaps one, part of what the buyer is paying for is legally
unbuildable. That is exactly the kind of thing a buyer is never told and would
badly want to know. It is also a differentiator: nobody else in the Kenyan land
market surfaces this automatically.

**Where the data came from:** nowhere. This layer is **derived** — we grew a band
around the rivers already in our database (which came from OpenStreetMap via
Geofabrik). No download at all. This is the first layer that is genuinely *our
intellectual property* rather than someone else's data reshaped.

**The widths, and their legal basis:**
- river 30 m, stream 6 m, canal 6 m, drains excluded (man-made, not natural)
- Basis: EMCA (Wetlands, Riverbanks, Lakeshores and Seashores) Regulations 2009
  (minimum 6 m, maximum 30 m from the high-water mark); Water (Resources)
  Regulations 2025; Survey Regulations Cap 299.
- We researched this rather than guessing, because a wrong width makes the whole
  layer worthless for a paid product. Every row stores its `legal_basis` text so
  a report can defend the number.

**Honest limitation:** the law measures from each *bank*, but OpenStreetMap only
gives us the river's *centre line* with no channel width. So we buffer from the
centre. For Kenya's mostly narrow rivers this is a sound, slightly conservative
approximation. Confidence 3 records that this is a rules-based estimate, not a
surveyed boundary.

---

### 2.2 The terrain trio (`etl_13`, `etl_14`, `etl_15`, `etl_16`)

This was the biggest new architecture since the schema: our first rasters.

#### Elevation / DEM (`etl_13` download + `etl_14` mosaic)

**What:** a national map where every 30 m square stores the height of the ground
above sea level. 32,400 x 39,600 pixels, about 1.28 billion of them.

**Why:** elevation is the parent of everything terrain. From it you derive
steepness, water flow, wetness, and eventually landslide and flood signals. Also
directly useful: altitude drives temperature and what crops grow.

**Where it came from:** **Copernicus GLO-30**, produced by the European Space
Agency's Copernicus programme. The heights were *measured from space* by the
TanDEM-X radar mission (DLR, Germany, and Airbus). We downloaded it from a free
public Amazon S3 bucket (`copernicus-dem-30m`), which serves the world as 1x1
degree tiles. We read the bucket's own `tileList.txt`, kept only the 96 tiles
overlapping Kenya's outline, and downloaded those.

**Licensing (important, and good):** Copernicus GLO-30 is "Full, Free and Open"
**including commercial use**, attribution only. That is much friendlier than OSM
(share-alike) or WDPA (non-commercial). The required notice is stored on the
catalogue row.

**Honest limitation:** it is a DSM (Digital *Surface* Model), meaning it includes
tree canopy and buildings, not bare earth. Fine for slope and relative wetness.
Confidence 4.

#### Slope (`etl_15`)

**What:** how steep the ground is, in degrees, for every 30 m square.

**Why:** steepness is one of the strongest "can you build here and what will it
cost" signals. Flat land is cheap to develop; steep land means retaining walls,
erosion, access problems. It also feeds the wetness index and the final score.

**Where from:** **derived by us** from the DEM. No download. We use Horn's 3x3
method, the same maths QGIS and ArcGIS use.

**The subtlety we handled:** the DEM is stored in degrees of longitude/latitude
but slope must be computed in metres. A pixel is ~30.9 m tall everywhere, but its
*width* in metres shrinks as you move away from the equator. We compute the true
ground width per row from that row's latitude. Ignoring this would tilt every
slope in the country slightly.

#### TWI / wetness (`etl_16`)

**What:** a Topographic Wetness Index: how prone each spot is to being wet.
High = valley bottoms and flood plains where water collects. Low = ridges that
shed water.

**Why:** an interim flood and waterlogging proxy until proper flood hazard maps
are obtained. Waterlogging matters for both building (foundations, drainage) and
farming.

**Where from:** **derived by us** from the DEM using `pysheds`, which simulates
water flowing downhill: fill tiny pits so water is not trapped, decide which way
is downhill for every cell, then count how much land drains through each cell.
TWI = ln(drainage area / slope).

**Why 90 m and not 30 m:** simulating drainage across 1.28 billion cells is very
heavy. At 90 m it is ~143 million cells: minutes instead of hours. Since the
catalogue itself defines this as a *proxy* until real flood data arrives, that
trade is appropriate. Confidence 3 records it.

---

### 2.3 Soils (`etl_17`)

**What:** two 30 m national layers — soil **pH** (acidity) and soil **texture
class** (clay through sand) for the top 0-20 cm.

**Why:**
- **pH** answers "can I farm here, and what will it cost to correct the soil".
  Acidic highland soils need lime; that is real money.
- **texture** answers a *building* question as much as a farming one. Heavy clay
  is **black cotton soil**: it swells when wet and shrinks when dry, cracking
  foundations and roads. Knowing a plot is on heavy clay changes what it is worth
  and what it costs to build on. This is a genuinely valuable, under-served
  signal in the Kenyan market.

**Where it came from:** **iSDAsoil**, by iSDA Africa — the first continent-scale
30 m soil property map, built with machine learning from over 100,000 analysed
soil samples plus satellite data (Hengl et al. 2021, *Scientific Reports*
11:6130). Hosted as Africa-wide Cloud Optimized GeoTIFFs on a public S3 bucket.

**Clever bit:** we did **not** download the continent. Because the files are
COGs, we opened them over the internet and read only the pixels inside Kenya's
bounding box. (This turned out to be slow on your connection for reasons
explained in section 4.)

**Licensing:** CC-BY-4.0 — commercial use allowed with attribution.

**Texture legend (values in the file):**
1 Clay · 2 Silty Clay · 3 Sandy Clay · 4 Clay Loam · 5 Silty Clay Loam ·
6 Sandy Clay Loam · 7 Loam · 8 Silt Loam · 9 Sandy Loam · 10 Silt ·
11 Loamy Sand · 12 Sand

Kenya's mean came out at 5.82, i.e. sandy-clay-loam / loam territory. Plausible.

**Important limitation to remember:** `soils.soil_type` in the catalogue is
defined as a *WRB taxonomy class*. iSDA does **not** publish taxonomy, only soil
properties. That layer must come from **SoilGrids** (ISRIC, 250 m) instead. We
did not fudge it.

---

### 2.4 Rainfall (`etl_18`) — written, not yet run

**What:** mean annual rainfall in mm/year, averaged over 1991-2020.

**Why 30 years, not last year:** one year tells you that year's *weather*. A
buyer needs the *climate*: what a place normally gets. The world standard is a
30-year "normal" (WMO). Averaging smooths out droughts and El Niño years and
leaves the real signal.

**Where from:** **CHIRPS**, the Climate Hazards Center at UC Santa Barbara.
Satellite rainfall estimates blended with ground rain-gauge station data.
**Public domain**, no restrictions.

**Resolution note:** 5 km is CHIRPS's *native* resolution. There is nothing finer
to get, and your catalogue already specifies 5 km for this layer. So this is not
a shortcut.

---

## 3. WHAT THE DATABASE CAN ANSWER TODAY

For any point or parcel in Kenya, we can now answer:

**Location and administration** — which county, sub-county, ward.

**Access** — how far to the nearest road, and what class of road.

**Services** — how far to the nearest school, health facility, water point.

**Connectivity** — how far to the nearest cell tower, and which operator.

**Terrain** — elevation, steepness, and whether water tends to collect there.

**Soil** — acidity and texture, including heavy-clay (black cotton) risk.

**Legal and environmental constraints** — whether it sits inside a riparian
reserve, or inside/near a protected area.

**Still missing:** rainfall (script ready), soil taxonomy, vegetation/NDVI, land
cover, built-up areas, and population density.

---

## 4. THE ONE UNSOLVED TECHNICAL PROBLEM

Reading iSDA's soil data was painfully slow and kept failing, while downloading
the 96 DEM tiles worked fine on the same connection. That difference is the clue.

**Cause:** iSDA's file is stored in Web Mercator, and we asked for it in
longitude/latitude. Converting *while streaming* forces the software to jump
around the remote file grabbing thousands of small scattered pieces. Each one is
a chance to time out. Whole-file sequential downloads do not have this problem.

**The permanent fix (first task next session):** separate fetching from
reprojecting.
1. Read Kenya's window in the file's *own* coordinate system, no conversion.
   That reads in one continuous sweep, like a normal download.
2. Save it locally.
3. Reproject that small local file on your own disk, with no network involved.

Same final quality, but the network part becomes the kind of work your connection
handles well. This pattern should be applied to every future remote-COG source.

---

## 5. WHAT REMAINS

**Data (P1):** soil taxonomy (SoilGrids), rainfall (run `etl_18`), NDVI, land
cover, built-up, population (WorldPop).

**Then the product logic:**
1. **Enrichment engine** — when a client uploads parcels, sample every layer
   under each parcel and store the results. This is the heart of the product.
2. **Suitability scoring** — combine those factors into a score out of 100.
3. Then: REST API, PDF reports, admin portal, buyer dashboard, first pilot client.

Rough estimate to a functioning intelligence database (data + enrichment +
scoring): **5 to 8 working sessions.**

---

## 6. LICENSING SUMMARY (must be settled before commercial launch)

**Cleared for commercial use:**
- Copernicus GLO-30 — free, commercial OK, attribution required
- iSDAsoil — CC-BY-4.0, commercial OK, attribution required
- CHIRPS — public domain

**Still to resolve:**
- OpenStreetMap (roads, rivers) — ODbL **share-alike**
- OpenCellID (towers) — CC-BY-SA **share-alike**
- WDPA (protected areas) — **non-commercial**; use KWS as the primary source for
  the paid product
- Communications Authority coverage maps; Kenya Power data — need permission

**Attribution strings that must ship with the product:**
- "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus
  Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European
  Union and ESA; all rights reserved."
- "iSDAsoil © iSDA Africa, CC-BY-4.0; Hengl et al. 2021, Sci Rep 11:6130."
- "CHIRPS (Climate Hazards Center, UC Santa Barbara), public domain. Funk et al.
  2015, Sci Data 2:150066."
