-- ===========================================================================
-- SCHEMA UPDATE v1.12 - WHERE "BOOK A SITE VISIT" GOES
-- Land Intelligence Platform - Geocode Spatial Solutions Ltd
--
-- WHY THIS EXISTS
--   The widget has carried a "Book a site visit" button since the listing
--   view was built, and it has always pointed at "#". It was left inert
--   deliberately - inventing a destination would be worse than an obvious
--   placeholder - but a dead button on a client's live listing is a defect
--   the day a real seller uses it, and it is the single most valuable click
--   on the page. A buyer who wants to see the land is a buyer.
--
--   clients.branding already holds logo_url, primary_color, secondary_color,
--   report_footer and custom_domain. It has nowhere to put this.
--
-- WHAT GOES IN IT
--   Whatever the seller actually uses. In Kenya that is usually a WhatsApp
--   link, sometimes a booking form, sometimes a phone number:
--
--     https://wa.me/254722000000?text=I%20am%20interested%20in%20Plot%20457
--     https://kamauproperties.co.ke/book-a-visit
--     tel:+254722000000
--
--   The widget renders the button only when this is set, so the button
--   appears when it works and is absent when it does not. There is no state
--   in which it is present and dead.
--
-- WHY IT IS VALIDATED IN THE APPLICATION AND NOT HERE
--   A CHECK constraint on a URL scheme would reject a client's row at load
--   time, which puts the failure in the wrong place - onboarding, not
--   rendering. The API validates the scheme before it emits an href and
--   simply omits the button otherwise, so a bad value degrades to a missing
--   button rather than a broken page or an injection.
--
-- Run from 01_database with psql:
--   psql -U postgres -d land_intelligence_kenya -f 15_schema_update_v1.12.sql
-- ===========================================================================

BEGIN;

ALTER TABLE clients.branding
    ADD COLUMN IF NOT EXISTS site_visit_url text;

COMMENT ON COLUMN clients.branding.site_visit_url IS
  'Where the widget''s "Book a site visit" button points for this client. '
  'A WhatsApp link, a booking form, or tel:. https:, http:, tel: and '
  'mailto: only - the API validates the scheme and OMITS THE BUTTON if it '
  'does not match, so a bad value costs a button and never a broken page. '
  'NULL means no button, which is the correct default: an inert button is '
  'worse than none.';

-- Written now, while the reasoning is fresh, because these columns existed
-- for two sessions before anything read them and nobody could say what was
-- meant to go in them.
COMMENT ON COLUMN clients.branding.logo_url IS
  'The SELLER''s logo, shown in the widget''s "listed by" line. Must be '
  'https: - an http: image on an https page is blocked as mixed content and '
  'the API omits it rather than emitting a broken tag. The company name is '
  'always rendered beside it, so a logo that fails to load degrades to text.';

COMMENT ON COLUMN clients.branding.primary_color IS
  'The seller''s accent colour, applied ONLY to the "listed by" strip. '
  'IT DOES NOT RESTYLE THE ANALYSIS, and that is a product decision rather '
  'than an oversight: a seller who can restyle the assessment panel will '
  'eventually restyle it to look like approval, and the independence of the '
  'analysis is the whole product. Validated as a hex colour before it '
  'reaches any style attribute.';

COMMIT;
