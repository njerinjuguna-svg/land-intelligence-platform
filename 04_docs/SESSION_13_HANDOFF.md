# LAND INTELLIGENCE PLATFORM — SESSION 13 HANDOFF

Geocode Spatial Solutions Ltd · Kenya · as at 27 August 2026

---

## 1. HOW TO WORK IN THIS PROJECT

Njeri runs every command. You edit files; she executes. There is no database
access from your side.

Give the whole PowerShell block each time. **Give it as single lines, or as a
script file.** Multi-line blocks with `@(...)` arrays and `foreach` crashed
PSReadLine twice this session and mangled a paste a third time. If something
takes more than two lines, write it as a `.ps1` and hand over one line that
runs it.

**Do not assume anything is on PATH.** Measured on this machine: `psql` works
but `createdb` does not; `python` hits the Microsoft Store stub outside the
venv; `cloudflared` was never installed by winget. Call tools by full path,
or resolve them at runtime.

Do not work in stages or ask "shall I continue?". If a direction is agreed, do
all of it in one turn.

PROGRESS.md and PRE_LAUNCH_CHECKLIST.md are the durable record. Ask before
appending. Deliver additions as separate `appendNN.md` files she pastes in.

Files reach her disk via the desktop bridge (`device_commit_files`).

**Before believing a failure, check the test.** Still earning its place: this
session a "missing" `/v1/health` route was a truncated grep, and a suspicious
JSON splice was a console dropping characters.

**No em dashes in buyer-facing copy.** Removed from `report_content.py` and
`api_01_embed.py` this session. Rewrite the sentence rather than substituting
a hyphen.

---

## 2. WHAT THE PRODUCT IS — TWO PHASES

Unchanged from session 12. Phase 1 is enrichment of a land-seller's own
parcels, shown as a widget on their site: what the land IS, no verdicts, no
refusals. Phase 2 is the Geocode marketplace, where the suitability verdict,
flood warning, protected-area refusal and "before you pay" checklist live.

The rule that does not move: **never print a claim we cannot source.**

---

## 3. WHERE EVERYTHING IS

Root: `E:\Land Intelligence Platform Geocode\Land Intelligence Platform`
Windows · PostgreSQL 16 + PostGIS · database `land_intelligence_kenya` ·
venv at `03_etl\venv`

**The project is now under git.** Private repo:
`https://github.com/njerinjuguna-svg/land-intelligence-platform`
`.gitignore` excludes `.env`, `06_rasters`, `03_etl/data`, the venv, `*.exe`,
`06_delivery/cache`, generated PDFs and the disposable test page.

**Two disks, two exposures.** The database lives on `C:` (default Postgres
data directory); the project on `E:`. Losing either loses a different half.

New at the root, double-clickable:

| file | what it does |
|---|---|
| `start_api.cmd` | starts the widget API |
| `stop_api.cmd` | stops whatever holds port 8000 |
| `start_tunnel.cmd` | public HTTPS URL via Cloudflare |

New elsewhere this session:

- `01_database\backup_01_full.ps1` — full dump + the raster shopping list
- `01_database\rebuild_check.ps1` + `schema_diff.py` — E10, answerable
- `01_database\14_schema_update_v1.11.sql` — the two missing columns
- `01_database\grants_landiq_api.sql` — the widget's DB user, with proof
- `05_enrichment\show_01_parcel.py` — E14's missing tool
- `05_enrichment\check_01_coverage_operators.py`
- `06_delivery\mint_key.py`, `check_maps_key.py`, `demo_page.html`
- `check_secrets.py` (root) — run before every push

---

## 4. CURRENT STATE

- **17 parcels.** Enrichment 45 passed / 0 failed / 1 known gap. Suitability
  62 passed / 0 failed. 3 blocked pending KWS.
- **Schema v1.11.** `rebuild_check.ps1` reports NO DEPLOY BLOCKERS.
- **Backed up.** 902.7 MB verified dump on `E:\geocode-backups`, plus a
  26-line raster catalogue CSV. Code on GitHub.
- **The widget works end to end on the public internet.** Verified from
  outside the network: a page loaded `v1.js` over TLS through Cloudflare's
  Johannesburg edge, fetched rendered HTML with a hashed key, from a database
  user that cannot write.

---

## 5. WHAT HAPPENED IN THIS SESSION (13)

### 5.1 Both verifiers were reading ghosts

Superseding a parcel deliberately leaves its enrichment active, so reports
already issued still resolve. Both verifiers filtered on `i.status` /
`s.status` alone and not on `p.status`, so they were grading withdrawn
parcels, and for re-loaded plots were keeping whichever version the sort
returned last. Fixed, plus a control that aborts on more than one active row
per `parcel_ref`.

**The live data proves it:** 17 active parcels, **25** active intelligence
rows. Five superseded Oak Grove v1 rows plus three withdrawn.

### 5.2 The ground card was understating slope by nearly half

`slope_mean_pct` holds degrees. The card printed "About {s} in 100", a
gradient. 7.06° was described as 7 in 100 when it is 12. Fixed with `tan()`,
then **the number was removed entirely** — correct and meaningless is still
meaningless. Same for the degrees figure in the build answer.

### 5.3 C16 became a column (v1.10)

`black_cotton_inconclusive`, set by the engine, **failing toward
inconclusive**. It fires on Karen too, which is intended: no signal we hold
separates Karen from the Athi-Kapiti plains. The 3.5° threshold previously
lived twice in `report_content.py` and nowhere in the engine.

### 5.4 A NULL now says which kind of NULL it is

Eighteen fields write a `not_sourced` note with the reason and checklist item.
**Debt named, not closed:** the second honest NULL — "searched a stated radius
and found none" — is still not implemented, because every layer writes its
source note inside the hit branch. 31 columns are listed as debt in
`verify_01`. A report still cannot say "no school within 25 km".

### 5.5 B1 recurred, and it is the CA's fault — settled

`safaricom_4G_2022` and `Telkom_4G` are two separately named CA files with
identical polygon counts (10,357) and identical area (583,962.3 km²). Our
loader did not collapse them; the CA published the same measurements twice.
**Per-operator 4G is permanently unshippable** until the CA says which
operator the measurements describe. That is a second question for the A2
letter.

### 5.6 E10 settled: it was two columns

`rebuild_check.ps1` replays every numbered file into a scratch database and
compares catalogues. The gap was `land.parcels.listed_date` and
`land.parcels.test_expectation` — both hand-added, both on a table the widget
reads. Constraints 393 to 393. Also established: **the live database has no
raster extension**, and **nothing in `01_database` recreates `staging`.**

### 5.7 The backup that did not exist

Cross-disk dump (C: to E:), verified readable with `pg_restore --list`,
retention after a proven write. Ships a `.rasters.csv` because the rasters
are files on disk and the dump cannot contain them.

**My bug, worth remembering:** the first version queried `path` when the
column is `storage_url`. The dump succeeded, the recovery list silently did
not, and it printed DONE. It now fails loudly.

### 5.8 Version control, on the twelfth session

No repository existed. `DEPLOY.md` instructed `git diff --stat` — a
documented procedure that could not execute. First commit: 165 files, 58,258
lines. `check_secrets.py` scans what git would actually publish.

### 5.9 The widget's database user, and a proof

`grants_landiq_api.sql` creates `landiq_api` with six SELECTs and two writes,
then **becomes that user and tries to break out** — update a parcel, update
the intelligence, delete a parcel, read staging. All four must fail.

**The catch that made it matter:** `api_01_embed.py` read `03_etl/.env`
unconditionally — the superuser's file. `06_delivery/.env.example` carried the
grants and nothing read it. Without that fix the tunnel would have put a
superuser on the internet. The API now prefers its own `.env` and **refuses to
start as a superuser**.

### 5.10 Stage 0 is live

Cloudflare quick tunnel, `--protocol http2` after QUIC dropped repeatedly.
Note: TCP timed out twice too, so the packet loss is the **internet
connection**, not the protocol. That is the honest limit of a laptop as a
host.

### 5.11 Satellite, Street View and the scheme map

Server-proxied: the browser asks us, we fetch from Google, we stream bytes.
Cached per plot so Google is billed once, not once per page view. Street View
checked against the free metadata endpoint first, because most Kenyan land is
not on a Street View road and Google answers that with a grey tile.

**Scheme map** with numbered pins (1-9 then A-Z, one character is all a
Google marker label holds), and the cards carry the matching numbers. Map and
cards share an ORDER BY; neither may be reordered without the other.

### 5.12 The index, and the flow

`/v1/scheme/embed` renders every plot as a card. One script tag, two
containers:

```html
<div id="geocode-scheme" data-scheme="OAK GROVE"></div>
<div id="geocode-plot" data-plot-ref="PLOT-457"></div>
```

Clicking a card swaps in that plot's detail with a back button; going back is
instant because the index HTML is kept. **Every card shows the best use next
to the number** — lesson 42, because a grid is nothing but skim-reading.

### 5.13 B4 narrowed, deliberately

The client's own parcel centroid now reaches the browser, but only to build
outbound Google Maps links (open the map, get directions). **Our OSM-derived
layers still never leave**, unchanged and still enforced by
`assert_no_geometry()`. The reasoning is written in full above
`_imagery_html`. If that judgement is wrong, that is where to reverse it.

---

## 6. STANDING RULES WORTH CARRYING

- **E2 — query it, don't recall it.** Broken twice this session by me:
  `path` vs `storage_url`, and checking column NAMES without their TYPES
  (`scopes` is `text[]`).
- **E14 — a green verification does not mean the answers are right.** Read
  one complete parcel per session: `python show_01_parcel.py`.
- **E16 (new) — a check that only checks what its author remembered is not a
  check.** The unexplained-NULL check passed while two fields sat unexplained,
  because they were not on its list. Inverted to scan everything.
- **E17 (new) — precision the reader cannot use is not rigour.** "About 9 in
  100" was correct and meaningless.
- **E15 — rename `transport.bus_stops`.** Still holds every transport stop.
- A rule you have to remember is a reminder. A rule the code cannot proceed
  without is a control.

---

## 7. WHAT IS OPEN

**Legal / data** — A1 KWS (Aberdares, Kakamega, Tana Delta unratable),
A2 CA (now TWO questions: written licence, and operator attribution),
A3 OpenCellID commercial licence, A5 Kenya Power, B5 **title — Njeri's
decision, unresolved**, B6 county zoning, B7 WASREB.

**Njeri is visiting these agencies in person.** The five drafted letters in
`04_docs/correspondence/` are the content, not the delivery method.

**Not built** — a server; rate limiting (Cloudflare's free edge rules cover
Stage 0 but `clients.subscriptions` is still unread); billing; key rotation;
"Book a site visit" destination (`clients.branding`); the marketplace.

**Known and unresolved** — Oak Grove plots all score 94–98 residential; the
model does not discriminate within one scheme, which is the comparison a
buyer in that scheme is making. Athi Plains black cotton (C16). The
searched-found-nothing NULL debt (5.4). `coverage_4g_pct`'s provenance: no
`4g/all` layer exists in the table though field_sources claims one.

**Never restore-tested.** `backup_01_full.ps1` verifies an archive is
readable; nobody has restored one into a working database. The scratch
database from `rebuild_check.ps1` is the right place. Twenty minutes.

---

## 8. IMMEDIATE NEXT ACTION

Nothing is broken. Pick from:

1. **The restore drill.** Twenty minutes, closes the last honest gap in the
   backup story.
2. **Title (B5) and price.** Both block the client agreement. Neither is a
   coding task and both have blocked everything else for three sessions.
3. **`clients.branding`** — the seller's logo, colours, and where "Book a
   site visit" points. Small, and it is what makes the widget look like
   *their* page rather than ours.
4. **Rate limiting against `clients.subscriptions`** — the last real gap
   before a second client.

## 9. PROGRESS.md IS BEHIND

`append11.md`, `append11b.md` and `append12.md` are written and **not yet
pasted in**. `append12.md` covers the parcel gate, the deployment kit, the
supersede fix, the verifier defect and the coverage finding. Everything from
section 5.6 onward in this document still needs an `append13.md`.
