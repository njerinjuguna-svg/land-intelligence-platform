# SESSION 14 HANDOFF

Project: Land Intelligence Platform, Geocode Spatial Solutions Ltd
Root: E:\Land Intelligence Platform Geocode\Land Intelligence Platform
Stack: Windows, PostgreSQL 16 + PostGIS, db land_intelligence_kenya, venv at 03_etl\venv, FastAPI + uvicorn
Repo: github.com/njerinjuguna-svg/land-intelligence-platform (private)

## 1. Standing working rules

- Njeri runs every command. Claude edits files; she executes. No database access from Claude's side.
- Give the whole PowerShell block each time, including cd and venv activation. Never fragments.
- Do not work in stages or ask "shall I continue?" If a direction is agreed, do all of it in one turn.
- PROGRESS.md and PRE_LAUNCH_CHECKLIST.md are the durable record. Ask before appending. Deliver additions as separate appendNN.md files she pastes in.
- Files reach her disk via the desktop bridge. If it drops, retry once, then attach instead.
- Before believing a failure, check the test. Several bugs this build have been in the verification, not the thing verified.
- No em dashes in buyer-facing copy.
- Plain language. She has said twice that dense explanations are hard to follow.

## 2. Product rules that do not move

- Phase 1 = enrichment of a seller's own parcels, shown as a widget on their site. Descriptive only. No verdicts, no warnings, no refusals.
- Phase 2 = the Geocode marketplace, where suitability verdicts, flood warnings, protected-area refusals and the "before you pay" checklist live.
- Never print a claim we cannot source. No title status, no zoning, no electricity connection, no per-operator coverage.
- A4/B4: ship values and pictures, never geometry, enforced by assert_no_geometry(). One narrow exception added this session, see section 5.

## 3. The big finding: Oak Grove was never loaded properly

05_enrichment/sample_parcels/OAK GROVE.kmz is an AutoCAD drawing exported to KML, not a parcel file.

What is actually in it:

- 1,086 placemarks, every one a LineString. Zero polygons.
- 1,073 are two-point line segments.
- Entity types: Line 1,025 / LWPolyline 58 / Arc 2 / 3DPolyline 1
- 15 CAD layers: 1FIANLSUBDIVISION (984), HIGH VOLTAGE (25), polylines (11), 0 (10), 1SUBDIV (10), roads (8), PUMP HOUSE (8), PDF_C-ANNO-TABL (8), boundary (7), sold (6), PDF_roads (3), PDF_0 (2), parcel23 (2), river_new_Project (1), new dimensions (1)
- Not one placemark has a name.

What went wrong: 03_load_client_parcels.py needs 3+ points to build a ring, so it kept 13 stragglers and silently discarded 1,073. Its fallback ref is PLOT-{index}, so PLOT-365, PLOT-457, PLOT-950 etc. were array positions in a CAD export, not plot numbers. They were loaded, enriched, scored and shown on a client-facing map as plots.

The fix: node the whole line network and take the enclosed faces. Not inventing geometry; every edge was drawn by the surveyor and the faces are determined.

Result: 720 faces, 688 kept, 99.9 acres, median 450 m2. 463 of them between 420 and 480 m2 (one plot module repeated).

Three things learned that must not be lost:

1. Full coordinate precision is mandatory. WKT at %.8f (1.1 mm) gives 308 faces; full precision gives 720. Rounding turns a dividing line's endpoint into a dangle and merges plots in pairs, silently. The script measures this and writes it into provenance.
2. All CAD layers go in. Restricting to "subdivision" layers loses 72 real plots whose frontage was drawn on the roads layer.
3. Stale parcels must be retired before the gate runs. PLOT-950 is an 8.5-acre blob; gated against it, dozens of correct plots get rejected for overlapping a thing that is not a parcel.

Numbering: OG-001 to OG-688, blocks found with ST_ClusterDBSCAN, ordered from the north-west then along each block so consecutive numbers are neighbours. This is Geocode's map label, NOT the scheme's plot numbers (recorded in every row's test_expectation). The source file has no numbers in any form. A real plot number needs the numbered DXF, a shapefile with attributes, or the mutation drawing.

Filters: min 150 m2, max 4 acres, compactness P2/A <= 40. Dropped 22 too small, 7 corridor-shaped, 3 stray rectangles 14 km off site.

Re-running on an unchanged file is now a no-op (ST_Equals + confidence check). It was not; a double-run created 688 redundant v1 rows.

## 4. Current data state

verify_01_enrichment.py: 700 parcels (688 OG + 12 landmark test parcels). All 42 fields at 696-700/700 coverage. 44 passed, 1 FAILED, 1 known gap.

Fields: flood_risk_class, flood_risk_breakdown, dist_any_road_m, dist_permanent_water_m, soil_type, soil_ph, soil_texture, black_cotton_risk, rainfall_normal_mm_yr, slope_mean_pct, ndvi_mean, landcover_class_worldcover, landcover_composition, landcover_class_io, built_up_pct_1km, in_riparian_buffer, dist_river_m, in_protected_area, dist_primary_school_m, dist_secondary_school_m, dist_hospital_m, dist_clinic_m, dist_water_point_m, pop_density_km2, nightlights_radiance_mean, nightlights_trend_radiance_yr, coverage_4g_pct, coverage_2g_pct, dist_tower_m, dist_town_centre_m, nearest_town_name, dist_airport_m, nearest_airport_name, dist_intl_airport_m, nearest_intl_airport_name, dist_major_road_m, dist_market_m, dist_police_m, dist_bus_stop_m, dist_railway_station_m, field_confidence, field_sources

verify_02_suitability.py: only 12 parcels scored. 42 passed, 0 failed.

### THE BLOCKER: score_01_suitability.py HAS NOT BEEN RUN ON THE 688

Every card in the demo says "Not rated". The demo shows a map and no product.

```powershell
cd "E:\Land Intelligence Platform Geocode\Land Intelligence Platform\05_enrichment"
..\03_etl\venv\Scripts\Activate.ps1
python score_01_suitability.py
python verify_02_suitability.py
```

### Two findings in the verify report

- The one FAILURE is in the test, not the data. PLOT-457 / nearest_intl_airport_name: got None. PLOT-457 is a retired CAD fragment and is not among the 700. The invariant needs re-pinning to a live parcel.
- Section C: 36 plots at 7-18 degrees against a project median of 2.25: OG-077 to 099, 233-236, 278-290, 384-391, 458, 513. These are the northern arm, eastern wedges and the isolated western sliver (scheme edges). The verifier's explanation ("if REPAIRED at load") is stale; these came from polygonization. The signal may still be right: some could be road reserve or riparian strip rather than sellable plots. Check against recovered_OAK_GROVE.kml in Google Earth.

### Licence exposure (pre-launch blockers, unchanged)

- coverage_2g_pct / coverage_4g_pct: Communications Authority of Kenya NOT DECLARED
- A1: WDPA is non-commercial. Replace with KWS or get written clearance.
- A4: OSM is ODbL share-alike; in_riparian_buffer is derived geometry and the high-exposure item.

## 5. The geometry firewall: one door cut

Njeri chose a live Google map over the drawn picture. There is no version of a live map where the browser does not hold the shapes.

- assert_no_geometry() is unchanged and still guards every analysis payload.
- New endpoint /v1/scheme/plots is the single documented exception.
- What leaves: the client's own parcel outlines, to that client's own key, at 6 decimal places.
- What never leaves: anything derived (soils, rainfall, buffers, amenities, anything from environment.* or analytics.*).
- The query selects land.parcels.geom and nothing else. If it ever grows a join onto a derived table, that is the moment this stops being defensible.
- Consequences: a competitor can read the outlines from the page (so it is per-client, enabled only by the presence of a browser key), and Google bills the Maps JavaScript API per map load, so cost scales with the seller's traffic.

## 6. Files created this session

| File | What |
|---|---|
| 05_enrichment/kmz_probe.py | Reports what is really in a KMZ/KML: layers, entity types, points per placemark, names. Loads nothing. |
| 05_enrichment/04_polygonize_cad.py | Recovers plots from a CAD line network. Dry-run default. --load, --retire-stale, --limit. Writes recovered_<PROJECT>.kml and .geojson. |
| recover_plots.cmd (root) | `recover_plots.cmd` to look, `recover_plots.cmd load` to write. |
| 06_delivery/demo_fusion.html | Fusion Estates Oak Grove listing replica + widget. |
| 06_delivery/demo_fusion_home.html | Fusion Estates homepage replica. Oak Grove card opens the listing. |
| 04_docs/03b_kplc_linkedin_message.md | LinkedIn approach to the KPLC GIS head. |
| mockup_plot_link.html | Design mockup of the shareable WhatsApp plot page (sent in chat, not on disk). |

## 7. Files modified

### 06_delivery/api_01_embed.py

- INDEX_MAX (was 200 hardcoded in three queries) now 1000, plus INDEX_COUNT_SQL for the true total. The page printed "N of 200 available" on a 688-plot scheme.
- _frame_and_zoom() replaces the fixed 640x360 frame. Picks zoom first, then cuts the frame to the content. 9% of plots numbered at 640x360 vs 97% at 640x560.
- _latlon_from_world(): inverse Web Mercator, for tap resolution.
- _scheme_frame() / _scheme_frame_geometry(): one definition of the picture's geometry, used by both drawer and tap handler, cached on _updated_tag.
- /v1/scheme/at: tap resolution. Browser sends a fraction; server inverts and runs ST_Contains, then nearest within TAP_TOLERANCE_M = 10. Tested 150/150 round-trip, corners return nothing.
- /v1/scheme/plots: the live-map geometry endpoint (section 5).
- /v1/scheme/map?detail=1: same ground at 2x resolution, stitched from 4 tiles.
- Label drawing: one uniform font size (30th percentile of what fits), ceiling 26, no plot skipped. Sides recovered exactly as roots of t^2 - (P/2)t + A, not 2A/P.
- seller_strip() now returns "" ("Listed by" and "Independent analysis by Geocode" removed at her instruction). Function kept so it is one line to reverse.
- _imagery_html(): one box, up to three panes (Satellite / Map / Street), toggled not reloaded.
- GOOGLE_EMBED_KEY reads GOOGLE_MAPS_BROWSER_KEY or GOOGLE_MAPS_EMBED_KEY. Refuses to use it if it equals the server key.
- /v1.js now no-cache + ETag (was max-age=300, which paired new markup with an old loader).
- /demo?site=<name> route with path scrubbing.
- CSS: .smap pan/zoom, .smapz zoom buttons, .livet toggle, .live [data-giq-pane]. Removed aspect-ratio:16/9; object-fit:cover.

### 06_delivery/v1.js (now v1.3.0)

- absolutise(): rewrites root-relative /v1/ image paths to the correct origin. Real latent bug: every picture would have 404ed on a real client's site. Only worked because the demo is same-origin.
- hideIfBroken(): a failed image removes its own frame instead of a broken-image icon.
- bindMapGestures(): drag, +/-/reset, double-click, pinch, Ctrl+wheel. Bare wheel left to the host page.
- loadDetail(): swaps in the 2x image on first zoom.
- liveScheme() / drawLive(): Google Maps JS, 688 clickable polygons, labels at zoom >= 17 capped at 300, falls back to the drawn picture on any failure.
- bindViewSwitch(): bound for both scheme and single-plot modes (was dead on a data-plot-ref page).

### 06_delivery/demo_page.html

Rebuilt (Kamau Properties, fictional).

## 8. Google and keys

- Billing is NOT enabled on project climate-risk-analysis-kenya. check_maps_key.py returns Google's own words: "The Google Maps Platform server rejected your request. You must enable Billing on the Google Cloud Project".
- The scheme map only kept working because it was cached on disk. Every per-plot image is a fresh request and fails.
- Server key must NOT have website restrictions (server requests carry no HTTP referrer).
- Browser key must be restricted to Maps Embed API AND Maps JavaScript API. The one created is restricted to Embed only. It was visible in a screenshot, so treat it as public; the website restriction is what protects it.
- Cost shape: every plot image is cached to disk on first fetch, so Oak Grove is a one-off of ~1,400-2,000 calls. The live map bills per page view.
- The platform API key vanished: the row was absent, not revoked. clients.api_keys has been overwritten before (restore drill found 3 live vs 1 in the dump). Worth an hour to find which script does it.
- A new test key was issued (value kept out of this file on purpose; it is in the old chat and in clients.api_keys).
- clients.api_usage UPDATE throws on every call. Usage counting is dead, and rate limiting and billing both read that table. Need the ten lines above the error to fix it.

## 9. Business and strategy

### Competitors

- First Street on Zillow/Redfin: closest to Phase 1. Independent risk data embedded in someone else's listing, credited by name. The credit is the product. US agents have pressured Zillow to remove it, a real risk under Phase 1.
- LandApp: $6/month, 150M US parcels, soil/topography/slope/flood + 0-100 indexes.
- Land id: $7-$67/month per seat, 40+ toggleable overlays, sold to professionals.
- Regrid: the parcel data layer everyone else buys.
- Searchland / LandInsight / Nimbus: UK land sourcing.
- PlotSight (Nigeria): closest African analogue. Buyer pays per check, from NGN 5,000, 2 free.
- Kenya: no product competitor. Only law firms, consultants and blog checklists.

### Land id comparison

They have that she does not: ownership/parcel records, zoning, US federal utility data, water wells, 2ft LiDAR contours, comparable sales. All things the US publishes and Kenya does not. Market absences, not capability gaps.

She has that they do not: 42 computed fields vs layers you interpret yourself; rainfall normals + driest-year percentile; NDVI; land cover composition; night lights and trend; 2G/4G coverage; measured named-amenity distances; black cotton risk; suitability scores that reconstruct from their components; per-field provenance and confidence; plot recovery from unstructured CAD.

Land id Pro now sells soil reports and "AI Insights", drifting from layers toward answers. Her direction is right and the window is real.

### Delivery: three modes, one server

1. Paste the code: two lines into a WordPress Custom HTML block. Works.
2. Hosted page: app.geocode.co.ke/fusion/oak-grove. ~90% built; needs generating per client.
3. Per-plot link: app.geocode.co.ke/p/fusion/oak-grove/412 for WhatsApp, plus QR codes and a printable sheet. Not built. Possibly the highest-value item.

### Pricing

- Setup fee per scheme + monthly per scheme. Not per plot. Not revenue share.
- The question that sets the price: "What does it cost you when a buyer comes for a site visit and walks away?" Their number, not hers.
- Diaspora buyers are where the pricing power is.
- For Fusion: small real setup fee, then free months. Get written permission to use their name, screenshots, and a reference call.

### Independence

Recommended a quiet line "Analysis by Geocode / how we measure this", especially on the WhatsApp page. Her call; currently removed.

### KPLC / water / sewer: parked

Kenya publishes no utility network data. Septic viability = soil texture + infiltration + slope, already measured. Water is the real hole; WRA borehole records are a more realistic ask than KPLC.

### Photos

System-generated (hers, evidence); seller marketing (theirs, behind a labelled bar, https links to their site, never mixed with measured data); per-plot photos impractical. Drone imagery is an upsell.

## 10. Decisions made at the end of session 14

- Server move deferred until MVP is finished and there are clients to pitch.
- Oak Grove is for the Fusion pitch only.
- She needs her own demo scheme: fictional subdivision on real ground, ~120 plots, designed with variety (river edge, slope, near/far from amenities).
- Second reason: the pipeline has never been tested on a second file.

## 11. Open questions not yet answered

1. Demo scheme: where, and what fictional company name? (Kitengela would exercise black cotton; a river edge would vary flood and riparian.)
2. Mockup feedback: seller's logo size, Geocode line too quiet or loud, price on the plot page or not?
3. Build first: amenity/road names, shareable plot link, or client handover sheet?
4. What she does when a client asks her to remove a finding (36 Fusion plots on steeper ground). Decide before the meeting.

## 12. Immediate next actions

1. python score_01_suitability.py. The 688 are unscored. Nothing else matters until this is done.
2. Get the traceback for the clients.api_usage error and fix it.
3. Re-pin the PLOT-457 invariant to a live parcel.
4. Commit session 14 work to git. None of it is committed.
5. Paste append11.md, append11b.md, append12.md, append13.md into PROGRESS.md (outstanding from session 13).
6. Build the demo scheme, run the full pipeline on it.
7. Names on amenities and roads (code already picks the named major road, then discards the name).
8. Shareable plot link + QR codes + printable sheet.
9. Rate limiting against clients.subscriptions.
10. Title (B5) and price: hers to decide, blocks the client agreement.
