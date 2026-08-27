
---

## Session 11 (2026-08-24) — DELIVERY HARDENING, LANDMARKS, AND ONE MISTAKE IN FOUR COSTUMES

**43 checks passing, 0 failed, 1 known gap.** Six new source tables holding
14,221 rows, twelve new intelligence columns, two migrations, twelve new
assertions, and a buyer-facing page built on nothing but measured values.

Njeri ran every command.

The session divides cleanly in two. The morning was spent reading what Phase 5
actually produced — four PDFs and one API response — and fixing what reading
them exposed. The afternoon built the landmarks layer. **Both halves taught the
same thing**, which is why Lesson 48 is the one worth keeping if the rest is
forgotten.

### WHAT READING FOUR PDFs FOUND THAT VERIFICATION DID NOT

`verify_01` was green. `verify_02` was green. Twenty PDFs generated without
error. Then four of them were read end to end, and every one carried a defect
no assertion was ever going to catch, because each was a defect of MEANING
rather than of value.

**PLOT-950 contradicted itself on a single page.** A red panel at the top said

> Every score would be computed on ground we are not confident is the plot.

and four lines below it, the report asserted

> On the plot itself: river.

Both statements were generated correctly. The second is the more dangerous, and
the reason is worth stating precisely: **a distance survives a bad boundary and
containment does not.** A hospital 1.6 km from roughly-there is 1.6 km from
actually-there. But "a river crosses this land" is a claim made ENTIRELY out of
the boundary — the one thing the panel above had just disowned. It is also, of
the two, the claim a buyer would act on. Containment now downgrades to
proximity when the boundary is untrusted, the distance list carries the caveat,
and a MEASURED acreage is suppressed on the same reasoning while a
CLIENT-STATED one survives, because that is their claim and we are only
repeating it.

**Three smaller ones, same reading.** "98 / 100 — Good best suited to
residential use" had no punctuation between the band and the clause, because
two renderers were each composing half a sentence; neither writes sentences
now. "On the plot itself: main road. Not nearby — on the land." read as a
fragment somebody forgot to finish. And Athi Plains led its **What is nearby**
list with

    River          2 min walk      161 m away

ranked first because the list sorts by distance and 161 m is the smallest
number on the page. Under that heading it reads as a selling point. It is a
riparian setback and a flood path. Distance alone cannot tell an amenity from a
constraint, so the kind is now declared rather than inferred, and features sort
last under their own note.

**And the plot size was missing from all twenty reports** — see Lesson 49,
which is about how I nearly explained that wrongly.

### LESSON 45: THE CAP HAD TO SURVIVE THE SKIM

TEST-KANO-01 printed, across the top of its report:

> **89 / 100 — Good**   best suited to agricultural use

on a plot the model had **capped at 35 for residential** because a large part of
it sits in the highest flood categories. Everything needed to see that was on
the page. The flood question said "Yes, it floods". The note said the overall
figure is the best of the four. Lesson 42 had already established that a cap is
a different KIND of statement from a low score.

None of it helps. **The overwhelming majority of people opening a report on a
plot intend to build on it**, they read the big number first, and "89 / 100 —
Good" is what they carry away from a page whose own model says do not build
here. A distinction that exists only in the database is not a distinction the
product has.

Capped uses are now named beside the headline. The cap's own reason string is
NOT reproduced — those are written for the breakdown and read like model
internals — because the four questions below already say why in plain words.

**And the first version of that fix was itself wrong**, which is the more
useful half. It picked the capped use with the LOWEST score. On Kano three uses
were capped, so it printed:

> We do not recommend this plot for **holding as an investment** — it scores 32
> out of 100 for that.

True, and useless. Kano floods. The sentence a buyer needed was about BUILDING,
and sorting by number buried it behind a market opinion nobody opened the
report for. **"Lowest number" and "worst consequence" are different questions**,
and the paragraph promised the second while the code answered the first.
Selection is now by consequence in a fixed order — residential, commercial,
agricultural — and investment never leads it. A weak investment score costs
money slowly; a house on a floodplain is a different category of wrong.

### LESSON 46: ONE MESSAGE OUTWARD, EVERY REASON IN THE LOG

The embed API refused a key that was correct. The response said:

> Unknown, revoked or expired API key.

The key hashed correctly, was not revoked, had not expired, and owned all twenty
parcels. **All three things the message named were false.** The company behind
it had `is_active = false`, and four separate conditions had been folded into
one `WHERE` clause, so a failure of any of them produced a message naming the
other three. Finding out which took a seven-column diagnostic query.

The response is right to be vague. Telling an unauthenticated caller "that key
is real but the account is suspended" confirms which keys exist — a probing
oracle. **The LOG has no reason to be vague, and that is the whole fix.** The
checks are made separately and named, the `HTTPException` body is byte-identical
in every case, and the reason prints to the server window. A client's developer
on the phone would otherwise spend an afternoon regenerating a key that was
never the problem.

> Hide the difference from the caller. Never hide it from yourself.

### LESSON 47: THE BUYER PAGE TOOK THREE PASSES, AND THE CLIENT WAS RIGHT TWICE

Session 10 had already rejected one mockup as too technical. This session the
same thing happened twice more, and both corrections were the client's.

The first pass built an honest analysis page with a **What we do not check**
section — title, zoning, electricity, valuation — six items with who to ask for
each. It is the most defensible page in the build. Njeri's response:

> all this details cannot go to the client side... that should be in our later
> stage after getting clients

**She is right, and the distinction is a product one, not a moral one.** The
limits are a SALES asset in the conversation with the seller, where they prove
we know what we do not know. On a listing page in front of a buyer they are a
wall of disclaimers between that person and the plot. Same content, opposite
effect, decided entirely by who is reading. The limits now live in the seller
pitch and the PDF; the listing page carries one sentence.

Her spec for what a buyer actually wants, verbatim: satellite image and street
view, directions, soil type, rainfall in simple terms not figures, distances to
amenities, famous landmarks nearby, **and the status of surrounding plots**.

Three findings came out of building it:

**The satellite image was never actually blocked.** B4 kept imagery out of the
PDF because Google's terms are strict about tiles inside a document we sell. A
web page is a different licence — the Maps JavaScript API and Street View
embeds are exactly that product. And drawing the plot boundary over the tile is
clean, because that boundary is **the seller's own survey data**, not ours and
not OSM's. It conveys nothing. B4 was read as "no imagery" when what it decided
was "no imagery in the PDF".

**The availability panel is the strongest sales feature on the page and we
cannot fill it.** All eight OAK GROVE plots read `listing_status = 'available'`
and every `price_kes` is NULL. "3 of 7 sold" was my placeholder and the data
says otherwise. This is not a code gap — it is a **second onboarding handshake**,
and unlike the `parcel_ref` mapping it has to keep happening after go-live.
Logged as D24.

**Four columns of imagined precision came off the page.** No invented price, no
fabricated sold/deposit statuses, and `dist_airport_m` removed entirely — see
below.

### LESSON 48: THE QUERY WAS RIGHT AND THE ANSWER WAS STILL WRONG

**This is the session's lesson.** Four defects, four different layers, one
shape. In every case the SQL was correct, the join was correct, the distance was
correct to the metre — and the answer was wrong, because the column was
answering the question NEXT TO the one a buyer was asking.

**1. `Shekiko Airport (disused)`.** TEST-TANADELTA-01's nearest airport, 7.5 km,
correctly measured. A disused airstrip is not somewhere anyone can fly into, and
a listing page offering it as "your nearest airport" is a false promise made in
the source's own words. Geometry cannot tell a live facility from a dead one.
**OSM said so in the NAME**, so a name filter can find it — deliberately narrow,
matching those words in parentheses or as whole words, so a genuine "Former
Presidents Road" survives. Tana Delta moved to Witu Airstrip at 19.9 km: 12 km
worse, and true.

**2. `GSU Airstrip`, on all eight OAK GROVE plots, 6.9 km.** Fully operational.
A General Service Unit airstrip no land buyer will ever fly from. **Nothing in
the name, the geometry or the tags says so** — a filter could never find this
one, because the defect is not in the data at all. It is in the question:
*nearest airport* and *where would I fly from* are the same question only where
every airport takes passengers.

The repair was NOT to exclude airstrips. `domestic` is inferred by name — an
airport is `international` if it says so and `domestic` otherwise — so
`domestic` is a DEFAULT, not a finding, and it is full of bush strips
indistinguishable from GSU. Filtering on it would trade a visibly wrong answer
for an invisibly wrong one. `international` is the one class we verify: four
facilities, each named so by its operator. That got its own column pair, and it
is what buyers see. `dist_airport_m` is unchanged and must be labelled
**airstrip** on any page — the difference is the entire point.

**3. A village is not a town centre.** `admin.places` holds 9,323 rows and 8,679
are villages. Measuring `dist_town_centre_m` to the nearest place of any kind
would put almost every parcel in Kenya a few hundred metres from a "town
centre" — the column would measure **OSM's tagging density, not a buyer's
access to a town**. Restricted to city / town / national_capital: 436 rows. The
same trap as C8, where health facilities stack on ward centroids.

**4. A named major road must be FURTHER than the paved road.** `dist_paved_road_m`
takes the nearest good-class road whether or not anyone named it;
`dist_major_road_m` requires a name, because a buyer cannot orient by an
unnamed trunk road. It is a strict subset, so it can only ever be larger. That
is now a verifier invariant — and the only assertion in the file that needs no
knowledge of Kenya at all, which is exactly why it is worth having.

> A filter can catch a fact the source admits about itself.
> It cannot catch a question that was subtly wrong.
> Only reading the answers out loud catches that.

Logged as D23 and E14. It is the direct descendant of D20 — that rule says never
display a field we do not source; this one says **a field we DO source can still
be the wrong answer**, and no amount of verification will say so.

### LESSON 49: I WROTE THE CAUSE BEFORE I CHECKED IT

All twenty PDFs printed no acreage. Not a wrong figure — the line was simply
absent, because the subtitle renders `size · project` and collapsed silently
when size came back None.

My explanation was that `SELECT p.area_sqm, ... i.*` names a column and then
splats a table holding one of the same name; a result row is keyed BY NAME, so
the duplicate collapses and the last one wins. It is a real bug shape. It
matched the symptom exactly. It is the third cousin of the `admin_name` join
that fanned out threefold and the raster catalogue serving whichever
`nightlights` row came back first. **I wrote the comment before I checked.**

It is not what happened. `analytics.parcel_intelligence` has 86 columns and
`area_sqm` is not one of them; the only name it shares with `land.parcels` is
`parcel_id`. Nothing was shadowed. **`land.parcels.area_sqm` is simply NULL** —
nullable, unpopulated at load, while `geom` is NOT NULL and had the answer all
along. Size now comes from `ST_Area(geom::geography)`, labelled *(our
measurement)*, with the client's stated figure winning when present.

**Rule E2 does not stop applying because the guess is a good one.** A confident
wrong cause, written into a comment, outlives the bug it misdescribes. The
aliasing went in anyway — for `parcel_id`, which IS shared, and which on a
parcel with no intelligence row would have written a null key into
`reports.reports`. The real bug was sitting one column over from the one I
invented.

### THE LANDMARKS BUILD

Six tables from OSM layers already on disk — nothing downloaded, and no licence
letter needed, because what we publish is a DISTANCE and a NAME.

| Table | Rows | |
|---|---|---|
| `admin.places` | 9,323 | new table; there had never been anywhere to measure "distance to town centre" FROM |
| `transport.airports` | 255 | 4 international, 246 domestic, 5 airstrips |
| `transport.bus_stops` | 1,082 | every transport stop, not just buses — see E15 |
| `transport.railways` | 750 | |
| `social.markets` | 2,205 | confidence 2; county registers are the primary |
| `social.public_services` | 606 | |

**One script, not six**, because all six are the same three steps against the
same file set and six scripts would be six copies of one bug. The SPECS table is
the only thing written six times.

**The preflight is the part worth keeping.** The first run loaded 9,323 places
and then died on row one of the next table: `transport.airports.facility_type`
is CHECK-constrained to international / domestic / airstrip and the spec said
`airport`. I had invented the vocabulary from what OSM calls things instead of
reading the schema that has to accept them — E2 again, on a constraint sitting
in a snapshot I had already opened twice that day. The repair is not to be more
careful. **The script now reads the real constraints out of `pg_constraint` and
runs in two passes** — read and classify everything, validate every produced
value, and only then load. A mismatch names all offenders at once and loads
nothing, instead of leaving the database in a state no single run produced.

Two smaller traps, both worth the words:

**`(n or "")` does nothing here.** A missing name arrives from pandas as `NaN`,
`NaN` is a float, and **floats are truthy** — so `or` never fires and
`NaN.lower()` raises. Coercion is by `isinstance`. The second half of that fix
matters more: the unnamed-row drop now runs BEFORE classification, so the
name-based classifier never sees a missing name rather than being hardened
against one.

**Parsing a CHECK constraint by splitting on commas is silently wrong.**
Elements come back as `'domestic'::text`, so `strip("'")` leaves
`domestic'::text` — the trailing character is `t`, not a quote — and the
validator would then reject every value INCLUDING the correct ones. Quoted
literals are pulled with a regex, tested against both real constraint strings
before shipping.

### STATE AT CLOSE

- **Phases 1–4 complete. Phase 5 built and hardened**, not yet exercised end to
  end against a live client site.
- **43 assertions**, up from 31. Section G is new: five landmark IDENTITIES —
  Karen→Wilson, Ruai→JKIA, Lodwar→Lodwar, Garissa→Garissa, Kericho→Kericho —
  and five invariants. The identities are a different KIND of assertion from
  everything above them: those check a modelled number against a documented
  expectation, these check a name against a fact about Kenya that no model
  produced.
- **The buyer page carries nothing invented.** No price, because there is none.
  Eight plots all available, because that is what the seller's records say.
- **The long pole is still legal**, and it grew by one: **WASREB Majidata** is
  the national georeferenced water and sewer network system under Water Act 2016
  s.111 — exactly `dist_water_line_m` and `dist_sewer_m`. Buried mains mean OSM
  has nothing, so it is a letter or it is nothing. Logged as B7 and bundled with
  the KWS batch.

**Newly open:** B7, D23, D24, E14, E15.

**Still the cheapest high-value move on the board:** the KWS letter. It closes
A1 and fixes the coarse-boundary risk that has Kakamega blocked, and it has been
the answer to this question for four sessions.
