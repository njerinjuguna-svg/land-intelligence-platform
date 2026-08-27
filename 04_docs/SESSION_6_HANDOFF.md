# Session 6 Handoff — Land Intelligence Platform

**Date:** 2026-08-12 · **Read this first in the next session.**

Point the next session at this file plus `PROGRESS.md` and
`PRE_LAUNCH_CHECKLIST.md`. This covers what session 6 did, what it found,
what is unfinished, and what to do first.

---

## 1. WHERE THE PROJECT STANDS

**P1 datasets: 25 of 27 complete.** The data phase is effectively closed.

| Remaining | Status |
|---|---|
| `utilities.power_distribution` | Njeri has a contact in Kenya Power's GIS department. **Ask for a DERIVED-USE licence, not the data** — permission to store "nearest MV line: 340 m" without redistributing the network is far easier to approve internally than a data transfer. |
| `land.parcels` | Client data, loaded at onboarding. Not ours to fetch. |

Everything else P1 is built, verified and catalogued.

---

## 2. WHAT SESSION 6 COMPLETED

### hazards.flood — FINAL run 77
Rebuilt from scratch after runs 55–62 failed seven times. Method:
- HAND by **D8 flow routing** (pysheds), not Euclidean nearest-drainage
- Hazard scaled by **catchment size**: `d(A) = 1.5m × (A/1000)^0.3`, top class
  requires outlet catchment ≥ 10 km²
- Channels at 5 km² accumulation; filled (invented) terrain excluded
- **Class 6 = permanent water**, a land-cover fact, NOT a hazard level
- Conditioning cached (`_cond/_fdir/_acc_93m.tif`) — reruns take ~2 min

**Final: Very low 67.8%, Low 11.7%, Moderate 7.9%, High 5.6%,
Very high 6.93% (40,204 km²), Permanent water 12,210 km².**

Six of seven landmarks correct. Budalangi reads Moderate — it floods by
**dike failure**, which HAND structurally cannot see.

### connectivity.coverage — run 69, 37,122 rows
From the CA's public ArcGIS Hub (the catalogue's "likely not
redistributable" note was an untested assumption and was **wrong**).
- 2g/all 9,274 · 4g/all 7,134 · 4g/Safaricom 10,357 · 4g/Telkom 10,357
- **NO 3g**: the CA published one dataset under two technology names,
  99.9% identical to six decimal places. The weaker layer is deleted.
- Schema v1.4 added `coverage_pct`, `admin_*`, `source_layer` etc.

### demographics.nightlights — run 73, 7,345 rows
NASA Black Marble VNP46A4 (ArchiveSet **5200**), 2015/2019/2022/2023/2024.
EOG's VNL was abandoned — programmatic access is now paid-subscribers-only.
GEE was rejected: **its free tier is noncommercial only.**
- Schema v1.5 added `trend_radiance_yr`; **`trend_pct_yr` is deliberately
  NULL**

### climate.rainfall — runs 79 and 80, four new variables
- `rainfall_recent_mean`, `rainfall_anomaly_pct`, `rainfall_driest_year_pct`
  (CHIRPS v3.0, 2021–2025)
- `rainfall_max5day_mean`, `rainfall_max5day_p90` (CHIRPS **v2.0**, 2010–2025)

### satellite.landcover — run 81, PARTIAL
Impact Observatory 2017/2023/2024 at 93 m. **CC BY 4.0, commercial OK.**
Yearly snapshots are fine. **The change layer is NOT shippable — see §4.**

---

## 3. THE FINDINGS THAT MATTER MOST

**1. 42% of "Kenya" was not Kenya.** `hazards.flood` class areas summed to
1,002,267 km² against Kenya's 580,367. The padded bounding box included the
Indian Ocean, Ugandan/Tanzanian Lake Victoria and neighbouring land; GLO-30
gives ocean an elevation of 0 rather than nodata, so it passed the "is there
land here" test. Fixed by rasterising `admin.country`. **Very high fell from
10.69% to 6.93%.** This same error hit land cover in session 5 and rainfall
in session 6 — **it has now occurred four times.**

**2. The nightlights trend was measuring the wrong thing.** Every
verification check passed while the metric was unusable: median ward at
33%/yr (11× over nine years), top wards in rural Homa Bay. Cause: log growth
from a near-zero base, with **335 of 1,422 wards at exactly zero in 2015**.
Absolute radiance change won outright — its top wards are Ruai, Kitengela,
Muthwani, Gatongora, Murera, Kalimoni, Gitothua, Mihang'o, Karen, and Hindi
on the LAPSSET corridor. Top-50 rank overlap between the two metrics: **0/50**.

**3. A mean can hide a drought.** Rainfall 2021–2025 averages **107% of
normal** while **68.9% of Kenya had a single year under 75% of normal** and
8.6% under 50%. The `driest_year` layer exists only because the mean looked
fine.

**4. Absolute HAND cannot work for flood.** No channel threshold satisfies
both a credible national share and correct landmarks — 5 km² gets every
landmark right with 21% of Kenya at HAND ≤ 2 m; 30 km² fixes the share but
never flags Garissa above Moderate. The fix was scaling by catchment size,
not tuning the knob.

**5. Impact Observatory is not temporally consistent** (see §4).

---

## 4. KNOWN BROKEN / NOT SHIPPABLE

### `landcover_change` (satellite.landcover) — DO NOT USE
IO's series shows tree cover going **13.58% → 25.58%** in seven years and
**23.05% of Kenya changing class**. Kenya's tree cover did not nearly double.
IO's Built area also reads 1.72–2.59% against WorldCover's 0.32% — a 5–8×
divergence. This is classifier drift between model versions, not ground
change.

**Action:** mark `variable = 'landcover_change'` as `pending_review` or
delete the catalogue row. Keep the yearly snapshots (each is a valid
single-date classification). **Change detection — the main reason we chose
this dataset — is not available from it.**

### Orphan ETL run row
A Ctrl+C during `etl_29` left a `metadata.etl_runs` row stuck at `running`
(KeyboardInterrupt bypasses the error handler). Harmless; close it manually
if you want a tidy audit trail.

---

## 5. DOCUMENTATION DEBT — DO THIS FIRST

**`PROGRESS.md` is five datasets behind.** It is written up through
`connectivity.coverage` only. It is **missing entirely**:

- `demographics.nightlights` (source switch, Black Marble, lessons 25)
- The nightlights trend calibration and schema v1.5
- `hazards.flood` runs 75 and 77 (permanent water class 6, the country clip)
- `climate.rainfall` recent + anomaly + driest-year (etl_27, run 79)
- `climate.rainfall` extremes (etl_28, run 80)
- `satellite.landcover` IO + the change-layer failure (etl_29, run 81)

**This is the highest-value first task in the next session.** The code is
recoverable; the reasoning behind these decisions is not.

`PRE_LAUNCH_CHECKLIST.md` also needs three additions:
1. CHIRPS **v2.0 vs v3.0 version split** — v3 publishes no pentad product, so
   extremes are v2 while normal/recent are v3. Nothing divides across
   versions, but they are not the same lineage. **CHC ends v2 production
   after December 2026 — re-probe then.**
2. **Fixed-pentad under-estimate** — a storm straddling a pentad boundary is
   split, so max-5-day under-estimates a true rolling maximum by ~10–20%.
   Consistent nationally, so the spatial pattern holds. Not design rainfall.
3. **IO land cover is not temporally consistent** (§4).

---

## 6. IMMEDIATE NEXT STEPS, IN ORDER

1. **Write up PROGRESS.md** (§5). Start the session with this.
2. Mark `landcover_change` as `pending_review`.
3. **Re-calibrate `AMIN_TOP_KM2`** (flood) on the country-clipped
   denominator. It was tuned when the denominator was 42% too large. The
   current value of 10 km² still passes, but there is now headroom to LOWER
   it and warn MORE, which this layer's stated rule favours.
   Run `calibrate_scaled_hazard.py` — but **add the country clip to it
   first**, it does not have one.
4. **Two emails.** CA (info@ca.go.ke): licence terms for the coverage
   geoportal, AND **which of their 3G/4G layers is correctly labelled**.
   Kenya Power via Njeri's contact: derived-use licence.
5. **Wire rainfall extremes into hazards.flood** as a forcing term. Keep it
   as `susceptibility × forcing` — two explainable numbers, NOT merged into
   one score with invented weights.

---

## 7. FILES CREATED OR CHANGED IN SESSION 6

**ETL scripts (`03_etl/`)**
- `etl_24_hazards_flood.py` — rewritten (flow routing, catchment scaling,
  class 6, country clip)
- `etl_25_ca_coverage.py` — new
- `etl_26_nightlights.py` — new (Black Marble)
- `etl_27_rainfall_recent.py` — new
- `etl_28_rainfall_extremes.py` — new
- `etl_29_io_landcover.py` — new

**Verification / calibration (`03_etl/`)**
- `test_hand_routing.py` — synthetic terrain, 8 checks, seconds to run
- `calibrate_channel_threshold.py` — proved no threshold works
- `calibrate_scaled_hazard.py` — chose the catchment scaling
- `calibrate_nightlight_trend.py` — chose absolute over percentage
- `verify_25_coverage.py`, `verify_26_nightlights.py`

**Schema (`01_database/`)**
- `05_schema_update_v1.4.sql` — connectivity.coverage percentages
- `06_schema_update_v1.5.sql` — nightlights trend_radiance_yr

**Docs (`04_docs/`)**
- `PRE_LAUNCH_CHECKLIST.md` — NEW. 5 legal blockers, 3 third-party
  questions, 9 accuracy items, 13 product rules, 7 engineering rules.
- `PROGRESS.md` — updated through connectivity.coverage only
- `SESSION_6_HANDOFF.md` — this file

---

## 8. HOSTING — RECOMMENDATION SUMMARY

Session 4's decision to keep rasters OUT of PostGIS (pointers only in
`metadata.raster_catalog.storage_url`) means migration is *copy files, update
one column* — not a rewrite.

- **Object storage:** Cloudflare R2 is worth a hard look — S3-compatible and
  **zero egress fees**, which matters a lot once a portal serves map tiles.
  Alternatives: S3 `af-south-1`, Backblaze B2. ~10–15 GB today.
- **Managed Postgres + PostGIS:** DigitalOcean Managed Postgres or Supabase
  for a pre-revenue product; AWS RDS `af-south-1` for lowest Kenyan latency.
- **Verify current pricing and PostGIS versions before committing** — the
  architecture is stable, the numbers change.
- **Timing:** after the enrichment engine design settles (it determines query
  patterns and sizing), before the pilot client.
- Also budget: automated backups, PgBouncer pooling, a local dev copy.

---

## 9. THE ROAD TO PRODUCTION

| Phase | Status |
|---|---|
| 1. Data | **Essentially done** — 25/27 P1 |
| 2. Accuracy debt | Checklist §C. Blocking: KNBS census, IEBC ward codes, flood re-calibration |
| 3. Enrichment engine | Not started. **This is the product.** Must enforce the 13 rules in checklist §D |
| 4. Scoring, API, PDF reports, portals | Not started |
| 5. Legal clearances | **Gates selling anything.** Checklist §A — 5 open items |

**The item to start early:** OSM's ODbL share-alike touches roads, rivers and
waterbodies. If it attaches to a derived database, that is a structural
decision about the product, not a footnote. Get a legal opinion before the
enrichment engine hard-wires those layers in.

---

## 10. HOW TO OPEN THE NEXT SESSION

> Read `04_docs/SESSION_6_HANDOFF.md`, `04_docs/PROGRESS.md` and
> `04_docs/PRE_LAUNCH_CHECKLIST.md`. Session 6 finished five datasets but
> PROGRESS.md is five datasets behind — write it up first, then re-calibrate
> the flood threshold on the country-clipped denominator.

**One standing instruction worth repeating to any future session:** six
values were asserted from memory in session 6 and every one was wrong
(`metadata.sources` columns, `admin.counties.name`, county aliases, `slcode`
semantics, EOG's OAuth secret, the LAADS ArchiveSet). Each cost a failed run;
each was settled in seconds by reading the source. **Query it, don't recall
it.**
