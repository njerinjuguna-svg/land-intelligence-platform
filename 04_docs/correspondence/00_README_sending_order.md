# Correspondence Pack — sending order and what each unblocks

**Prepared session 7, 2026-08-18. Six letters to five organisations.**

Nothing here is sent. Each file contains the draft plus notes on why it is
phrased as it is, so you can edit with the reasoning visible rather than
guessing at it.

---

## Send in this order

| # | To | Unblocks | STATUS |
|---|---|---|---|
| **1** | **Communications Authority** | **A2 (legal blocker)** + B1 + possibly A3 | **SENT — 2026-08-18.** Phoned first; advised verbally that **no licence is required**, and referred to another data body (unnamed). Email sent seeking WRITTEN confirmation, the identity of that body, and the 3G/4G clarification. **A2 stays OPEN until the written reply arrives** — a phone call is not an artefact. |
| **2** | **WRA** | B2 + the ODbL exit (A4) + `river_class` NULL since session 2 | **PENDING — Njeri attending in person.** Letter drafted and held. Take a printed copy: it lists all three requests, so nothing is forgotten in the room, and it leaves a document on file after the meeting. |
| 3 | Kenya Power | A5 + a missing P1 dataset | Ready. Personal contact. |
| 4 | KNBS | C3 (population) | Ready. Foundational, not blocking. |
| 5 | IEBC | C4 (`LIP-W` ward codes) | Ready. Foundational, not blocking. |
| 6 | KWS | **A1 (legal blocker)** | Ready. Blocking, but slow to resolve — start early. |

**Why the CA goes first.** It is the only one where you are *already holding
and building on* data you have no permission to sell. WRA, KNBS, IEBC and KWS
are things you want; the CA is something you have. It is also the only letter
where a reply might close three checklist items at once.

**Why WRA is second and not last.** It was ranked last when it was only about
flood gauge data. It is actually the authoritative river network — which is the
clean exit from your sharpest ODbL exposure, since `riparian_buffers` is
derived from OSM rivers — plus the perennial/seasonal classification, plus the
gauge records. Connecting the licensing thread to the accuracy thread is what
moved it up.

---

## Before you send any of them

**Verify every address.** Only `info@ca.go.ke` is confirmed from your own
files. The rest carry the organisation's website and a note to take the current
address from it. **Do not let a placeholder go out.**

**Fill the common blanks:** `[YOUR TITLE]`, `[PHONE]`, `[COMPANY REG NO]`, the
date.

**Send as a signed PDF on letterhead, attached to the email.** Kenyan agencies
route formal requests better when there is a letter to file. The Kenya Power
one is the exception — that is a personal email to a named contact and should
stay one.

**One paragraph needs checking before it goes:** the KWS letter offers to share
encroachment findings derived from client parcel data. That may cut across
confidentiality terms in your land-company agreements. Soften it to aggregate
reporting, or make it conditional on client consent, unless you are sure.

---

## The thread running through all six

Every letter asks for **derived use, not data**.

> "May we publish that the nearest MV line is 340 metres away, without ever
> holding or redistributing your network?"

is a different question, with a different answer, from "may we have your
network?" It exposes nothing in bulk, reads closer to a service enquiry than a
data release, and can often be approved at departmental level rather than
travelling up to a board.

It is also all the product actually needs. You are not building a data
reseller. You are building something that answers questions about a specific
parcel, and a distance is not a database.

---

## What is still not covered

- **The lawyer.** `LICENSING_OPTIONS_MEMO.md` §7 holds the brief, now complete
  and specific. It is not a letter to an agency — it goes to Kenyan
  IP/technology counsel.
- **Unwired Labs (OpenCellID).** A commercial enquiry, not an approval request:
  they sell licences, so this one closes for money. Price it before engineering
  a replacement. May be made redundant if the CA grants transmitter access.
- **County governments** — zoning, markets, sewer, waste. P2/P3, and 47
  separate conversations. Deal with them per pilot county rather than
  nationally.
