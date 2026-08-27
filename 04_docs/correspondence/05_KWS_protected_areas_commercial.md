# Letter 6 — Kenya Wildlife Service

**Purpose:** commercial terms for protected area boundaries, to replace WDPA.

**Checklist item closed if this succeeds:** A1 — a legal blocker open since
session 3.

---

## Why this one is a genuine blocker, not a nice-to-have

`environment.protected_areas` holds **349 areas** from the World Database on
Protected Areas (UNEP-WCMC). WDPA is **explicitly non-commercial**.

That is fine for building and testing, which is what we have been doing. It is
not fine for selling, and the layer answers a question that materially affects
whether a plot can be built on at all. **Dropping it is not a good option; the
data has to be replaced or cleared.**

Two routes, and this letter takes the first:

1. **KWS under a commercial agreement** — authoritative, Kenyan, and removes
   the problem outright. `datasets.csv` already names KWS as the intended
   primary source with WDPA as backup, so this is returning to the plan rather
   than changing it.
2. Written clearance from UNEP-WCMC for our specific use. Worth pursuing in
   parallel if KWS is slow, though a non-commercial licence is not usually
   waived on request.

**Send to:** verify the current address at **https://www.kws.go.ke** — do not
guess. KWS Headquarters, Langata Road, P.O. Box 40241-00100, Nairobi.

**Fill in:** `[YOUR TITLE]`, `[PHONE]`, `[COMPANY REG NO]`, the date.

---

## Draft

**Subject: Request for protected area boundary data — commercial licence terms**

The Director General
Kenya Wildlife Service
Langata Road
P.O. Box 40241-00100
Nairobi

Dear Sir/Madam,

**RE: REQUEST FOR PROTECTED AREA BOUNDARY DATA AND COMMERCIAL LICENCE TERMS**

Geocode Spatial Solutions Ltd is a Kenyan geospatial company building a
national land intelligence database. When a land parcel is assessed on our
platform, one of the checks performed is whether it lies inside, or close to, a
national park, national reserve, conservancy or sanctuary.

This matters commercially and legally. Land offered for sale in Kenya
occasionally sits within or adjoining a protected area, and buyers are not
always told before purchase. Surfacing it at the point of sale is one of the
purposes of our platform.

We currently use the World Database on Protected Areas, from which we hold 349
Kenyan areas. **That dataset is licensed for non-commercial use only**, so
while it has been adequate for development it cannot be used in the product we
intend to sell. We would rather license the authoritative Kenyan source than
continue on a dataset we are not entitled to sell against.

We therefore request:

1. **Boundary data for protected areas under the Service's mandate** — national
   parks, national reserves, sanctuaries, marine protected areas and, where
   held, conservancies — in a GIS format (shapefile or geodatabase);
2. the **official name and designation** of each area, and the managing
   authority where the Service is not itself the manager;
3. **the terms on which this data may be licensed for commercial use**,
   including any licence fee, attribution wording, and any restriction on
   onward redistribution.

**On redistribution: we do not seek it.** Our requirement is to compute and
publish derived statements for a specific parcel — for example "this parcel
lies approximately 1.8 kilometres from the boundary of Nairobi National Park" —
rather than to publish or supply the boundaries themselves. If the Service
prefers a licence limited to derived use, that would meet our needs entirely.

If it is useful, we would be glad to share back the results of our analysis:
specifically, where land currently being marketed for sale intersects or
adjoins protected areas. We hold parcel data from land-selling companies and
would be able to identify such cases as they arise. We recognise encroachment
is a matter the Service takes seriously and would be pleased for our platform
to work with that rather than around it.

We would welcome a meeting, and are happy to follow whatever formal application
process applies.

Yours faithfully,

**Njeri Njuguna**
[YOUR TITLE]
Geocode Spatial Solutions Ltd
[PHONE] · njerinjuguna943@gmail.com
[COMPANY REG NO]

---

## Notes on why it is written this way

**We admit the WDPA position openly.** We have been using a non-commercial
dataset and are stopping before selling. Volunteering that is better than
having it discovered, and it establishes that we approach licensing carefully —
which is the whole basis on which a state agency would license to us.

**The derived-use offer appears again**, as with WRA, the CA and Kenya Power.
It is consistently the smallest possible ask that still meets the need, and it
is consistently the easiest thing for an institution to approve.

**The encroachment offer is the strongest card and is real.** We will hold
parcel boundaries from land-selling companies. Being able to flag land marketed
inside or adjoining a protected area is directly useful to KWS and costs us
nothing we would not already compute.

**One caution before sending: check this against your client agreements.**
Offering to share findings derived from client parcel data may cut across
confidentiality terms with the land companies. It may need to be softened to
aggregate or anonymised reporting, or made conditional on client consent.
**Do not send this paragraph as written without checking that.**
