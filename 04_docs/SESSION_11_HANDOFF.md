# SESSION 11 HANDOFF — 24 August 2026

Scratch handoff, not the durable record. **PROGRESS.md and PRE_LAUNCH_CHECKLIST.md
have NOT been touched** — the Session 11 write-up is drafted in my head and is the
first thing to do tomorrow, with Njeri's go-ahead.

---

## STATE AT CLOSE

**Verification: 43 passed, 0 FAILED, 1 known gap, exit 0.**
Enrichment run `f4555739-eadb-4b7b-ade3-25a8c753df39`, engine v7 + landmarks.

### What was built

| Thing | Where | Status |
|---|---|---|
| Landmarks ETL — 6 tables, 14,221 rows | `03_etl/etl_30_osm_landmarks.py` | run, clean |
| `admin.places` + 6 landmark columns | `01_database/11_schema_update_v1.8.sql` | applied |
| International-airport column pair | `01_database/12_schema_update_v1.9.sql` | applied |
| `layer_landmarks()` — 12 columns | `05_enrichment/enrich_01_engine.py` | run |
| Section G, 12 new checks | `05_enrichment/verify_01_enrichment.py` | 43/0 |
| Buyer page on real PLOT-457 values | `04_docs/mockups/landiq_buyer_page.html` | published |

Row counts: `admin.places` 9,323 · `transport.airports` 255 ·
`transport.bus_stops` 1,082 · `transport.railways` 750 · `social.markets` 2,205 ·
`social.public_services` 606.

---

## THE ONE LESSON, IN FOUR COSTUMES

Every defect today had the same shape and **none of them was a bug**. The query was
right, the join was right, the distance was right, and the ANSWER was still wrong,
because the column was answering the question NEXT TO the one a buyer was asking.

1. **`Shekiko Airport (disused)`** — a facility out of service. OSM said so in the
   name, so a word filter could find it. Fixed in `etl_30` (`DEFUNCT`).
2. **`GSU Airstrip`** on all 8 OAK GROVE plots — fully operational, and a police
   airstrip nobody flies from. **Nothing in the data says so.** A filter could never
   find this one, because the defect was in the question, not the data. Fixed by
   adding `dist_intl_airport_m` — `international` is the only aviation class this
   database verifies rather than infers.
3. **A village is not a town centre** — 8,679 of 9,323 places are villages. Measuring
   to the nearest of any kind would have measured OSM's tagging density, not access
   to a town. Same trap as C8.
4. **A named major road must be FURTHER than the paved road** — it is a subset, so it
   can never hold a nearer member. Now a verifier invariant that needs no knowledge
   of Kenya at all.

> A filter can catch a fact the source admits. It cannot catch a question that was
> subtly wrong. Only reading the answers out loud catches that.

Also mine, and worth remembering: I wrote a confident comment blaming `i.*` column
shadowing for the missing plot size **before checking the schema**. It was wrong —
`parcel_intelligence` has no `area_sqm`; the column is simply NULL and the geometry
had the answer all along. Rule E2 does not stop applying because the guess is a good
one.

---

## TOMORROW, IN ORDER

1. **Write up Session 11** in `PROGRESS.md` + 3 checklist items:
   - rename `transport.bus_stops` (it holds every transport stop, not just buses)
   - **listing-status onboarding requirement** (see below)
   - extend D20 to landmarks: never publish a landmark a buyer cannot use
2. **Add WASREB to the letter batch** — Majidata is the national georeferenced water
   and sewer network system (Water Act 2016 s.111). It is exactly
   `dist_water_line_m` / `dist_sewer_m`. Buried mains mean **OSM has nothing** — it
   is a letter or it is nothing. Bundle with KWS / KPLC / the other drafted letters.
3. **The KWS letter is still the cheapest high-value move on the board** — closes A1
   and fixes the coarse-boundary risk that has Kakamega blocked.

## THE CLIENT CONVERSATION — TWO HANDSHAKES, NOT ONE

Known before: `parcel_ref` mapping, agreed once at onboarding.

**New, and it is ONGOING:** all 8 OAK GROVE plots read `listing_status = 'available'`
and every `price_kes` is NULL. The scheme-availability panel — the strongest
sales feature on the buyer page — is a live window into the client's own sales and
only works if somebody keeps `listing_status` current after go-live. That belongs in
the agreement, not in a discovery six months later.

## STILL OPEN

- **B5 — title.** Njeri's decision. No "Verified" badge on any page until made.
- Power / transformer distance: needs an Overpass download (Geofabrik's free
  shapefile set omits the power layer).
- Per-operator 4G naming: blocked on CA confirmation (B1b).
- Satellite + Street View panels: need a Google Maps key with billing.
- `PLOT-1069` / `PLOT-1070` share one polygon. `PLOT-950` slope 14.38 deg against a
  project median of 3.00. Both still flagged, both still unexplained.
