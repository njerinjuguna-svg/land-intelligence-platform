r"""
============================================================================
SET A CLIENT'S BRANDING
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHAT THE SELLER CONTROLS, AND WHAT THEY DO NOT

  Their logo, their accent colour, their footer wording, and where "Book a
  site visit" goes. All of it attaches to the "listed by" strip and the
  call-to-action.

  NOT the analysis. Not the score dial, not the answers, not the cards, not
  the colours of any of them. That is a product decision and not an
  oversight: a seller who can restyle the assessment will eventually restyle
  it to look like approval, and the independence of the analysis is the
  entire product. It is also the same reasoning that keeps the verdicts off a
  seller's page altogether (section 2).

  If a client asks to match their brand, the answer is that the panel says
  "Listed by <them>" and "Independent analysis by Geocode", and that the
  second line is what makes the first one worth reading.

VALIDATION HAPPENS TWICE, ON PURPOSE
  Here, so a bad value is rejected while somebody is looking at it, with an
  explanation. And again in the API at render time, because this script is
  not the only way a row can reach that table - psql exists, and so does a
  future admin page.

RUNS AS THE SUPERUSER
  landiq_api has no INSERT or UPDATE on clients.branding, by design: the
  component on the internet must not be able to restyle itself.

USAGE
  python set_branding.py --company "ZZ TEST" --show
  python set_branding.py --company "ZZ TEST" \
      --visit "https://wa.me/254722000000?text=I%20am%20interested" \
      --logo  "https://kamauproperties.co.ke/logo.png" \
      --color "#14532d" \
      --footer "Kamau Properties Ltd. Site visits every Saturday."
  python set_branding.py --company "ZZ TEST" --clear-logo
============================================================================
"""
import os
import re
import sys
import argparse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
ENV_DIR = BASE.parent / "03_etl"

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
ACTION_SCHEMES = ("https://", "http://", "tel:", "mailto:")


def connect():
    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")


def check(field, value):
    """-> (ok, message). The message is what the widget will actually do."""
    if value is None:
        return True, None
    v = value.strip()
    if field == "primary_color":
        if not HEX.match(v):
            return False, ("not a hex colour. Use #14532d or #abc. Anything "
                           "else is dropped before it reaches a style "
                           "attribute.")
        return True, "accent on the 'listed by' strip only"
    if field == "logo_url":
        if not v.lower().startswith("https://"):
            return False, ("must be https. An http image on an https page is "
                           "blocked as mixed content, so the widget omits it "
                           "and shows the company name alone.")
        return True, "shown beside the company name"
    if field == "site_visit_url":
        if not any(v.lower().startswith(s) for s in ACTION_SCHEMES):
            return False, ("scheme must be https:, http:, tel: or mailto:. "
                           "The button is omitted otherwise - there is no "
                           "state where it is present and dead.")
        return True, "the 'Book a site visit' button appears"
    return True, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True, help="name, or part of it")
    ap.add_argument("--logo")
    ap.add_argument("--color")
    ap.add_argument("--footer")
    ap.add_argument("--visit")
    ap.add_argument("--show", action="store_true")
    for f in ("logo", "color", "footer", "visit"):
        ap.add_argument(f"--clear-{f}", action="store_true")
    a = ap.parse_args()

    engine = connect()
    with engine.connect() as conn:
        hits = conn.execute(text("""
            SELECT company_id, name FROM clients.companies
             WHERE name ILIKE :q ORDER BY name"""),
            {"q": f"%{a.company}%"}).all()
    if not hits:
        sys.exit(f"No company matching '{a.company}'.")
    if len(hits) > 1:
        print("More than one company matches:")
        for _, n in hits:
            print(f"   {n}")
        sys.exit(1)
    company_id, name = hits[0]

    cols = {"logo_url": a.logo, "primary_color": a.color,
            "report_footer": a.footer, "site_visit_url": a.visit}
    for arg, col in (("clear_logo", "logo_url"), ("clear_color",
                     "primary_color"), ("clear_footer", "report_footer"),
                     ("clear_visit", "site_visit_url")):
        if getattr(a, arg):
            cols[col] = ""            # empty string -> stored as NULL below

    changes = {k: v for k, v in cols.items() if v is not None}

    if changes:
        print(f"\nFor: {name}\n")
        bad = False
        for col, val in changes.items():
            if val == "":
                print(f"   {col:<16} CLEARED")
                continue
            ok, msg = check(col, val)
            mark = "ok  " if ok else "BAD "
            print(f"   {mark}{col:<16} {val[:60]}")
            if msg:
                print(f"       -> {msg}")
            bad = bad or not ok
        if bad:
            sys.exit("\nNothing written. Fix the values above and run again.")

        sets = ", ".join(f"{c} = :{c}" for c in changes)
        params = {c: (None if v == "" else v.strip())
                  for c, v in changes.items()}
        params["cid"] = company_id
        with engine.begin() as conn:
            n = conn.execute(text(
                f"UPDATE clients.branding SET {sets}, updated_at = now() "
                f"WHERE company_id = :cid"), params).rowcount
            if not n:
                cl = ", ".join(changes)
                vl = ", ".join(f":{c}" for c in changes)
                conn.execute(text(
                    f"INSERT INTO clients.branding (company_id, {cl}) "
                    f"VALUES (:cid, {vl})"), params)
                print("\n   (no branding row existed - created one)")
        print("\nSaved. RESTART THE API to see it: the widget reads branding "
              "per request,\nbut stop_api.cmd / start_api.cmd is the reliable "
              "way to be sure.")

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT logo_url, primary_color, report_footer, site_visit_url
              FROM clients.branding WHERE company_id = :c"""),
            {"c": company_id}).one_or_none()

    print(f"\n{'=' * 70}\nCURRENT BRANDING - {name}\n{'=' * 70}")
    if not row:
        print("  none set. The widget shows no 'listed by' strip and no")
        print("  'Book a site visit' button.")
    else:
        for label, val in zip(("logo_url", "primary_color", "report_footer",
                               "site_visit_url"), row):
            print(f"  {label:<16} {val if val else '-'}")
        if not row[3]:
            print("\n  No site_visit_url: the 'Book a site visit' button is "
                  "absent.\n  That is intended - an inert button is worse "
                  "than none.")
    print("=" * 70)
    print("The analysis panel itself is not styleable, deliberately. See the")
    print("header of this file for why.")


if __name__ == "__main__":
    main()
