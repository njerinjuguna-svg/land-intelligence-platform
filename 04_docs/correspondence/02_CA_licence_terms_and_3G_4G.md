# Letter 2 — Communications Authority of Kenya

**Purpose:** written licence terms for the ICT coverage layers, and
clarification of which of two apparently identical layers is correctly
labelled.

**Checklist items closed if this succeeds:** A2 (legal blocker — currently
gates selling anything derived from coverage data) and B1.

**Possible bonus:** the CA also publishes transmitter locations. If the licence
comes back permissive, that may let us retire OpenCellID and close A3 at the
same time.

---

## Before sending

| | |
|---|---|
| **Email** | `info@ca.go.ke` |
| **Address** | Communications Authority of Kenya, CA Centre, Waiyaki Way, P.O. Box 14448-00800, Nairobi |
| **Best practice** | Signed PDF on letterhead attached to the email. Copy the Director/Head of Licensing, Compliance and Standards if you can identify the current holder from ca.go.ke. |
| **Fill in** | `[YOUR TITLE]`, `[PHONE]`, `[COMPANY REG NO]`, the date, and **verify the exact layer names on the portal before sending** |

**The delicate part.** We are telling a regulator that two of its published
datasets appear to be the same data under two different names. That is very
likely a publishing oversight rather than a data error, and the letter is
written to give them an easy, face-saving route to confirm or correct it. It
asks which layer we should rely on — not what went wrong.

**Do not soften it into vagueness, though.** The specific finding (99.9% of
records identical to six decimal places) is what makes the question answerable
by whoever actually holds the file. A vague query gets a vague reply.

---

## Draft

**Subject: Request for licence terms — ICT Services Coverage geoportal data**

The Director General
Communications Authority of Kenya
CA Centre, Waiyaki Way
P.O. Box 14448-00800
Nairobi

Dear Sir/Madam,

**RE: LICENCE TERMS FOR ICT SERVICES COVERAGE DATA, AND A CLARIFICATION ON
TECHNOLOGY LABELLING**

Geocode Spatial Solutions Ltd is a Kenyan geospatial company building a
national land intelligence database. Among the factors we assess for a land
parcel is the quality of mobile network coverage in the surrounding area, which
is a material consideration for buyers, particularly outside the major towns.

We have obtained the sublocation-level coverage datasets published on the
Authority's ICT Services Coverage geoportal. We write on two matters.

**1. Licence terms for commercial use**

The datasets are publicly downloadable, but each carries no declared licence:
the `licenseInfo` and `accessInformation` fields are empty on every item we
retrieved. We do not regard public availability as authority to use the data
in a commercial product, and we have therefore recorded it internally as not
redistributable and have not used it in any commercial output.

We respectfully request written confirmation of the terms on which this data
may be used commercially, specifically:

- whether we may compute and publish derived statements from it — for example
  "the sublocation containing this parcel is reported as 64.9 per cent
  4G-covered" — within a paid report;
- any attribution wording the Authority requires;
- whether onward redistribution of the underlying polygons is permitted or
  prohibited. **We do not seek to redistribute them.** Our requirement is to
  publish derived measurements only;
- whether any licence fee or data-sharing agreement applies.

We would add that we have been careful in how the data is represented. Because
the Authority publishes a coverage percentage per sublocation rather than
signal propagation contours, our platform states the coverage of the
surrounding administrative area and does not assert that any individual parcel
has service. We have also recorded that no Airtel percentage is published, and
our reports state that the absence of Airtel figures reflects the absence of
published data rather than the absence of coverage.

**2. A clarification on technology labelling**

In preparing the data we found something we would like the Authority's guidance
on, as we would rather ask than assume.

Two published layers — one labelled 3G and one labelled 4G — appear to contain
the same data. Specifically:

- both contain the same number of features (7,134);
- their coverage percentages have the same median and the same distribution;
- when joined on the sublocation identifier, **over 99.9 per cent of records
  agree to six decimal places.**

Two distinct mobile technologies would not be expected to agree so closely. We
have concluded that one dataset has most likely been published under two
technology labels, and we have retained the more recent of the two and set the
other aside.

Our difficulty is that we cannot tell which label is the correct one. If the
layer we retained is the mislabelled copy, figures we describe as 4G coverage
may in fact describe 3G — a difference that matters to a buyer.

We would be grateful if the Authority could advise which of the two layers
carries the correct technology label, or confirm the correct figures for each
technology. We are of course happy to correct our records accordingly.

We would also note, for completeness, that the layer carrying the 3G label
includes "test" in its published service name, which may itself explain the
matter.

**A related question**

If the Authority's licence terms permit commercial use, we would also welcome
confirmation that the same terms extend to the published transmitter location
data. We currently rely on a crowdsourced international source for tower
positions, which is materially less reliable than the Authority's own records,
and we would prefer to use the authoritative data where we are permitted to.

We would welcome the opportunity to discuss any of the above, and are happy to
follow whatever formal process the Authority prefers.

Yours faithfully,

**Njeri Njuguna**
[YOUR TITLE]
Geocode Spatial Solutions Ltd
[PHONE] · njerinjuguna943@gmail.com
[COMPANY REG NO]

---

## Notes on why it is written this way

**We demonstrate good faith before asking for anything.** Stating that we have
recorded the data as not redistributable and have not used it commercially
establishes that we are asking permission rather than seeking retrospective
cover. Regulators respond differently to the two.

**The "we do not seek to redistribute" line does the heavy lifting**, exactly
as in the WRA letter. Permission to publish a derived percentage is a much
smaller thing to approve than a data release, and it is all we actually need.

**The mislabelling is framed as our difficulty, not their error.** "We cannot
tell which label is correct" invites a helpful answer; "your data is wrong"
invites a defensive one. The evidence is still stated precisely, because a
vague question cannot be answered by the person who holds the file.

**The "test" observation is placed last and stated neutrally.** It gives them a
ready explanation that costs no institutional face — the likeliest true one —
without our asserting it.

**The transmitter request is deliberately last and framed as a preference for
authoritative data over crowdsourced.** That is both true and flattering in a
way a regulator can accept. If it succeeds it closes checklist A3 as a side
effect, which is worth a paragraph.
