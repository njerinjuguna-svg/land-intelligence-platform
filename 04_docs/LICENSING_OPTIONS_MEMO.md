# Share-Alike Exposure — Options Memo

**Land Intelligence Platform · Geocode Spatial Solutions Ltd**
**Prepared: session 7, 2026-08-18 · For: Njeri**
**Status: decision document. Nothing here is legal advice — it is the factual
position and the realistic paths, written so that the question put to a lawyer
is short, specific and cheap to answer.**

---

## 1. Why this memo exists

Two datasets carry **share-alike** licences:

| Source | Licence | Feeds |
|---|---|---|
| OpenStreetMap (via Geofabrik) | ODbL-1.0 | `transport.roads` (730,006 segments), `environment.rivers` (46,529), `environment.waterbodies` (14,945), and **`environment.riparian_buffers`** (41,862) derived from the rivers |
| OpenCellID (Unwired Labs) | CC-BY-SA-4.0 | `connectivity.towers` (142,279 cells) |

Share-alike means: under some conditions, what you build from the data must be
released under the same licence. If that condition attaches to the enrichment
database, it reaches the product itself — so this is an architecture decision,
not a footnote, and it must be settled **before the enrichment engine hard-wires
these layers in.**

The good news, and the point of this memo: **the exposure is much smaller than
"our whole spatial stack", and two-thirds of it can be engineered away cheaply.**

---

## 2. What the licence actually requires

ODbL divides what you make into two categories:

- **Derivative Database** — carries share-alike.
- **Produced Work** — an image, document, report or map rendered *from* the
  data. **You may licence a Produced Work however you like.** You must
  attribute, and you must, on request, offer recipients the underlying database
  under ODbL.

The test the OpenStreetMap Foundation gives: *if the published result is
intended for extraction of the original data, it is a database; otherwise it is
a Produced Work.*

There is also a **Geocoding Guideline** covering the closest analogue to what we
do. It holds that where OSM is not modified beyond trivial transformation, and
results are not used to build a new database containing a substantial part of
OSM, share-alike is not triggered — results based on an "Indirect Hit" contain
no raw OSM at all, only inferences from it.

**So the question is never "is ODbL a problem". It is: WHICH OF THE THINGS WE
SHIP IS A DATABASE?**

> **An obligation that is easy to forget:** even when shipping only Produced
> Works, ODbL requires that on request you offer the derivative database under
> ODbL. That is an operational commitment — someone must be able to answer that
> request — not merely a licensing footnote.

---

## 3. Three exposures, not one — ranked

### HIGH — `environment.riparian_buffers`
41,862 polygons, buffered from OSM river centrelines under EMCA 2009, Water
(Resources) Regs 2025 and Survey Regs Cap 299.

**This is the sharp one, and it is sharp precisely because it matters most.**
It is derived *geometry* — unambiguously a database, not an inference — and it
is the layer our own build log calls "the first layer that is genuinely our
intellectual property rather than someone else's data reshaped." It is also a
genuine market differentiator: nobody else in the Kenyan land market surfaces
riparian reserve overlap automatically.

If share-alike reaches anything, it reaches this.

### MEDIUM — `transport.roads`, `environment.rivers`, `environment.waterbodies`
Raw OSM held verbatim in PostGIS. Plainly a copy.

**But share-alike triggers on distribution, not on possession.** Holding OSM
internally to compute things is not conveyance. This becomes a live problem only
if we ship the geometry — an API returning road lines, a bulk export, a shapefile
handed to a client.

### LOW — `analytics.parcel_intelligence`
Stores `dist_any_road_m = 340`. A number inferred from OSM, containing no OSM
data. Nobody reconstructs a road network from a distance.

This is the closest match to the Geocoding Guideline's Indirect Hit, and the
weakest exposure in the stack. The per-parcel PDF report built from it is very
likely a Produced Work.

---

## 4. The decision that gates everything — and it is yours, not a lawyer's

**What actually leaves the building?**

| Delivery form | Share-alike exposure |
|---|---|
| PDF report per parcel | Lowest. Almost certainly a Produced Work. |
| Rendered map tiles / images | Low. A rendered map is the textbook Produced Work. |
| API returning **values** (distances, classes, scores) | Low–medium. Inferences, not data. |
| API returning **geometry** (the buffer polygon, road lines) | **High. This is shipping a database.** |
| Bulk export / data feed to a client | **Highest. Unambiguously a database.** |

### DECIDED, session 7 (Njeri)

> **The PDF is the analysis only — no images.** Imagery belongs on the
> seller's platform, where a buyer wants directions to the land, or Street
> View if it exists for that plot.

**This is a good answer and it removes most of the exposure at a stroke.**

**The PDF carries no imagery**, so every imagery licensing question — Google's
caching and printed-output restrictions, basemap attribution inside a document
we sell, tile terms in a commercial PDF — **simply does not arise for the
deliverable.** The report is text and numbers derived from data: about as
clearly a Produced Work as it is possible to be.

That leaves the platform, and it splits into two very different things:

| Platform function | What it needs | Position |
|---|---|---|
| Show the parcel and our derived layers on a map | A basemap + overlays | Rendered view = Produced Work. Self-render from OSM: clean and free. |
| "Directions to my land" and Street View | Routing, street-level imagery | **Do not build this. Link out.** See below. |

### DEEP-LINK OUT FOR NAVIGATION AND STREET VIEW

A plain `https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>` link
hands the buyer directions, live traffic, satellite view and Street View where
it exists — **at zero cost and zero licensing exposure to us**, because the
user is then on Google's consumer service under Google's own terms, not
consuming our API quota under ours.

What this avoids, all at once:

- Directions API and Street View Static API billing
- Google Maps Platform caching and storage restrictions
- **The rural Street View coverage problem stops being ours.** Where Google
  has no imagery the buyer sees that directly, rather than our platform
  promising a feature it cannot deliver on most Kenyan plots.
- Mapillary's CC-BY-SA share-alike, which was the other street-level route

Buyers already know the Google Maps interface and will navigate with it
anyway. Rebuilding a worse version inside the platform costs money and adds
licence surface for no advantage.

### THE ONE ARCHITECTURAL RULE THIS LEAVES

If the platform draws the riparian buffer or a flood polygon on a map, **that
overlay must be rendered SERVER-SIDE into the image or tile.** The moment the
backend sends the buffer geometry to a browser as GeoJSON, we are transmitting
derived spatial data rather than a picture of it — which is precisely the
Produced Work / Derivative Database line.

**Ship values and pictures. Never geometry.** Decide this before the platform
is built; retrofitting it is expensive.

(The parcel's own boundary is the client's data, not ours and not OSM's, so it
may travel freely.)

---

## 5. The options

### Option A — Change nothing; ship only Produced Works
Keep OSM and OpenCellID. Ensure everything delivered is a report, a rendered
map, or a set of values. Never ship geometry or bulk data. Attribute properly.

- **Engineering cost:** near zero.
- **What it buys:** the fastest path to a pilot.
- **What it costs:** a permanent constraint on the product. The moment a client
  wants the riparian polygon in their own GIS — which land companies do ask for —
  the answer is no, or the answer is ODbL.
- **Residual risk:** the riparian buffer layer still sits in our database as a
  derivative of OSM. Low risk while undistributed; not zero.

### Option B — Move rivers off OSM, keep OSM roads  ← **recommended**
Rebuild `environment.rivers` from a commercially clean source, then re-run
`etl_12` so the riparian buffers derive from that instead.

**Our own catalogue says rivers were never meant to be OSM.** `datasets.csv`
lists `environment.rivers` with **WRA as primary source and HydroSHEDS as
backup**. OSM was a substitution of convenience in session 2.

Two clean candidates, and **checking their specifications reversed which one I
would lead with:**

**1. HydroSHEDS / HydroRIVERS** — free for non-commercial *and* commercial use
with attribution, already registered in `sources.csv`. **But it only includes
rivers with a catchment of at least 10 km² or mean flow of at least
0.1 m³/s**, extracted at 15 arc-second (~500 m) resolution.

That threshold is the problem. Our riparian widths are 30 m for rivers and
**6 m for streams** — and streams are precisely what a 10 km² cutoff removes.
Swapping OSM's 46,529 mapped segments for HydroRIVERS would silently delete
most of the small-watercourse buffers, which is a *worse* product failure than
the licensing exposure it fixes.

**2. Our own DEM-derived channel network — the better lead.** `etl_24` already
derives channels from the Copernicus GLO-30 DEM by flow accumulation at
**≥ 5 km²**, i.e. denser than HydroRIVERS, at 93 m rather than 500 m. Copernicus
is cleared for commercial use. **It is already built and cached** in
`_acc_93m.tif`, and the threshold is tunable rather than fixed by someone else.

**Recommended shape: DEM network for geometry, HydroRIVERS for validation and
attributes, OSM demoted to validation only.** That is exactly the pattern
`etl_24` already uses for flood channels — and it worked there.

- **Engineering cost:** one ETL to vectorise the cached channel raster, plus an
  `etl_12` re-run. The expensive part (conditioning, 27 minutes) is already done
  and cached.
- **What it buys:** **the highest-risk layer, and the differentiator, becomes
  ODbL-free.** Exposure collapses from "our whole spatial stack" to "roads and
  what we derive from them."
- **What it costs — state this honestly:** a modelled flow line is not a mapped
  watercourse. No names. No perennial/seasonal distinction. No way to tell a
  canal from a drain from a natural river — and `etl_12` deliberately EXCLUDES
  drains today, because they are man-made. That distinction would be lost.
- **A LEGAL QUESTION HIDES IN THE THRESHOLD, and it is not a technical one.**
  A riparian reserve under EMCA attaches to an actual watercourse. Set the
  accumulation threshold too low and we buffer ephemeral gullies — claiming
  statutory reserve over land that carries none, on a parcel someone is buying.
  That error direction is worse than missing a buffer: it tells a client their
  land is unbuildable when it is not. **Choose the threshold conservatively,
  document the reasoning, and re-examine confidence 3 rather than carrying it
  over.**

> **THIS RAISES WRA'S PRIORITY (see §6).** `datasets.csv` names WRA as the
> intended primary source for rivers. A WRA river network would be
> authoritative, name-carrying, ODbL-free, and would settle the perennial /
> seasonal distinction that neither the DEM nor HydroRIVERS can. **The WRA
> request is therefore not just about flood gauge data (checklist B2) — it is
> also the clean exit from the sharpest ODbL exposure.** It was ranked last on
> the contact list; on this analysis it should not be.

### Option C — Move towers off OpenCellID
- **CA transmitter layers** exist, but every CA item has `licenseInfo` null —
  this trades a *known* share-alike condition for an *unknown* permission
  (checklist A2). **Not obviously an improvement until the CA writes back.**
- **OSM as backup** is what `datasets.csv` lists — and OSM is also share-alike.
  Not an escape route.
- **Assessment: do not engineer this yet.** It is best resolved by the CA
  email, not by code. OpenCellID is confidence 2 (crowdsourced) and the weakest
  layer we hold, so it is also the cheapest to drop entirely if the answer is
  unfavourable.

### Option D — Replace OSM roads
**Not realistic, and worth saying plainly so nobody spends a week discovering
it.** KeNHA is the listed backup but covers classified roads only. The product's
value is "distance to *any* road", including the minor and unclassified roads
that reach a rural plot. Nothing available matches 730,006 nationally mapped
segments.

**Roads stay OSM. This is the irreducible core of the legal question.**

---

## 6. Recommended sequence

1. **Decide the delivery format.** One paragraph: what does a pilot client
   receive? Product decision, no cost, gates everything else.
2. **Write to WRA — moved up from last to second.** It now serves three
   purposes at once: the authoritative river network that is the clean exit
   from the ODbL exposure, the perennial/seasonal distinction the model cannot
   supply, and the gauge data for the flood exponent (B2). One request,
   three blockers.
3. **Write to the CA.** May settle both the coverage licence (A2) and the
   OpenCellID question in one reply.
4. **Build the interim rivers swap from the cached DEM channel network**, and
   re-run `etl_12`. Do it *before* the enrichment engine binds to
   `environment.rivers`. Treat it as interim: WRA data supersedes it if it
   arrives.
5. **Then ask the lawyer one narrow question** (§7). By this point it is about
   roads and distances only — hours of advice, not days.
6. **Build the enrichment engine so the OSM-derived layers are swappable.** Do
   not hard-wire them. If the opinion comes back badly, the cost should be a
   configuration change, not a rewrite.

**Order matters here.** Steps 2 and 3 are letters that take weeks to answer, so
they should leave before the engineering starts, not after. Step 4 is work we
may partly discard if WRA replies well — but it is cheap, and it removes the
sharpest exposure in the meantime.

---

## 7. What is actually left for the lawyer

With the delivery format settled (§4), the brief is now specific:

> **Background.** Geocode Spatial Solutions Ltd operates a land intelligence
> platform for Kenya. It holds a copy of OpenStreetMap data (ODbL-1.0) in its
> own PostGIS database — 730,006 road segments, 46,529 watercourses, 14,945
> waterbodies — obtained via Geofabrik. It also holds OpenCellID cell tower
> positions (CC-BY-SA-4.0).
>
> **How the data is used.** From these and about twenty other datasets, the
> platform computes per-parcel values for client land parcels: "distance to
> nearest road: 340 m", "flood hazard class: moderate", "within riparian
> reserve: yes". These values are stored in Geocode's own database.
>
> **What is delivered to paying clients.**
> 1. A **PDF report per parcel containing text and numbers only — no maps and
>    no imagery.**
> 2. A **web platform** displaying the parcel on a rendered map, with Geocode's
>    derived layers drawn as server-rendered image overlays. Geometry is not
>    transmitted to the client browser or API.
> 3. **Outbound links to Google Maps** for directions and Street View. No
>    imagery is stored, cached or redistributed by Geocode.
>
> **What is NOT delivered:** OSM geometry, bulk data exports, or any API
> returning spatial geometry derived from OSM.
>
> **Questions.**
> 1. Is the PDF report a Produced Work under ODbL section 1.0, or a Derivative
>    Database?
> 2. Does `analytics.parcel_intelligence`, holding computed values only and no
>    OSM data, constitute a Derivative Database of OSM?
> 3. Is a server-rendered map image containing an overlay derived from OSM
>    (`environment.riparian_buffers`, buffered from OSM river centrelines) a
>    Produced Work?
> 4. **Does the analysis change for `environment.riparian_buffers`
>    specifically**, being derived *geometry* rather than a computed value —
>    even where it is only ever displayed as a rendered image?
> 5. What must the attribution say, and where must it appear, on (a) the PDF
>    and (b) the platform?
> 6. What is the practical scope of ODbL's obligation to offer the Derivative
>    Database on request — who may ask, what must be provided, and does it
>    extend to a database Geocode holds but does not distribute?
> 7. **The same analysis for OpenCellID under CC-BY-SA-4.0**, whose ShareAlike
>    attaches to Adapted Material rather than to Produced Works. Is computing
>    distance-to-nearest-tower an adaptation of the database?
> 8. If the answer to any of the above is unfavourable, does replacing the OSM
>    *rivers* with an independently derived network — leaving only OSM *roads*
>    in the stack — change the position materially?
>
> **Commercial context for question 8:** OSM roads cannot realistically be
> replaced (no alternative covers Kenya's minor road network at comparable
> density), whereas rivers can be. Knowing whether the rivers swap is
> sufficient, or whether roads alone still create the exposure, determines
> whether that engineering work is worth doing.

**Kenyan IP/technology counsel.** The OSMF community guidelines are guidance
from the licensor's foundation, not law, and OSMF does not give legal advice.

---

## 8. Imagery — basemaps, satellite, street view

A separate question with **opposite economics**, added because it is the first
thing anyone asks when they picture the product.

### You cannot pay your way out of ODbL — but you can out of OpenCellID

There is no commercial licence to buy from the OpenStreetMap Foundation. No
amount of money removes share-alike; the only routes are comply or replace.
That is why §5 is about engineering rather than budget.

**OpenCellID is different.** It is operated by Unwired Labs, who *do* sell
commercial licences. Price that before engineering a replacement — it may be
cheaper than the swap, and it closes checklist A3 outright.

### Three kinds of "view", three different answers

| View | Options | Position |
|---|---|---|
| **Basemap** (roads, labels) | Google, Mapbox, Esri — paid per use; or render our own from OSM | **A rendered map tile is the textbook Produced Work.** Self-rendering from OSM is clean AND free. Recommended. |
| **Satellite / aerial** | Sentinel-2 free at 10 m · Mapbox Satellite (Maxar Vivid, z8–18) · Maxar / Airbus / Planet direct | **10 m will not show a plot boundary.** Land work needs sub-metre. This is the only genuinely expensive line. |
| **Street view** | Google Street View Static API · Mapillary · KartaView | See the coverage warning below. |

**Indicative Google pricing (verify — these move):** Essentials SKUs including
Static Maps carry 10,000 free events per month, then roughly $2–7 per 1,000.
Pro SKUs including Dynamic Street View get 5,000 free. At 1,000 reports a month
with two map images each we sit inside the free tier; at 10,000 reports it is
tens of dollars. **Imagery is not what stops us launching.**

### The coverage reality that matters more than the price

**Google Street View barely covers rural Kenya** — Nairobi, Mombasa, and main
highways. Our market is peri-urban and rural: Ruai, Kitengela, Juja, Kajiado,
Athi River. Street View cars have not driven those access roads.

**Before budgeting for street-level imagery, open Street View on five plots in
the pilot counties.** If four have no coverage, this is not a licensing or a
pricing question — the feature does not exist for our market yet.

Mapillary is the crowdsourced alternative and is free for commercial use, but
coverage is patchy for the same reason **and it is CC-BY-SA — share-alike
again.** It is not an escape route; it is the same problem wearing a different
hat.

### One trap specific to our product

Google Maps Platform terms restrict caching, storing imagery, and printed
output. **Our deliverable is a PDF report we sell.** Embedding Google tiles in
a commercial PDF is exactly what those clauses govern — permitted under
conditions, but a specific question to check in the License Restrictions
section, never assumed. Self-rendered OSM tiles avoid it entirely and are a
Produced Work.

### Position

**Do not buy imagery yet.** It is a per-report cost that scales *with* revenue
rather than gating it, and the enrichment engine does not exist to consume it.
For the pilot: parcel boundary plus our derived layers over a self-rendered OSM
basemap. Clean, free, and it is the actual product — the intelligence, not the
picture.

---

## 9. What this memo does not cover

- **WDPA (checklist A1)** — non-commercial, a separate and simpler problem:
  replace with KWS under a commercial agreement, or obtain written clearance.
  Not a share-alike question.
- **CA coverage (A2)** — no declared licence at all. Different failure mode:
  not a restrictive licence, but the absence of one.
- **A full audit of every OSM-touching layer.** This memo covers the four that
  `sources.csv` attributes to OSM and OpenCellID. `social.public_services`,
  `transport.bus_stops` and others are P2/P3 OSM-sourced and unbuilt — they
  inherit the same answer and should be checked before they are built.
