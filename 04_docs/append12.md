---

## SESSION 12 — THE GATE, THE DEPLOYMENT KIT, AND A VERIFIER THAT WOULD HAVE LIED

Covers the parcel-gate and deployment work carried over from session 11 and
not yet written up, plus this session's own.

### 12.1 Upload rejection became a control — `parcel_gate.py`

A client's file is not evidence. `parcel_gate.py` refuses a parcel outright
rather than enriching it with a warning attached: a warning is something a
renderer can drop, and a rejection is not.

On the Oak Grove file: **5 accepted, 8 rejected**.

Two of the rejections are worth recording because they are not data errors.
PLOT-1069 and PLOT-1070 are geometric twins. We cannot tell a drafting
duplicate from the same ground sold to two people, and choosing one would be
choosing at random, so neither loads. That is the gate doing the one thing a
warning cannot.

### 12.2 The loader's DELETE was wrong and the foreign key caught it

`03_load_client_parcels.py` reloaded a client file with
`DELETE FROM land.parcels WHERE project_name = ...`. The database refused:

```
ForeignKeyViolation: update or delete on table "parcels" violates
foreign key constraint "parcel_intelligence_parcel_id_fkey"
```

**The constraint was right and the loader was wrong.** A client's second file
is not permission to erase the enrichment, the scores, or reports already
issued to buyers. Without that constraint this run would have silently
destroyed the history of three parcels.

Supersede, never delete — the rule already used everywhere else in this build:

| case | behaviour |
|---|---|
| accepted, already present | old row superseded, new row at v+1 |
| accepted, new | inserted at v1 |
| rejected, already present | old row marked `rejected`, not deleted |
| present but absent from the file | **left alone and reported** |

That last row matters. A plot missing from a new file might be sold, or the
client might have exported one phase of several. Guessing would be inventing
a withdrawal.

Run result: 3 previously loaded parcels withdrawn (PLOT-950, PLOT-1069,
PLOT-1070), 17 parcels active.

### 12.3 Deployment kit

`Dockerfile` (widget only, non-root, healthcheck hits the database),
`docker-compose.yml` (Postgres deliberately **not** in it — a database in the
same compose file is a database somebody will run in production by accident),
`.env.example` with least-privilege grants, and `DEPLOY.md` as the runbook.
Everything still runs on one laptop.

### 12.4 Both verifiers would have lied on the first supersede run

Superseding a parcel deliberately does not touch its enrichment or its score,
so that reports already issued still resolve. The old `land.parcels` row keeps
its `parcel_id`; its `parcel_intelligence` row stays `active` against it.

Both verifiers filtered on the intelligence status alone:

```sql
WHERE i.status = 'active'      -- verify_01
WHERE s.status = 'active'      -- verify_02
```

which pulls in two kinds of ghost:

- **Withdrawn parcels** — rejected by the gate, no longer for sale, still
  carrying the enrichment computed when they were accepted. Sections B and C
  would have reported on them, and it would have read as the gate failing.
- **Stale twins** — an accepted re-load creates a new `parcel_id` at v+1 with
  fresh enrichment while v1's enrichment is still active. Both share a
  `parcel_ref`, and the results dict is keyed on `parcel_ref`, so one silently
  overwrote the other. A verifier grading last week's answers and printing
  them green.

The scorer and the delivery API already filtered on both. The two verifiers
were the only readers that did not.

Fixed, and a **control** added in both: more than one active row per
`parcel_ref` now aborts the run and names the `parcel_id`s, rather than
grading an arbitrary half of the evidence.

**E14 restated, because this is the clearest instance of it so far: the check
was the thing that was broken.**

### 12.5 `show_01_parcel.py` — E14 finally has a tool

"Read one complete parcel per session" was a rule with nothing behind it,
which makes it a reminder. `show_01_parcel.py` prints every field of one
active parcel with its source and confidence attached, NULLs shown as NULL
with the radius that was searched, geometry withheld. It asserts nothing and
can fail nothing. Reading it is the check.

It paid for itself on its first run — see 12.6.

### 12.6 What reading PLOT-365 found

**The ground card understated slope by nearly half.** `slope_mean_pct` holds
degrees; the column name predates the layer. Two readers in
`report_content.py`: one printed `{slope}°` and was right, the other printed
*"About {slope} in 100"* — a gradient, which is a different quantity.

| stored | printed | actually |
|---|---|---|
| 5.07° Kericho | 5 in 100 | **9 in 100** |
| 7.06° Aberdares | 7 in 100 | **12 in 100** |
| 12° | 12 in 100 | **21 in 100** |

The steepest ground we hold was described to a buyer as a little over half as
steep as it is, on the one card that tells him what groundwork will cost.
Nothing could have caught it: the stored value is correct, the band is
correct, only the sentence was wrong. Now converted with `tan()` once, at the
point of printing.

**Clinic and hospital printed as two lines with the same number.** Health
facilities sit at the ward centroid (C8, confidence 2), so both collapse onto
one point wherever a ward holds one facility. Measured: PLOT-365 1391/1391,
Kericho 834/834, Kitengela 1465/1465, Ruai 2015/2015 — four of the five that
report both. The widget stacked them, and a buyer reads two lines as two
places. Now one row, **"Health facility"**, named for what we can stand
behind, wherever the distances are equal; left as a pair where they differ
(Karen 3088/2489, Lodwar 15550/10181, Tana Delta 23826/7939).

**Two things checked and found already correct**, recorded so they are not
re-investigated: `nearest_airport_name` still says *GSU Airstrip* on the Oak
Grove plots but never reaches a buyer — `dist_airport_m` is deliberately
excluded from `LANDMARK_FIELDS`. And `has_4g` renders as *"4G data ·
Available · in this area"*, which satisfies D4.

### 12.7 C16 became a column — schema v1.10

`black_cotton_risk = 'none'` on ground the check cannot clear. The rule saying
so lived as prose in `field_sources`, and what actually enforced it was a bare
`slope < 3.5` written **twice in `report_content.py` and not once in the
engine**.

`black_cotton_inconclusive` is now set by the engine and read by both
renderers. It **fails toward inconclusive**: unknown slope counts as flat, and
no soil data at all also sets it. If we cannot see the landform we certainly
cannot clear the soil.

It fires on Karen, which is Nitisols and genuinely stable. That is intended.
No signal this database holds separates Karen from the Athi-Kapiti plains —
both discriminators point the wrong way, measured. On flat ground the honest
statement is that the check does not settle it. Over-flagging costs a seller
one line of caution; under-flagging puts a house on ground that moves.

Geography is deliberately not part of the test: "peri-urban Nairobi" has no
boundary in this database and inventing one would be a claim we cannot
source (D20).

This does **not** close C16. It makes C16 impossible to render as an absence
of a gap.

### 12.8 A NULL now says which kind of NULL it is

`dist_water_point_m` NULL carried `search_radius_m: 25000` and was honest.
`dist_power_line_m` NULL carried nothing at all. Nothing in the row separated
*"we searched 25 km and found none"* from *"no such layer exists here"*.

Eighteen fields now write a `not_sourced` note with the reason and the
checklist item where one exists — A5 Kenya Power, B7 WASREB, B6 zoning — and
"no source identified" where none does. These are claims about **our
coverage**, not about the ground, and must never be rendered as an absence on
the parcel.

Consequence worth stating: until this, a report could never honestly say "no
power line within X km", and an acquirer asking what we actually hold had no
answer in the data.

### 12.9 New verifier section H — controls still firing

A control nobody checks becomes a reminder the first time someone edits the
layer it lives in. Section H tests that the safeguards are switched on, not
that the ground is right:

- C16 inconclusive flag set on every parcel it must cover
- every unsourced field states why, on every parcel

### 12.10 B1 recurred, and this time it is the CA's fault — SETTLED

`coverage_4g_pct_safaricom` and `coverage_4g_pct_telkom` return values
identical to fourteen decimal places on every parcel where both are present
(8 of 8; 0 differ). A previous session had already measured that all 10,357
Safaricom polygons `ST_Equals` a Telkom polygon, and left one question open:
**did the CA publish one dataset twice, or did etl_25 resolve both slots to
the same service?** The engine wrote down the query that would settle it.

That query has now been run (`check_01_coverage_operators.py`):

| operator | tech | source_layer | polygons | km² |
|---|---|---|---|---|
| all | 2g | airtel_safaricom_telkom_2G1 | 9,274 | 608,714.5 |
| Safaricom | 4g | safaricom_4G_2022 | 10,357 | 583,962.3 |
| Telkom | 4g | Telkom_4G | 10,357 | 583,962.3 |

**Two separately named CA files, identical polygon count, identical total
area.** Our loader did not collapse them — the CA supplied the same
measurements twice under two operator filenames. B1 recurred at the source.

Consequences:

- The `DO_NOT SHIP PER-OPERATOR 4G` instruction is now **permanent**, not
  provisional. The columns are marked `not_sourced` with that reason, so the
  refusal is in the data rather than in a comment.
- The open question is the CA's to answer and belongs in the **A2 letter**:
  *which operator do the 4G measurements describe?* Not "please confirm the
  licence" alone — this is a second, separate question to the same body.
- Note also that no `4g/all` layer exists in the table, though field_sources
  claims one with its own vintage. `coverage_4g_pct` — the headline figure the
  widget renders — needs its provenance re-checked against this inventory
  before Phase 2. Not done.

### 12.11 The unexplained-NULL check was itself unexplained-NULL-shaped

The check added in 12.9 passed on its first run while `temp_mean_c` and
`solar_kwh_m2_day` sat NULL with nothing attached — because they were not on
the list of fields it knew to look for. **A check that only checks what its
author remembered is the same failure as a rule that only lives in a
comment.**

Inverted: it now scans every NULL column on every parcel and demands each be
explained. A column added next session fails loudly until somebody decides
what its NULL means.

That inversion exposed the real gap. There are two honest kinds of NULL —
*we hold no layer* and *we searched a stated radius and found none* — and
**only the first is implemented.** Every layer writes `src[...]` inside its
hit branch, so a genuine "nothing within 25 km" writes nothing at all,
despite the `SEARCH_M` docstring stating that it does. Thirty-one columns are
listed in the verifier as named debt rather than quietly passing.

Consequence, unchanged from 12.8 and now precise: a report cannot say "no
school within 25 km", only leave a blank. The widget drops NULLs so nothing
false ships — this is a Phase 2 and PDF-report gap, not a widget blocker, and
it is **deliberately deferred**.

### 12.11 State after this session

- 17 parcels active — 12 landmark + 5 Oak Grove
- enrichment verification: 43 passed, 0 failed, 1 known gap (Athi Plains, C16)
- suitability verification: 62 passed, 0 failed
- 3 blocked and unratable pending KWS data: Aberdares, Kakamega, Tana Delta
- schema at v1.10 (`13_schema_update_v1.10.sql`)
- Oak Grove still scores 94–98 residential across all five plots. The model
  does not discriminate within one scheme, which is the comparison a buyer in
  that scheme is actually making. Unresolved.
