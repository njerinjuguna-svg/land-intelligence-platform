
---

## Session 11b — THE PRODUCT MODEL, WRITTEN DOWN AT LAST

This entry exists because a check of the repository found something worse
than a bug. **The two-phase business model was not recorded anywhere.**
Eleven sessions, 30 ETL pipelines, 114 assertions, five drafted letters — and
the single decision that determines what every one of them is FOR lived only
in conversation. The only trace of it in the whole build was one column,
`clients.companies.marketplace_opt_in`, added in session 1 and never
explained.

It surfaced the way undocumented decisions always do: I built the wrong thing
confidently. The embed widget was rendering the buyer's REPORT — the four
questions, the flood warning, the "before you pay" checklist — onto a
SELLER'S website, and it took Njeri saying so to catch it.

### THE TWO PRODUCTS

**PHASE 1 — SELL ENRICHMENT OF THE SELLER'S OWN PARCELS.** This is what we
sell now. The customer is a land-selling company. The widget goes on THEIR
website, describing land THEY own, to a buyer THEY are courting. It presents
what the land IS: size, soil, rainfall, access, amenities, landmarks, network,
and which other plots in the scheme are still open.

**PHASE 2 — THE GEOCODE MARKETPLACE**, once there are clients. We own the
page. The BUYER is the reader. This is where the unbiased half lives: the
suitability verdict, the flood warning, the protected-area refusal, the
recommendation, the "before you pay" checklist. `marketplace_opt_in` is the
flag a client sets to appear there.

### WHY THE JUDGEMENTS DO NOT GO ON THE SELLER'S PAGE

Njeri's reason, in her words: *a seller will always want the best for
themselves.* That is not a criticism — **it is what a seller is for**. Asking
their website to host an argument against their own sale is asking for
something no client will keep.

There is a second reason, and it is the one that protects the product rather
than the relationship. **A client who can see the analysis on their own page
will ask us to soften it.** Not maliciously; they will have a plot with a
`very_high` flood class and a buyer on the phone. And the moment we soften it
once, the analysis is worth nothing ANYWHERE — including on the marketplace,
where it is the entire product. The split is not diplomacy. It is the only
arrangement in which the verdict stays worth having.

    Facts go where the seller is the customer.
    Judgements go where we own the page and the buyer is the reader.
    Nothing is falsified in either place: a fact is simply not a verdict.

### WHAT CHANGED IN THE CODE

`report_content.build_listing()` is the Phase 1 view, beside `build_report()`
which stays the Phase 2 / PDF view. Both read the SAME enrichment row, in the
same module, for the reason that module exists: the day the widget and the
report disagree about a flood class, a client stops trusting both.

They are two functions and not one function with a flag, deliberately. A
boolean invites one view to drift into the other.

**THE PLOT SIZE IS THE SELLER'S FIGURE.** Not `ST_Area` of the boundary. They
surveyed it, they are selling it, they are the customer, and quietly replacing
their acreage with our measurement of their own plot is a survey finding
delivered as a typo. If they supplied no size, the field is simply absent. The
geometry-derived figure stays in the PDF, where the reader is the buyer and an
independent measurement is exactly the point.

**A BLOCKED PARCEL LOSES ITS SCORE AND GAINS NOTHING ELSE.** No red panel, no
stated reason, no "Not rated" badge a buyer would read as a warning. The
absence is the whole treatment. Why a plot cannot be scored is a conversation
for us and the seller, not something to print on their listing in front of
their buyer.

### THE ONE RULE THAT DOES NOT MOVE

**We do not print a claim we cannot source.** No title status, no zoning, no
electricity connection, no per-operator coverage. On a SELLER'S page this
matters MORE, not less: a "Title Verified" badge on the page of the person
selling the land is the most dangerous thing this product could render, and it
is dangerous *precisely because it benefits them*. D20 and D23 apply on both
pages without exception, and B5 stays open until Njeri decides it.

### ALSO THIS SESSION

**`v1.js` exists.** The whole architecture had always been "two lines in the
client's page", and the second line pointed at a file that had never been
written. With it: a `/v1.js` route, and CORS — without which the browser
blocks every response and the widget renders nothing on a real client domain.
Proven end to end against a deliberately ugly stand-in page built with none of
our styles, because a widget that only looks right on a page we designed is a
demo, not an embed.

**LESSON 50: `False`, `NULL` AND `NOT FOUND` ARE THREE ANSWERS, AND I SHIPPED
TWO BUGS TREATING THEM AS TWO.**

Deferring A1 meant WDPA — non-commercial — could no longer answer
`in_protected_area`. Switching to commercially usable sources broke the
product twice in one hour, in opposite directions:

1. The OSM protected-areas layer covers little of Kenya, so the query returned
   nothing for Aberdares, Kakamega and Tana Delta — and the code read *nothing
   found* as **not in a park**. Three national parks became saleable land.
   `False` is exactly the value that lets a parcel be scored, priced and
   listed.

2. The repair checked "did WDPA return a row" instead of "does WDPA say
   INSIDE". The search radius is tens of kilometres and there is a park within
   that of most of Nairobi, so **nineteen of twenty parcels blocked**,
   including Karen and every OAK GROVE plot. The product was dead.

Both failures are the same failure. The question has three answers — inside /
not inside / cannot tell — and I twice wrote code that could only express two,
reading "did the query return a row" as though it meant "is the parcel
inside". The state machine is now written out explicitly rather than inferred:

    commercial source answered          -> use it, note if WDPA disagrees
    silent, and WDPA says INSIDE        -> UNRESOLVED (NULL), block the score
    silent, and WDPA says near or none  -> False, and that IS an answer

And `blocking()` now fails CLOSED: anything other than a confident `False`
stops the score, because `if r.get("in_protected_area")` treats `None` and
`False` identically — correct Python, wrong product.

**The price of deferring A1, stated plainly:** `dist_protected_area_m` is now
NULL on most parcels, because that number came from data we cannot publish.
The boolean still answers, scoring is unaffected, and it returns the day KWS
lands. Three parcels remain unsellable until then — and that is the real
argument for the KWS letter. A1 is not licence housekeeping; it is the
difference between refusing to rate land and rating it.

### STATE AT CLOSE

- **43 enrichment assertions + 71 scoring checks, 0 failed.** Four parcels
  correctly blocked: three protected-area-unresolved, one boundary.
- **The widget works on a third-party page.** Phase 1 is renderable end to end.
- **Still not built:** a server (it runs on one laptop), rate limiting,
  billing, upload rejection gates, the Google Maps key for satellite and
  Street View.
- **A1 downgraded** to a later improvement by Njeri's decision, with the
  consequences above made safe rather than ignored. **A2 (CA) reported as
  cleared** — get the written confirmation on file, per the standing rule that
  a verbal go-ahead is not an answer to an acquirer. **A5 (Kenya Power)
  awaiting data.**
