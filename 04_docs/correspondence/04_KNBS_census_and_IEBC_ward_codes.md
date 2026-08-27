# Letters 4 and 5 — KNBS and IEBC

Two agencies, one underlying problem: **our administrative and population
foundation is unofficial.** Every ward-level statistic in the database rests on
it, so these two letters fix more downstream than their size suggests.

**Checklist items closed:** C3 (population not census-calibrated), C4
(provisional `LIP-W` ward codes), B3, and the incomplete ward file open since
session 1.

---

# LETTER 4 — Kenya National Bureau of Statistics

**Send to:** verify the current address at **https://www.knbs.or.ke** — do not
guess. Herufi House, Lt. Boulevard Road, Nairobi.

**Note:** `sources.csv` records KNBS as tier 1, "GoK open data". This may
already be downloadable, or need only a data request form rather than a
negotiation. **Check the portal before sending** — if the tables are public,
this becomes a two-line query about format rather than a request.

---

**Subject: Request for 2019 Census population data at ward level**

The Director General
Kenya National Bureau of Statistics
Herufi House, Lt. Boulevard Road
Nairobi

Dear Sir/Madam,

**RE: REQUEST FOR 2019 KENYA POPULATION AND HOUSING CENSUS DATA AT COUNTY AND
WARD LEVEL**

Geocode Spatial Solutions Ltd is a Kenyan geospatial company building a
national land intelligence database used to assess land parcels for buyers and
land-selling companies. Population and settlement density are among the factors
we report.

We currently derive population from WorldPop, a modelled global gridded
dataset. Comparing it against the 2019 Census has shown us clearly why a
modelled product cannot substitute for the official count:

- nationally, WorldPop totals **55,201,278** against the Census figure of
  **47,564,296** — an overstatement of about **16 per cent**;
- at county level the divergence is far larger in the arid north. Mandera reads
  approximately **209 per cent** above the Census figure, Garissa **86 per
  cent**, Turkana **34 per cent**.

We have taken the position internally that we will not publish absolute
population figures to clients until we can anchor them to the official Census,
and we have restricted our platform to relative comparisons in the meantime.
We would prefer to resolve this properly rather than continue to caveat it.

We therefore request the **2019 Kenya Population and Housing Census** results
at:

1. **county level** — total population, households, and area; and
2. **ward level** — the same, this being the unit at which we compute
   statistics.

Digital tabular form (CSV or Excel) would be ideal. If ward-level tabulations
are published in volume form only, we would be grateful for guidance on the
correct volume and table numbers so we can transcribe them accurately.

We would also welcome confirmation of the terms on which this data may be used
in a commercial product, and the attribution wording you require.

We would note that our intended use is what is known as dasymetric mapping: the
Census provides the authoritative total for each administrative unit, and the
modelled grid is used only to distribute that official total within the unit.
The published figure a user sees would therefore be the Bureau's, not a
model's. **We do not intend to rescale or adjust the Census in any way** — the
Census is the anchor, and the model defers to it.

We are happy to complete whatever data request procedure the Bureau requires.

Yours faithfully,

**Njeri Njuguna**
[YOUR TITLE] · Geocode Spatial Solutions Ltd
[PHONE] · njerinjuguna943@gmail.com

---

# LETTER 5 — Independent Electoral and Boundaries Commission

**Send to:** verify the current address at **https://www.iebc.or.ke** — do not
guess. Anniversary Towers, University Way, Nairobi.

---

**Subject: Request for ward boundary data and official ward codes**

The Chief Executive Officer
Independent Electoral and Boundaries Commission
Anniversary Towers, University Way
Nairobi

Dear Sir/Madam,

**RE: REQUEST FOR WARD BOUNDARIES AND OFFICIAL WARD CODES**

Geocode Spatial Solutions Ltd is a Kenyan geospatial company building a
national land intelligence database. Wards are the administrative unit at which
we compute and report most statistics, which makes the Commission's boundary
data foundational to our work.

We currently hold a ward boundary dataset obtained from an open humanitarian
data repository. It has two limitations we cannot resolve from that source:

1. **It contains 1,425 wards against the 1,450 officially gazetted** — about
   98.3 per cent. We cannot determine which 25 are absent, or whether the
   discrepancy reflects omission or a boundary revision.
2. **It carries no usable ward codes.** The identifier field in the file is not
   unique per ward, so we have been obliged to assign provisional internal
   codes. Any future join to official statistics — Census data among them —
   will require migrating to the Commission's codes.

We therefore request:

1. the **complete gazetted ward boundary dataset**, in a GIS format
   (shapefile or geodatabase);
2. the **official ward code** for each ward, together with its parent
   constituency and county codes; and
3. confirmation of the **currently gazetted ward count** and the date of the
   most recent boundary revision, so that we can record the vintage of what we
   hold.

We would also welcome confirmation of the terms on which this data may be used
in a commercial product, and the attribution wording you require.

We would be glad to follow whatever formal request procedure applies.

Yours faithfully,

**Njeri Njuguna**
[YOUR TITLE] · Geocode Spatial Solutions Ltd
[PHONE] · njerinjuguna943@gmail.com

---

## Notes on why these are written this way

**Both letters lead with the specific defect, quantified.** "1,425 of 1,450"
and "+209 per cent in Mandera" are checkable numbers. An official reading them
can see immediately that we have done the work and are not fishing.

**The KNBS letter states what we will NOT do, and it is the load-bearing
sentence.** Statistical agencies are wary of people rescaling official figures
into something that then carries their name. Saying plainly that the Census is
the anchor and the model defers to it removes the objection before it is
raised.

**Mentioning that we already restrict ourselves to relative comparisons**
demonstrates we treat the gap as a real limitation rather than an inconvenience
to be worked around. That is worth more than any assurance about future
conduct.

**The IEBC letter asks for the ward count as a question, not an assertion.** We
believe it is 1,450; if it has since changed, we would rather be told than
carry a stale figure. Asking also gives them something easy and satisfying to
answer, which tends to get letters replied to.

**Neither claims urgency.** These are foundational rather than blocking — the
platform functions without them, with caveats. Manufacturing urgency towards
government agencies rarely accelerates anything and can cost credibility.
