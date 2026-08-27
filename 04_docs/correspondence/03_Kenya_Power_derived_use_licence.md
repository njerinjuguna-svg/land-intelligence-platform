# Letter 3 — Kenya Power (KPLC)

**Purpose:** a **derived-use licence**, not the data.

**Checklist item closed if this succeeds:** A5 — and it completes
`utilities.power_distribution`, one of only two P1 datasets still missing.

---

## Before sending

| | |
|---|---|
| **Send to** | Njeri's GIS contact, by name. **This is not a letter to a Director General.** |
| **Register** | Warmer and shorter than the WRA and CA letters. A named person who already knows you can move something internally that a formal letter cannot. |
| **Fill in** | `[CONTACT FIRST NAME]`, `[YOUR TITLE]`, `[PHONE]`, how you know each other |

---

## THE CENTRAL POINT — do not lose this in editing

**We are not asking for the network. We are asking for permission to publish a
distance.**

A utility's GIS team can rarely approve releasing the distribution network:
it is commercially sensitive, security-relevant, and the request goes up
several levels and usually dies there.

But "may we state that the nearest medium-voltage line is 340 metres away,
without ever holding or redistributing your network" is a different question
with a different answer. It exposes no asset locations in bulk, it is closer to
a service enquiry than a data release, and it can often be approved at
departmental level.

**Every "no" this letter is likely to get is a no to a request we are not
making.** Say so early and plainly.

---

## Draft

**Subject: A licensing question — proximity to distribution infrastructure**

Dear [CONTACT FIRST NAME],

I hope you are well.

I am writing about something I would value your guidance on, and I want to be
clear at the outset that **it is not a request for Kenya Power's network
data.** I know how that request usually goes, and it is not what we need.

Some background. Geocode Spatial Solutions Ltd is building a national land
intelligence database for Kenya. When a land-selling company uploads a parcel,
we assess it against physical and regulatory factors — terrain, soil, flood
exposure, rainfall, distance to roads, schools, health facilities and water —
and produce a written assessment for the buyer.

"Is there power nearby, and what would connection realistically cost?" is one
of the questions buyers ask most, and one we currently cannot answer. We are
reduced to inferring it from night-time satellite lights and openly mapped
power lines, which is a poor substitute and we would rather not ship it.

**What we would like to ask for is narrower than a data release.**

We would like permission to compute and publish a **derived measurement** — for
example:

> "Nearest medium-voltage distribution line: approximately 340 metres."
> "Nearest transformer: approximately 1.2 kilometres."

under terms in which we would undertake that:

1. we would **not redistribute, publish, display or export the network
   geometry** in any form;
2. no map, report, portal or API of ours would render the lines or
   transformers;
3. we would publish **only a distance figure** for a specific parcel, rounded
   so that the underlying position cannot be reconstructed;
4. we would attribute Kenya Power as the source of that measurement in whatever
   wording you require;
5. we would accept audit, review or withdrawal of the arrangement at Kenya
   Power's discretion.

If it helps, the computation could be done in a way where **we never hold the
network at all** — for instance against a service you host, or in a supervised
environment, with only the resulting distances returned to us. We are open to
whatever structure your data governance people are most comfortable with.

**Why this matters beyond our product.** A buyer who does not know a plot is
four kilometres from the nearest line discovers the connection cost after
purchase, and that is usually when a plot stops being developed. Making it
visible before purchase tends to mean connections are budgeted for rather than
abandoned.

Could I ask two things: first, whether an arrangement of this kind is something
Kenya Power would consider at all; and second, who the right person or
department would be to make it to formally. I am glad to put it in whatever
form is required, and equally glad to come in and explain what we are building.

Thank you for your time — I appreciate it.

Best regards,

**Njeri Njuguna**
[YOUR TITLE]
Geocode Spatial Solutions Ltd
[PHONE] · njerinjuguna943@gmail.com

---

## Notes on why it is written this way

**The first line says what we are NOT asking for.** Your contact has almost
certainly declined this request before in its usual form. Removing that
expectation immediately is what buys the rest of the letter a reading.

**The five undertakings are numbered so they can be forwarded.** Your contact
will need to put this to someone else. Numbered commitments can be pasted into
an internal note; prose cannot.

**Point 5 — accepting withdrawal at their discretion — is deliberate.** It
makes the arrangement feel reversible, and reversible things get approved far
more readily than permanent ones.

**Offering to never hold the data at all is the strongest concession** and is
placed right after the undertakings. If the sticking point is custody rather
than use, this removes it entirely, and it costs us little: we need the
distance, not the lines.

**The public-interest paragraph is one paragraph and factual.** A utility
benefits from connections being budgeted rather than abandoned. Said once, it
lands; laboured, it reads as leverage.

**Two questions at the end, both easy to answer.** "Would you consider this?"
and "who should I ask?" Neither requires your contact to decide anything, which
makes replying low-cost — and a reply is what we need.
