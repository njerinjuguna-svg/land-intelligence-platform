# Deploying the LandIQ widget

**What gets deployed is the widget only** — `api_01_embed.py`,
`report_content.py`, `v1.js`. The ETL pipelines, the raster catalogue, the
enrichment engine and the scorer stay on a machine you control and run against
the same database.

That split is the security boundary, not tidiness. The widget is the one
component reachable from the public internet; it should be able to read a
handful of tables and write its own usage rows, and nothing else. Enrichment
needs to rewrite every parcel in the country. Those two things must not share
an image or a database user.

---

## Before anything is copied anywhere

**E10 is settled. It was two columns.**

The rule was blocking for a reason that had already happened once:
`02_schema_update_v1.1.sql` had been overwritten with a scratch SELECT,
taking six sales statuses, two columns, a trigger, an index and seven
intelligence columns with it. Session 7 rebuilt those from the live database
but only checked the three tables the trail led to, so nobody knew what else
was missing.

Now measured, not estimated. `rebuild_check.ps1` replays every file in
`01_database` into an empty database and compares catalogues against the live
one:

```powershell
cd "E:\Land Intelligence Platform Geocode\Land Intelligence Platform\01_database"
powershell -ExecutionPolicy Bypass -File .\rebuild_check.ps1
```

The gap was `land.parcels.listed_date` and `land.parcels.test_expectation` —
both added by hand, both in no migration, both on a table the widget reads on
every page load. `14_schema_update_v1.11.sql` closes it. Constraints came back
393 to 393. **A serving database built from these files is now exact**, and
re-running the check is how that stays true after any schema change.

Two things the check established that change what has to be copied:

- **The live database has no raster extension.** Rasters are files on disk,
  catalogued by path and sampled with rasterio. Nothing raster is in Postgres,
  so a serving machine needs neither the extension nor a single raster file.
- **Nothing in `01_database` recreates the `staging` schema.** Correct for a
  server, which never runs an ETL. Not correct for the workbench: these files
  restore a shape, not twelve sessions of loaded data. That is a backup
  problem, and it is more urgent than this document —
  `01_database\backup_01_full.ps1`.

---

## Stage 0 — before there is a server at all

**Use this until a client is paying.** It costs the price of a domain, which
is already owned. Everything below it stays true and waits.

The widget needs a public HTTPS URL. It does not need a machine in a data
centre. `cloudflared` provides a stable public hostname that tunnels to a
service on this laptop — no port forwarding, no static IP, TLS terminated by
Cloudflare.

```powershell
# one-off
winget install --id Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create landiq
cloudflared tunnel route dns landiq embed.geocode.co.ke

# each time
uvicorn api_01_embed:app --port 8000
cloudflared tunnel run --url http://127.0.0.1:8000 landiq
```

This preserves the property step 4 exists to protect. The API binds
`127.0.0.1` because the key travels in a header and port 8000 is plain HTTP;
`cloudflared` connects to that loopback address from the same machine, so the
key never crosses a network unencrypted. Cloudflare presents the certificate.
No Caddy, no nginx, nothing else listening.

**The one thing that is not optional.** Right now the API reads `03_etl\.env`
and connects as `postgres` — the enrichment superuser, which can rewrite every
parcel in the country. On this laptop, behind no network, that has been
harmless. **The moment a tunnel exists, it is a superuser connection behind an
internet-facing service with deliberately permissive CORS.** Do step 2 below
*before* the first `cloudflared tunnel run`, and give the widget its own `.env`
pointing at `landiq_api`. This is the only step that moves from "later" to
"now" because of Stage 0, and it is not negotiable.

**What Stage 0 buys beyond being free.** Cloudflare's free tier does rate
limiting at the edge. The gap named at the bottom of this document — a public
key with nothing stopping a million calls — is largely answerable with a
dashboard rule rather than code, for as long as Stage 0 lasts. It does not
remove the need to build it properly against `clients.subscriptions`; it does
mean the first client is not exposed while that gets written.

**What Stage 0 is not.** The laptop must be on, awake and online for the
client's page to render. Kenyan grid and home broadband make that a real
availability problem. This is honest for demos and one friendly pilot; it is
not honest under a signed uptime commitment. When a client is paying, move to
the sections below — one Nairobi VPS is the whole of it.

---

## 1. A database with backups

Postgres 16 with PostGIS. The database is the asset — thirty ETL runs and
every parcel a client has uploaded. Restore-tested, not just backed up.

**On Stage 0 this is the laptop's existing database**, and the backup is
`01_database\backup_01_full.ps1` to an external drive. Weekly minimum, after
any ETL run is better.

**On a server it is only four tables.** The widget's API reads `land.parcels`,
`analytics.parcel_intelligence`, `analytics.suitability_scores` and the
`clients` tables. Every reference layer — roads, rivers, places, coverage,
towers, protected areas — and every raster is read at *enrichment* time only,
on the workbench. A serving machine needs none of it, which is why a VPS at
KES 3,500/month is not undersized for this.

That split also keeps the licence exposure off the server. The high-exposure
item under A4 is `environment.riparian_buffers`, because it is *derived
geometry* and therefore unambiguously a database; under this split it never
leaves the laptop. The server holds clients' own parcel geometry and computed
values. Worth a lawyer's confirmation before it is relied on in an acquisition
conversation, but it is a reason to publish rather than to lift the database
wholesale.

There is no managed Postgres in Kenya. Nearest managed is Johannesburg or Cape
Town, which adds latency for every Kenyan buyer and moves the data out of the
country for no benefit. Prefer a Nairobi VPS with your own Postgres.

## 2. A user that can only do what the widget does

The widget must not connect as `postgres`. Create `landiq_api` with the grants
listed in `.env.example` — SELECT on six tables, INSERT on the two log tables.
If the widget is ever exploited, that is the whole blast radius.

## 3. The image

```bash
cp .env.example .env          # fill in DB_HOST and the landiq_api password
docker compose build
docker compose up -d
docker compose logs -f api    # expect "Application startup complete"
curl -fsS http://127.0.0.1:8000/v1/health
```

`/v1/health` touches the database, so a 200 means the container can actually
serve a plot rather than merely that it started.

## 4. TLS and a domain

Put Caddy or nginx in front on `embed.geocode.co.ke`. The API binds
`127.0.0.1` deliberately — port 8000 is plain HTTP and **the API key travels
in a header**, so anything that reaches it unencrypted is a key on the wire in
clear text.

```
embed.geocode.co.ke {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy gets a certificate automatically. Confirm the loader is served over
HTTPS before giving a client the snippet:

```bash
curl -fsSI https://embed.geocode.co.ke/v1.js
```

## 5. What a client pastes

```html
<div id="geocode-plot" data-plot-ref="PLOT-457"></div>
<script src="https://embed.geocode.co.ke/v1.js" data-key="pk_live_..."></script>
```

The loader derives the API origin from its own `src`, so staging, production
and a client's reverse proxy all work with no change to those two lines.

---

## Not built yet, and honest about it

**Rate limiting.** `clients.subscriptions` and `clients.api_usage` exist and
the API already writes usage rows. Nothing reads them, and nothing stops a
client — or somebody who copied their key out of their page source — calling a
million times. The key is public by nature in every embed widget; **the limit
is what makes that acceptable**, and it is the last real gap before this is
sellable. Do it before the second client, not the second incident.

**Key rotation.** Keys are revocable (`clients.api_keys.revoked`) but there is
no way for a client to rotate one without us minting it by hand. Fine for the
first client. Not fine at ten.

**Backup restore drill.** `backup_01_full.ps1` now verifies that each archive
is readable (`pg_restore --list` fails on a truncated file), which is more than
existed before and still less than a drill. **Nobody has restored one into a
working database.** A backup nobody has restored is a belief. The scratch
database from `rebuild_check.ps1` is sitting there and is exactly the right
place to try it — that is the drill, and it costs twenty minutes.

---

## First-client checklist

1. `parcel_ref` mapping agreed with their developer — their "Plot 457" to our
   `parcel_ref`. Serving the wrong plot's analysis to a buyer is the worst
   failure this product has.
2. **Who updates `listing_status`, through what, and how often.** The
   availability panel is the strongest thing on the page and it goes stale
   silently. This is the handshake that never stops — put it in the agreement.
3. Their parcels through `parcel_gate.py` before enrichment. Expect
   rejections: Oak Grove had two bad parcels in eight, and that was a careful
   file.
4. Key minted, `is_active` true on their company row, snippet tested on their
   staging domain.
