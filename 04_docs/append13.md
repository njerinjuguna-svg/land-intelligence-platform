---

## SESSION 13 — THE PLATFORM LEFT THE LAPTOP

Two things were true at the start of this session that nobody had written
down: the project had **no version control** and **no backup**. Twelve
sessions of work existed in exactly one place, and its own deployment runbook
contained a command that could not execute.

By the end it was on GitHub, on a second disk, restorable, and serving a real
scheme to a browser anywhere in the world.

### 13.1 E10 settled — it was two columns

Rule E10 recorded that the numbered SQL files were once found SHORT of the
live database, without saying by how much. Nobody had measured it, because
reading files cannot answer the question: **files are not a schema, a schema
is what a database ends up with after running them.**

`rebuild_check.ps1` replays every file in `01_database` into an empty
database; `schema_diff.py` compares catalogues. The gap:

```
land.parcels.listed_date
land.parcels.test_expectation
```

Two columns, both hand-added, both in no migration, both on a table the
widget reads on every page load. Constraints came back 393 to 393.
`14_schema_update_v1.11.sql` closes it, and the check now reports **NO DEPLOY
BLOCKERS**.

Three things the check established as a side effect:

- **The live database has no raster extension.** Rasters are files on disk,
  catalogued by path, sampled with rasterio. A serving machine needs neither
  the extension nor a single raster file.
- **Nothing in `01_database` recreates `staging`.** Correct for a server,
  which never runs an ETL. Not correct for the workbench — see 13.3.
- **`test_expectation` is a test fixture in a production table.** Recorded
  rather than fixed: the alternative is `land.parcels` having two different
  shapes depending on which machine you are on. NULL on a serving machine by
  design.

`listed_date` still needs a decision — it is read by no code found in
`05_enrichment` or `06_delivery`. Either it is the listing date the
availability panel will want (D24), or it should be dropped deliberately.

**The tool's first verdict was wrong and worth recording.** It printed "125
DEPLOY BLOCKERS" by counting every difference, 19 of which were
`staging.*_raw` ETL landing tables that no server should have. A number that
counts everything measures nothing, and it buried the two entries that
mattered. It now separates shipped schemas from workbench ones.

### 13.2 The backup that did not exist

`backup_01_full.ps1`: whole database, custom format, **cross-disk** — the
database lives on `C:` and the project on `E:`, so the two were never one
disk failure apart, and writing the dump to `E:` is a genuine second copy.
902.7 MB, verified readable with `pg_restore --list`, retention applied only
after a proven write.

It also writes a **`.rasters.csv`** beside every dump. The rasters are files
on disk; the dump cannot contain them and never will. That CSV is the list of
what would have to be re-fetched, which is the difference between an
afternoon of recovery and a fortnight of guessing which of ninety datasets
were actually loaded.

**My bug, and the dangerous kind.** The first version queried a column called
`path`; the column is `storage_url`. The dump succeeded, the recovery list
silently did not, and the script printed DONE. **A backup that looks finished
and is not is worse than one that fails.** It now stops loudly if that file
is not written. This is rule E2 — query it, don't recall it — broken by the
person quoting it.

### 13.3 The workbench cannot be rebuilt from this project

Established by 13.1 and worth stating on its own, because it is easy to
mistake for solved once the deploy check goes green:

These files restore a **shape**. They do not restore 14,221 landmark rows,
10,357 coverage polygons, the OSM extracts, the calibrated nightlights, or
the raster corpus. If the laptop is lost, the schema survives and twelve
sessions of loaded data do not.

That is a backup problem, not a deploy problem, and it is the more urgent of
the two.

### 13.4 Version control, on the twelfth session

`DEPLOY.md` instructed `git diff --stat _live_schema_snapshot.sql` before
migrating. **There was no repository.** A documented procedure pointing at a
tool that was never there.

Consider what PROGRESS.md already records: `02_schema_update_v1.1.sql` was
once overwritten with a scratch SELECT, taking six sales statuses, two
columns, a trigger, an index and seven intelligence columns with it, and
**nobody noticed until session 7.** That is precisely the accident version
control turns into a one-command recovery. Disk failure was never the main
risk here; an overwritten file was.

First commit: 165 files, 58,258 lines. Private repo at
`github.com/njerinjuguna-svg/land-intelligence-platform`.

`.gitignore` excludes `.env`, `06_rasters`, `03_etl/data`, the venv, `*.exe`,
`06_delivery/cache`, generated PDFs and the disposable test page.
`.gitattributes` normalises line endings, because without it a file saved by
a different editor shows up as *every line changed* and the diff stops being
a diff.

**`check_secrets.py`** scans what git would actually publish — tracked files,
not the working tree — and refuses on a `.env`, a quoted credential, a live
embed key, a private key block, an AWS or Google key, or a connection string
with an inline password.

It produced one false positive on `api_key=x_api_key`, a Python keyword
argument. The fix is worth recording because the tempting one was wrong:
loosening the pattern until the noise stopped would have quietly stopped
catching `DB_PASSWORD=Nj3ri!Geocode2026` in a `.env`. **A scanner that cries
wolf gets switched off; a scanner loosened to stop crying wolf gets trusted
while catching nothing.** The rule is now per file type — in `.py`, `.js`,
`.ps1` a credential must be quoted, because an unquoted value there cannot be
a string literal; in `.env` and `.ini` unquoted is how values are written and
is still flagged.

### 13.5 The widget's database user, and a proof it is confined

`grants_landiq_api.sql` creates `landiq_api` with six SELECTs and two writes
— exactly what `api_01_embed.py` queries — then **becomes that user and tries
to break out**: update a parcel, update the intelligence, delete a parcel,
read `staging`. Each must fail, and the script raises rather than printing
quietly if one succeeds. All four confirmed.

**The catch that made the whole exercise necessary.** `api_01_embed.py` read
`03_etl/.env` unconditionally — the ETL's file, holding the postgres
superuser. `06_delivery/.env.example` carried the `landiq_api` grants in a
comment, DEPLOY.md said to copy it, and **nothing read it.** Every grant
above would have been decoration: the widget would still have connected as a
superuser, and Stage 0 would have put that superuser on the public internet.

Fixed twice over. The API prefers its own `.env` and announces which file it
used, and it **refuses to start as a superuser** — a refusal, not a warning,
because the failure mode is silent: everything works exactly as well with the
wrong credentials, right until it does not.

`\password` replaced `\prompt` after the first run echoed a password to the
screen and into terminal scrollback.

### 13.6 Stage 0 — the widget is on the public internet

Cloudflare quick tunnel from the laptop. Cost: a domain already owned. The
API binds `127.0.0.1` because the key travels in a header; `cloudflared`
connects to that loopback from the same machine, so the key never crosses a
network unencrypted and Cloudflare presents the certificate.

Verified from outside the network: `{"ok":true,"api_version":"0.1.0"}`
through Cloudflare's **Johannesburg** edge, and `v1.js` served over TLS.

QUIC dropped every few minutes; forcing `--protocol http2` helped but TCP
also timed out twice before connecting. **The packet loss is the internet
connection, not the protocol.** That is the honest, measured limit of a
laptop as a host, and it is the concrete version of the caveat in DEPLOY.md.

`start_api.cmd`, `stop_api.cmd` and `start_tunnel.cmd` sit at the project
root and are double-clickable. They call the venv's `python.exe` and a local
`cloudflared.exe` by full path, because PATH on this machine proved
unreliable in three separate ways: `psql` present but `createdb` absent,
`python` answering with a Microsoft Store stub, `cloudflared` never installed
by winget at all.

### 13.7 Satellite, Street View and the scheme map

**The browser never receives a coordinate for the pictures.** An `<img>`
pointing at Google with lat/lon in the URL would publish the parcel's
position into a page we do not control. Instead the browser asks us, the
server looks the coordinate up, fetches from Google, and streams back the
bytes.

Cached on disk per plot, so Google is billed once per plot rather than once
per page view. Street View is checked against the free metadata endpoint
first, because most Kenyan land for sale is not on a Street View road and
Google answers that with a grey "no imagery" tile rather than an error — that
panel is omitted entirely where there is no coverage.

**Scheme map** with numbered pins, no centre or zoom set so Google fits the
view to the markers. Labels are 1-9 then A-Z because a Google marker label
holds one character; past 35 plots the pins stay and the labels go, since an
unlabelled pin is honest and a wrong one is not. **The map and the cards
share an ORDER BY and neither may be reordered without the other** — that
ordering is the entire contract between pin 3 and card 3.

Diagnosing this cost an hour because the failure was silent: the widget's
placeholder looks identical whether the key is absent, in the wrong file, or
added after the API was already running. The API now states at startup
whether it can see the key, and `check_maps_key.py` asks Google directly and
prints the answer verbatim. The answer was **billing not enabled** — nothing
to do with the code.

### 13.8 The scheme index, and the flow a buyer actually wants

`/v1/scheme/embed` renders every plot as a card. One script tag, two
containers:

```html
<div id="geocode-scheme" data-scheme="OAK GROVE"></div>
<div id="geocode-plot" data-plot-ref="PLOT-457"></div>
```

Cards are buttons, not links: there is no URL on the seller's site we could
guess, and inventing one would break their page. Clicking swaps in the plot
detail with a back button; going back is instant because the index HTML is
kept rather than re-fetched. The click listener is delegated from the
container once, so it survives every re-render instead of leaking a listener.

**Every card carries the best use beside the number.** Lesson 42: KANO-01
scores 89 overall while its residential score is capped at 35 because much of
it floods, and "89 — Good" on a grid is exactly the skim-read the report
header was rewritten to prevent. A grid is nothing but skim-reading. Blocked
plots show "Not rated" and no figure.

### 13.9 B4 narrowed, deliberately, and where to reverse it

A static tile cannot pan or zoom and "Get directions" cannot work unless the
plot's coordinate reaches the browser.

The rule's PURPOSE is ODbL, and A4's exposure is
`environment.riparian_buffers` — derived geometry, unambiguously a database.
**A client's own parcel centroid is not that.** They drew it, they sent the
KMZ, they publish the location themselves, they run site visits to it every
Saturday. Withholding a plot's position from the buyers of that plot protects
nothing and breaks the one thing a land listing exists to do.

So: our derived layers never leave, unchanged and still enforced by
`assert_no_geometry()`; the pictures are still fetched server-side; the
client's own point is used only to build outbound Google Maps links. The full
reasoning sits above `_imagery_html` in `api_01_embed.py`, which is where to
reverse it if the judgement is wrong.

### 13.10 Copy changes

**Nearest mast removed** from the seller's page. A distance to a
crowd-estimated OpenCellID position at confidence 2 is a number no land buyer
can act on; D4's pairing requirement is already satisfied by the wording
"Available · in this area". The value stays in the database and the PDF.

**Slope figures removed.** The ground card printed "About {s} in 100" from a
value held in degrees — a gradient, understating 7.06° as 7 in 100 when it is
12. That was fixed with `tan()`, and then the number was removed entirely:

> "About 9 in 100" is now CORRECT and still means nothing to a buyer standing
> on a plot in Juja.

**New rule E17 — precision the reader cannot use is not rigour, it is clutter
that looks like rigour.**

**Em dashes removed** from all buyer-facing copy, rewritten rather than
swapped for hyphens, which would leave the same stilted rhythm.

### 13.11 The restore drill — performed, at last

`restore_drill.ps1` takes the newest dump, restores it into a scratch
database, and compares against live on schema **and** row counts. 902.7 MB
restored in 11 minutes:

| | live | restored |
|---|---|---|
| tables and views | 103 | 103 |
| columns | 1,119 | 1,119 |
| constraints | 393 | 393 |
| indexes | 234 | 234 |
| tables with identical row counts | | 100 of 101 |

**DEPLOY.md's "backup restore drill: never performed" is closed.**

Row counts are exact, not `reltuples` — a freshly restored table has not been
analysed, and an estimate that says "empty" about a full table is worse than
no check at all.

**The check's first verdict was wrong, in a way worth keeping.** It failed the
drill because `clients.api_keys` held 3 rows live and 1 restored — correct,
because the dump was six days old and two keys had been minted since.
Treating any shortfall as failure means the check can only ever pass for a
dump taken this instant. It now separates two different questions:

- **Did the restore work?** A table absent, or present with zero rows where
  live has many. Nothing legitimate produces that. Fails the drill.
- **What is the recovery point?** Fewer rows, all non-zero. Drift since the
  dump, expected, growing with the dump's age — and the genuinely useful
  output, because it says what restoring today would cost.

### 13.12 State at the end of session 13

- 17 parcels · enrichment 45 passed / 0 failed / 1 known gap · suitability
  62 passed / 0 failed · 3 blocked pending KWS
- Schema v1.11 · rebuild check clean · restore drill passed
- Code on GitHub, database dumped cross-disk, restore proven
- The widget serves a scheme — map, numbered plots, click-through detail,
  satellite imagery — to a browser anywhere, from a database user that cannot
  write a single row

**What is left is not technical.** Title (B5), price, and a seller willing to
paste two lines into their page.
