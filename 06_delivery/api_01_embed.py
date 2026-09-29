r"""
============================================================================
EMBED API v0.1 - the endpoint a client's website calls
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHAT A CLIENT INTEGRATES. Two lines in their page:

    <div id="geocode-plot" data-plot-ref="PLOT-457"></div>
    <script src="https://embed.geocode.co.ke/v1.js" data-key="pk_live_..."></script>

  That is the whole integration, and it is deliberate. If we are writing
  bespoke code per customer we are a consultancy, not a product.

WHY AN EMBED AND NOT AN API OF THE DATA
  Checklist A4: OpenStreetMap is ODbL and share-alike triggers on
  DISTRIBUTION, not possession. Holding OSM to compute "nearest road: 340 m"
  conveys nothing. Handing a client geometry conveys a database.

    embed widget      client receives nothing; it renders from our server
    API of values     numbers only
    API of geometry   this IS conveyance - the highest exposure there is

  So the widget is the product and the geometry never crosses the boundary.
  `report_content.assert_no_geometry()` enforces that on every response,
  because "remember not to select geom" is a reminder and this is a control.

THE ONE REAL INTEGRATION POINT IS PLOT IDENTITY
  Their site says "Plot 457"; our database says `parcel_ref`. That mapping is
  agreed at onboarding and it is where the conversation with their developer
  actually happens. Serving the wrong plot's analysis to a buyer is the worst
  failure this product has, so the lookup is scoped to the calling company and
  an unknown ref is a 404 - never a nearest match, never a guess.

RUN IT
  pip install fastapi uvicorn
  uvicorn api_01_embed:app --reload --port 8000
  curl -H "X-API-Key: <key>" http://localhost:8000/v1/plots/PLOT-457
============================================================================
"""

import os
import re
import math
import sys
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_content import (build_report, build_listing,
                            assert_no_geometry, GeometryLeak)

try:
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse, HTMLResponse, Response
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    sys.exit("ERROR: pip install fastapi uvicorn")

BASE = Path(__file__).resolve().parent
API_VERSION = "0.1.0"

# THIS FILE'S OWN .env FIRST, and the reason is the whole security boundary.
#
# Until now this read 03_etl/.env unconditionally - the ETL's file, holding
# the postgres superuser. DEPLOY.md said to `cp .env.example .env` here, and
# 06_delivery/.env.example carried the landiq_api grants, and NOTHING READ IT.
# Creating the confined user, granting it exactly eight privileges and proving
# it could not write would all have been decoration: the widget would still
# have connected as a superuser, and the tunnel would have put that superuser
# on the public internet.
#
# 03_etl/.env stays as the fallback so the enrichment tools are unaffected,
# and the choice is announced at startup rather than assumed.
_LOCAL_ENV = BASE / ".env"
_ETL_ENV = BASE.parent / "03_etl" / ".env"

if _LOCAL_ENV.exists():
    load_dotenv(_LOCAL_ENV)
    ENV_DIR, _ENV_FILE = BASE, _LOCAL_ENV
else:
    load_dotenv(_ETL_ENV)
    ENV_DIR, _ENV_FILE = _ETL_ENV.parent, _ETL_ENV
    print(f"WARNING: no {_LOCAL_ENV} - falling back to {_ETL_ENV}, which is "
          f"the ETL's credentials. Copy .env.example to .env and point it at "
          f"landiq_api before exposing this API.", file=sys.stderr)

print(f"[config] credentials from {_ENV_FILE}", file=sys.stderr)

_pw = os.getenv("DB_PASSWORD")
if not _pw or _pw == "put_your_password_here":
    sys.exit(f"ERROR: set DB_PASSWORD in {_ENV_FILE}")
engine = create_engine(
    f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{_pw}"
    f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
    f"/{os.getenv('DB_NAME','land_intelligence_kenya')}",
    pool_pre_ping=True)


def _refuse_superuser():
    """A control, not a warning. The API will not start as a superuser.

    This is the one component reachable from the public internet. There is no
    configuration in which it legitimately needs to be able to rewrite a
    parcel, drop a table, or read the staging schema - grants_landiq_api.sql
    exists precisely so it cannot.

    A warning here would be a reminder, and the failure mode it guards against
    is silent: everything works exactly as well with the wrong credentials,
    right up until it doesn't.
    """
    try:
        with engine.connect() as conn:
            who, sup = conn.execute(text(
                "SELECT current_user, "
                "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user)"
            )).one()
    except Exception as e:                                # noqa: BLE001
        sys.exit(f"ERROR: cannot reach the database using {_ENV_FILE}: {e}")

    if sup:
        sys.exit(
            f"\nREFUSING TO START.\n\n"
            f"  Connected as '{who}', which is a SUPERUSER, using {_ENV_FILE}.\n"
            f"  This API is the one component reachable from the internet and\n"
            f"  it must not hold credentials that can rewrite the database.\n\n"
            f"  Fix:\n"
            f"    psql -U postgres -d land_intelligence_kenya "
            f"-f ../01_database/grants_landiq_api.sql\n"
            f"    copy 06_delivery/.env.example to 06_delivery/.env\n"
            f"    set DB_USER=landiq_api and its password there\n")
    print(f"[config] connected as '{who}' (not a superuser)", file=sys.stderr)


_refuse_superuser()

# Say plainly whether the imagery will work. The widget falls back to a
# neutral placeholder when the key is missing, which is right on a client's
# page and useless to the person configuring it - "no pictures" looks
# identical whether the key is absent, in the wrong file, or added after the
# API was already running. The API reads its configuration ONCE, at startup.
_gk = (os.getenv("GOOGLE_MAPS_KEY") or "").strip()
if _gk:
    print(f"[config] Google Maps key: set ({_gk[:6]}...{_gk[-4:]}, "
          f"{len(_gk)} chars) - satellite and scheme map enabled",
          file=sys.stderr)
else:
    print(f"[config] Google Maps key: NOT SET in {_ENV_FILE} - the widget "
          f"will show a placeholder where the pictures go. Add "
          f"GOOGLE_MAPS_KEY=... to that file and RESTART.", file=sys.stderr)

# Reported separately, because "the interactive map is missing" is otherwise
# indistinguishable from "the pictures are missing" and the two have
# different causes and different fixes.
_ek = (os.getenv("GOOGLE_MAPS_EMBED_KEY") or "").strip()
if _ek and _ek == _gk:
    print("[config] Embed key: SAME AS THE SERVER KEY - the interactive map "
          "is disabled. That URL is public, so this would publish the key "
          "that bills Static Maps. Make a second key restricted to the Maps "
          "Embed API.", file=sys.stderr)
elif _ek:
    print(f"[config] Embed key: set ({_ek[:6]}...{_ek[-4:]}) - the movable "
          f"map on each plot is enabled", file=sys.stderr)
else:
    print(f"[config] Embed key: not set - the movable map on each plot is "
          f"using OpenStreetMap, which needs no key. It shows roads and "
          f"place names rather than imagery. For a satellite one, add a "
          f"SECOND key restricted to the Maps Embed API as "
          f"GOOGLE_MAPS_EMBED_KEY=... in {_ENV_FILE}.", file=sys.stderr)

app = FastAPI(title="Geocode LandIQ embed API", version=API_VERSION)

# ---------------------------------------------------------------------------
# CORS - AND WHY IT IS WIDE OPEN, WHICH LOOKS WRONG AND IS NOT
# ---------------------------------------------------------------------------
# This API is called by a <script> running on the CLIENT'S domain, so without
# Access-Control-Allow-Origin the browser blocks the response and the widget
# renders nothing. That much is mechanical.
#
# The part worth understanding: an origin allowlist would be SECURITY THEATRE
# here. The API key sits in the client's page source, visible to anyone who
# views it - that is inherent to every embed widget, Google Maps included -
# and the Origin header is set by the browser, so anything that is not a
# browser simply omits it. An allowlist would stop nobody who had already
# read the key, while breaking every legitimate staging domain, preview URL
# and CMS subdomain a client has.
#
# What actually protects the data is what already exists:
#   - the key is hashed, revocable, and scoped to ONE company in SQL
#   - an unknown parcel_ref is a 404, never a nearest match
#   - assert_no_geometry() means the worst case is somebody scraping values
#     for plots the client is already publishing on their own website
#
# The one real control still missing is RATE LIMITING against
# clients.subscriptions - a stolen key should cost the thief nothing and cost
# us nothing. That is the gap to close, not this one.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,      # never; see the loader's `credentials: omit`
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-API-Key"],
    max_age=3600,
)

LOADER = BASE / "v1.js"


@app.get("/v1.js")
def loader():
    """The two lines a client pastes point HERE.

    Served from this app rather than a CDN so that the origin the loader
    derives from its own src is always the API it needs to call. Put a CDN in
    front of the whole app later if it matters; do not split them, or a
    client on a stale cached loader will be calling an origin that has moved.
    """
    if not LOADER.exists():
        raise HTTPException(500, "loader missing")
    body = LOADER.read_text(encoding="utf-8")

    # NO-CACHE, AND THE REASON IS NOT PARANOIA.
    #
    # This was max-age=300. The server renders the HTML; this file supplies
    # the behaviour that HTML depends on, and the two ship together. For five
    # minutes after any deploy a browser would pair NEW markup with an OLD
    # loader, and the failure that produces is the worst kind: everything
    # renders, nothing is missing, and the controls simply do nothing. It
    # cost a round trip to find exactly that - zoom buttons drawn by the new
    # server, driven by a loader from before they existed.
    #
    # no-cache does not mean "download every time". It means "ask every
    # time", and the ETag makes the answer 304 Not Modified with no body on
    # every load but the first after a change. One conditional request for a
    # 12 KB file is a price worth paying for never being out of step.
    etag = '"' + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16] + '"'
    return Response(body, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache", "ETag": etag})


# ---------------------------------------------------------------------------
# Auth. The key is never stored - only its hash.
# ---------------------------------------------------------------------------
def authenticate(raw_key):
    """-> (auth dict, None) on success, or (None, reason) on refusal.

    THE KEY IS HASHED BEFORE IT TOUCHES THE DATABASE, and the column is
    `key_hash` because session 2 already decided this. A leaked database dump
    must not be a set of working credentials.

    THE CALLER LEARNS NOTHING; THE OPERATOR LEARNS EVERYTHING.

    This function used to answer one question - is this key good - by folding
    four separate conditions into a single WHERE and returning None. That is
    right for the RESPONSE. An unauthenticated caller must not be able to tell
    a wrong key from a revoked one from a suspended account, because that
    difference is a probing oracle: it confirms which keys exist.

    It is wrong for the LOG, and this build paid for the difference. A key
    that hashed correctly, was not revoked, had not expired and owned all
    twenty parcels was refused for the one remaining reason - the company
    behind it had is_active = false - and the message said "Unknown, revoked
    or expired API key". None of those three was true. It took a seven-column
    diagnostic query to find out which of four things had gone wrong, and a
    client's developer, on the phone, would have had none of that: they would
    have spent the afternoon regenerating a key that was never the problem.

    So the checks are made SEPARATELY and named. The HTTPException body is
    unchanged and identical in every case; the reason goes to the server log,
    where support can read it and an attacker cannot.
    """
    if not raw_key:
        return None, "no key supplied"
    h = hashlib.sha256(raw_key.encode()).hexdigest()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT k.api_key_id, k.company_id, k.scopes, c.name,
                   k.revoked, k.expires_at, c.is_active
              FROM clients.api_keys k
              LEFT JOIN clients.companies c ON c.company_id = k.company_id
             WHERE k.key_hash = :h
        """), {"h": h}).one_or_none()

    if row is None:
        return None, "no key with that hash"
    if row[4]:
        return None, "key revoked"
    if row[5] is not None and row[5] <= datetime.now(timezone.utc):
        return None, f"key expired {row[5]:%Y-%m-%d}"
    if row[6] is None:
        return None, "key points at a company_id that does not exist"
    if not row[6]:
        return None, f"company '{row[3]}' is not active"

    return ({"api_key_id": row[0], "company_id": row[1],
             "scopes": row[2] or [], "company": row[3]}, None)


def client_ip(request):
    """-> a value the `inet` column will accept, or None.

    logs.api_logs.ip_address is typed `inet`, and request.client.host is NOT
    always an IP address - it is 'testclient' under FastAPI's test client, and
    behind a proxy it can be whatever the hop reports. Postgres rejects the
    row, which took the whole usage log down with it on the first run.

    Validate, or store nothing. An unparseable host is not worth losing the
    billing record for.
    """
    host = getattr(getattr(request, "client", None), "host", None)
    if not host:
        return None
    try:
        import ipaddress
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def log_call(auth, request, status, ms):
    """Every call is logged. A usage row a client can be billed from must be
    written by the thing that served the call, not reconstructed later."""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO logs.api_logs
                    (api_key_id, endpoint, method, status_code, latency_ms,
                     ip_address)
                VALUES (:k, :e, :m, :s, :l, :ip)"""),
                {"k": auth["api_key_id"] if auth else None,
                 "e": str(request.url.path), "m": request.method,
                 "s": status, "l": ms,
                 "ip": client_ip(request)})
            if auth:
                conn.execute(text("""
                    INSERT INTO clients.api_usage
                        (api_key_id, period_start, period_end, calls)
                    VALUES (:k, date_trunc('month', now())::date,
                            (date_trunc('month', now())
                             + interval '1 month - 1 day')::date, 1)
                    ON CONFLICT DO NOTHING"""), {"k": auth["api_key_id"]})
                conn.execute(text("""
                    UPDATE clients.api_usage SET calls = calls + 1,
                           updated_at = now()
                     WHERE api_key_id = :k
                       AND period_start = date_trunc('month', now())::date"""),
                    {"k": auth["api_key_id"]})
    except BaseException as exc:
        # Logging must never take the endpoint down with it.
        print(f"   ! usage logging failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# The one query. NOTE WHAT IT DOES NOT SELECT.
# ---------------------------------------------------------------------------
PARCEL_SQL = text("""
    SELECT p.parcel_ref     AS p_parcel_ref,
           p.project_name   AS p_project_name,
           p.area_sqm       AS p_area_sqm,
           p.listing_status AS p_listing_status,
           p.price_kes      AS p_price_kes,
           ST_Area(p.geom::geography) AS p_area_calc_sqm,
           i.*, s.overall_score, s.residential_score, s.agricultural_score,
           s.commercial_score, s.investment_score, s.score_breakdown,
           s.model_version, s.version AS score_version
      FROM land.parcels p
      LEFT JOIN analytics.parcel_intelligence i
             ON i.parcel_id = p.parcel_id AND i.status = 'active'
      LEFT JOIN analytics.suitability_scores s
             ON s.parcel_id = p.parcel_id AND s.status = 'active'
     WHERE p.parcel_ref = :ref
       AND p.company_id = :cid          -- row-level scope, in SQL not code
       AND p.status = 'active'
     LIMIT 1
""")
# `i.*` would carry p.geom if the join brought it - it does not, because
# parcel_intelligence holds no geometry column. assert_no_geometry() is the
# backstop for the day somebody adds one.
#
# EVERY PARCEL COLUMN IS ALIASED. `p.area_sqm, ... i.*` names a column and
# then splats a table holding a column of the same name; the row is keyed BY
# NAME, the duplicate collapses, and the LAST one wins. In the PDF generator
# that silently sourced the plot size from parcel_intelligence instead of
# land.parcels, and every report printed no acreage at all - no error, no
# warning, just an absent line. Same query shape, same bug, fixed here before
# it could serve a wrong size to a buyer. Nothing to the left of a `.*` goes
# unaliased.


def fetch(company_id, ref):
    with engine.connect() as conn:
        row = conn.execute(PARCEL_SQL, {"ref": ref, "cid": company_id}
                           ).mappings().one_or_none()
    if row is None:
        return None
    r = dict(row)
    parcel = {"parcel_ref": r.get("p_parcel_ref"),
              "project_name": r.get("p_project_name"),
              "area_sqm": r.get("p_area_sqm"),
              "area_calc_sqm": r.get("p_area_calc_sqm")}
    score = {"overall_score": r.get("overall_score"),
             "residential_score": r.get("residential_score"),
             "agricultural_score": r.get("agricultural_score"),
             "commercial_score": r.get("commercial_score"),
             "investment_score": r.get("investment_score"),
             "score_breakdown": r.get("score_breakdown"),
             "model_version": r.get("model_version"),
             "version": r.get("score_version")}
    return build_report(r, score, parcel)


def fetch_listing(company_id, ref):
    """The Phase 1 view: the same row, rendered as a listing rather than a
    report. Deliberately a separate function and NOT a flag on fetch() - the
    two views answer different questions for different readers, and a boolean
    would invite one of them to drift into the other."""
    with engine.connect() as conn:
        row = conn.execute(PARCEL_SQL, {"ref": ref, "cid": company_id}
                           ).mappings().one_or_none()
    if row is None:
        return None
    r = dict(row)
    parcel = {"parcel_ref": r.get("p_parcel_ref"),
              "project_name": r.get("p_project_name"),
              "area_sqm": r.get("p_area_sqm"),           # THE SELLER'S figure
              "listing_status": r.get("p_listing_status"),
              "price_kes": r.get("p_price_kes")}
    score = {"overall_score": r.get("overall_score"),
             "residential_score": r.get("residential_score"),
             "agricultural_score": r.get("agricultural_score"),
             "commercial_score": r.get("commercial_score"),
             "investment_score": r.get("investment_score"),
             "score_breakdown": r.get("score_breakdown"),
             "version": r.get("score_version")}
    sibs = scheme_rows(company_id, r.get("p_project_name"))
    return build_listing(r, score, parcel, sibs)


AUTH_REFUSED = "Unknown, revoked or expired API key."


def guard(raw_key, request):
    auth, why = authenticate(raw_key)
    if not auth:
        # ONE message outward, ALWAYS. The reason is printed, never returned.
        # If this string ever varies by cause it becomes an oracle telling an
        # attacker which keys are real.
        print(f"   ! 401 {request.url.path} - {why}")
        log_call(None, request, 401, 0)
        raise HTTPException(401, AUTH_REFUSED)
    return auth


@app.get("/v1/plots/{ref}")
def plot_json(ref: str, request: Request, x_api_key: str = Header(None)):
    """The report as data. Values only - never geometry."""
    t0 = time.time()
    auth = guard(x_api_key, request)
    rep = fetch(auth["company_id"], ref)
    ms = int((time.time() - t0) * 1000)
    if rep is None:
        # AN UNKNOWN REF IS A 404, NEVER A NEAREST MATCH. Serving the wrong
        # plot's analysis is the worst failure this product has.
        log_call(auth, request, 404, ms)
        raise HTTPException(404, f"No plot '{ref}' for this account. Check the "
                                 f"reference your site sends matches the "
                                 f"parcel_ref agreed at onboarding.")
    try:
        assert_no_geometry(rep)
    except GeometryLeak as e:
        log_call(auth, request, 500, ms)
        raise HTTPException(500, f"Refused to respond: {e}")
    log_call(auth, request, 200, ms)
    return JSONResponse({"api_version": API_VERSION, "plot": rep})


@app.get("/v1/plots/{ref}/embed", response_class=HTMLResponse)
def plot_embed(ref: str, request: Request, x_api_key: str = Header(None)):
    """The rendered fragment a client's page drops in.

    Rendered HERE, not in their browser from our data. That is the whole
    point: they receive a picture of the answer, not the answer's inputs.
    """
    t0 = time.time()
    auth = guard(x_api_key, request)
    rep = fetch_listing(auth["company_id"], ref)
    ms = int((time.time() - t0) * 1000)
    if rep is None:
        log_call(auth, request, 404, ms)
        raise HTTPException(404, f"No plot '{ref}' for this account.")
    # One query for all of it now, validated, instead of report_footer alone.
    b = fetch_branding(auth["company_id"])
    log_call(auth, request, 200, ms)
    return HTMLResponse(listing_html(rep, b["footer"],
                                     api_key=x_api_key,
                                     company_id=auth["company_id"],
                                     branding=b))


TONE_COLOR = {"yes": "#0ca30c", "careful": "#fab219", "no": "#d03b3b",
              "unsure": "#8a948e"}


def render_fragment(rep, branding=None):
    """Server-side render. Self-contained, inherits nothing from the host page."""
    accent = (branding[0] if branding and branding[0] else "#1a7f4b")
    footer = (branding[1] if branding and branding[1] else "")
    css = ("--acc:%s" % accent)
    out = [f'<div class="giq" style="{css}">', """<style>
.giq{font:15px/1.55 ui-sans-serif,system-ui,sans-serif;color:#12211a;
 border:1px solid #e2e6e2;border-radius:14px;padding:18px 20px;background:#fff;max-width:720px}
.giq h3{margin:0 0 4px;font-size:19px}
.giq .sub{color:#54615a;font-size:13.5px;margin:0 0 14px}
.giq .q{border-top:1px solid #eef1ee;padding:13px 0}
.giq .q b{display:block;font-size:15px;margin-bottom:3px}
.giq .a{font-weight:640;margin-bottom:4px}
.giq .why{color:#54615a;font-size:14px;margin:0 0 7px}
.giq .means{background:#f4f6f4;border-radius:9px;padding:10px 12px;font-size:14px}
.giq .chk{margin:14px 0 0;padding-left:19px;font-size:14px;color:#54615a}
.giq .warn{border:1px solid #d03b3b;background:#fdf3f3;border-radius:11px;padding:14px 16px}
.giq .foot{margin-top:15px;padding-top:12px;border-top:1px solid #eef1ee;
 font-size:12px;color:#8a948e;line-height:1.6}
.giq .score{display:inline-block;background:var(--acc);color:#fff;border-radius:9px;
 padding:6px 12px;font-weight:660;font-size:15px}
</style>"""]
    out.append(f'<h3>{rep["ref"] or "Plot"}</h3>')
    if rep.get("size"):
        out.append(f'<p class="sub">{rep["size"]}'
                   + (" (our measurement)" if rep.get("size_measured") else "")
                   + (f' · {rep["project"]}' if rep.get("project") else "")
                   + '</p>')
    if rep["withheld"]:
        out.append(f'<div class="warn"><b>{rep["withheld"]["title"]}</b>'
                   f'<p style="margin:6px 0 0">{rep["withheld"]["text"]}</p></div>')
    else:
        if rep.get("score"):
            s = rep["score"]
            # Strings from report_content, never composed here. The PDF
            # built its own and shipped "Good best suited to residential use".
            out.append(f'<p><span class="score">{s["headline"]}</span>'
                       f' &nbsp;<span class="sub">{s.get("use_line") or ""}'
                       f'</span></p>')
            # A capped use is named in the widget for the same reason it is
            # named in the PDF: the big green number is what a skimmer takes
            # away, and TEST-KANO-01 showed 89 / 100 Good on a plot the model
            # caps at 35 for building because a large part of it floods.
            if s.get("not_for_line"):
                out.append('<p class="warn" style="font-size:14px">'
                           f'<b>{s["not_for_line"]}</b></p>')
        for q in rep["questions"]:
            c = TONE_COLOR.get(q["tone"], "#54615a")
            out.append(f'<div class="q"><b>{q["ask"]}</b>'
                       f'<div class="a" style="color:{c}">{q["answer"]}</div>'
                       f'<p class="why">{q["because"]}</p>'
                       f'<div class="means">{q["means"]}</div></div>')
    if rep["checklist"]:
        out.append('<div class="q"><b>Before you pay</b><ol class="chk">')
        for c in rep["checklist"]:
            out.append(f'<li>{c["do"]}</li>')
        out.append('</ol></div>')
    out.append('<div class="foot">' + " ".join(rep["limits"]) +
               (f'<br>{footer}' if footer else "") +
               '<br>Map data © OpenStreetMap contributors, ODbL. '
               'Analysis by Geocode Spatial Solutions Ltd.</div></div>')
    return "".join(out)


# ---------------------------------------------------------------------------
# THE SELLER'S WIDGET
# ---------------------------------------------------------------------------
# Phase 1 product: facts about the seller's own land, on the seller's own
# page. No refusals, no warnings, no "before you pay". Those belong to the
# Geocode marketplace, where we own the page and the buyer is the reader.
# The long-form reasoning is in report_content.build_listing().
#
# Styles are scoped under .giq and use no framework, no webfont and no
# external request - this is injected into somebody else's live page and must
# not fight their CSS or slow their site down.
# ---------------------------------------------------------------------------
SCHEME_SQL = text("""
    SELECT parcel_ref, listing_status, price_kes, area_sqm
      FROM land.parcels
     WHERE company_id = :cid AND status = 'active'
       AND project_name = :proj
       AND listing_status NOT IN ('hidden', 'cancelled')
     ORDER BY parcel_ref
     LIMIT 60""")


def scheme_rows(company_id, project):
    """Other plots in the same scheme - the availability panel.

    Scoped to the calling company AND the project, so a key can never see
    another client's inventory. Hidden and cancelled plots are excluded
    because the seller withdrew them deliberately.
    """
    if not project:
        return []
    with engine.connect() as conn:
        rows = conn.execute(SCHEME_SQL,
                            {"cid": company_id, "proj": project}).all()
    from report_content import STATUS_WORDS, acres
    return [{"ref": r[0],
             "status": STATUS_WORDS.get(r[1], r[1]),
             "state": r[1],
             "price": (f"KSh {float(r[2]):,.0f}" if r[2] else None),
             "size": acres(r[3])} for r in rows]


# ===========================================================================
# THE INDEX - EVERY PLOT IN A SCHEME, AS CARDS
#
# The seller now embeds TWO things: this on their scheme page, and the plot
# widget on each plot page. One line each, same key.
#
# WHY THE CARD SHOWS THE BEST USE AND NOT JUST THE NUMBER
#   Lesson 42, carried over from the report header. TEST-KANO-01 scores 89
#   overall while its residential score is CAPPED AT 35, because much of it
#   is in the highest flood categories. A card reading "89 - Good" on a page
#   of plots is precisely the skim-read the report guards against, and a grid
#   is nothing BUT skim-reading. So the use travels with the number, always.
#
# WHY BLOCKED PLOTS SHOW NO NUMBER AT ALL
#   Same rule as the scorer: a blocked parcel comes back with NULL scores and
#   a reason, never a low number, because a low number invites a comparison
#   that must not be made. On a card that means "Not rated" and nothing else.
# ===========================================================================

# HOW MANY PLOTS ONE PAGE RENDERS, AND WHY THE NUMBER IS NAMED.
#
# It used to be the bare literal 200, written three times, in the index query,
# the marker query and the ring query. Oak Grove has 688 plots. The widget
# rendered 200 of them, drew 200 on the map, and printed
#
#     "153 of 200 available"
#
# to a buyer, which is not a truncated total. It is a WRONG one. The other 488
# plots did not exist as far as anyone reading that page could tell, and
# nothing anywhere said a limit had been reached.
#
# That is the same failure that put thirteen CAD fragments in this database
# for weeks: a component that keeps what it can carry and never mentions what
# it dropped. So the true count is now fetched separately, always, and the
# page says both numbers whenever they differ.
# 200 was chosen when the largest real scheme held thirteen plots. Oak Grove
# holds 688 and a seller whose page silently omits 488 of them has been sold
# a broken product. A card is a small button, so 688 of them is a page a
# phone renders without complaint; the cost of being generous here is much
# lower than the cost of being quietly wrong.
#
# The limit does not go away, because an unbounded query behind a public
# endpoint is how a page takes a minute to load. It moves to where a scheme
# is genuinely enormous, and the count above makes that case visible instead
# of silent.
INDEX_MAX = 1000

INDEX_SQL = text("""
    SELECT p.parcel_ref, p.project_name, p.listing_status, p.price_kes,
           p.area_sqm, s.overall_score,
           (s.score_breakdown ->> 'best_use') AS best_use
      FROM land.parcels p
      LEFT JOIN analytics.suitability_scores s
             ON s.parcel_id = p.parcel_id AND s.status = 'active'
     WHERE p.company_id = :cid AND p.status = 'active'
       AND p.listing_status NOT IN ('hidden', 'cancelled')
       AND (:proj = '' OR p.project_name = :proj)
     ORDER BY p.project_name NULLS LAST, p.parcel_ref
     LIMIT :lim""")

# Deliberately the same WHERE clause as INDEX_SQL and no LIMIT. If the two
# ever drift apart the page will report a total it is not listing from, which
# is the defect this pair exists to prevent, so they are kept adjacent.
INDEX_COUNT_SQL = text("""
    SELECT count(*) FROM land.parcels p
     WHERE p.company_id = :cid AND p.status = 'active'
       AND p.listing_status NOT IN ('hidden', 'cancelled')
       AND (:proj = '' OR p.project_name = :proj)""")

USE_WORDS = {"residential": "a home", "agricultural": "farming",
             "commercial": "business", "investment": "investment"}


def index_rows(company_id, project=""):
    """-> (cards, total). TOTAL IS NOT len(cards) AND MUST NOT BE TREATED AS IT.

    Returning them as a pair rather than letting the caller measure the list
    is the point: a caller that wants to print a total has to hold the real
    one, and cannot reach for len() and print a number that is really the
    page size.
    """
    p = {"cid": company_id, "proj": project or ""}
    with engine.connect() as conn:
        total = conn.execute(INDEX_COUNT_SQL, p).scalar() or 0
        rows = conn.execute(INDEX_SQL, dict(p, lim=INDEX_MAX)).all()
    from report_content import STATUS_WORDS, acres
    out = []
    for ref, proj, state, price, area, score, best in rows:
        v = float(score) if score is not None else None
        out.append({
            "ref": ref,
            "project": proj,
            "state": state,
            "status": STATUS_WORDS.get(state, state),
            "price": (f"KSh {float(price):,.0f}" if price else None),
            "size": acres(area),
            "score": None if v is None else round(v),
            "label": (None if v is None else
                      "Good" if v >= 75 else "Fair" if v >= 55 else "Poor"),
            "use": USE_WORDS.get(best, best) if best else None,
        })
    return out, total


# One-character labels, because that is all a Google static map marker will
# carry. 1-9 then A-Z gets 35 plots onto a map; past that the markers stay
# and the labels go, since an unlabelled pin is honest and a wrong one is not.
def _marker_label(n):
    if n < 9:
        return str(n + 1)
    if n < 35:
        return chr(ord("A") + n - 9)
    return None


def _scheme_points(company_id, project):
    """[(ref, lon, lat)] in the SAME ORDER as index_rows.

    The order is the whole contract between the map and the cards: marker 3
    is card 3. Both queries sort by project then parcel_ref for that reason,
    and neither may be reordered without the other.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT parcel_ref, ST_X(ST_Centroid(geom)), ST_Y(ST_Centroid(geom))
              FROM land.parcels
             WHERE company_id = :cid AND status = 'active'
               AND listing_status NOT IN ('hidden', 'cancelled')
               AND (:proj = '' OR project_name = :proj)
             ORDER BY project_name NULLS LAST, parcel_ref
             LIMIT :lim"""),
            {"cid": company_id, "proj": project or "",
             "lim": INDEX_MAX}).all()
    return [(r[0], float(r[1]), float(r[2])) for r in rows]


# ===========================================================================
# THE SCHEME MAP - PLOT BOUNDARIES, NUMBERED INSIDE EACH ONE
#
# Pins at a centroid answer "roughly where", which is not the question a
# buyer looking at a subdivision asks. They want to see the SHAPE of plot 3,
# where it sits against plot 4, and which one is on the corner. That needs
# the boundaries drawn, and the number inside the boundary rather than on a
# pin floating above it.
#
# Google's Static Maps API can draw paths, but it cannot put text inside one -
# markers are its only labels, and a marker is a pin. So the satellite base
# comes from Google and THE OVERLAY IS DRAWN HERE, which also means the
# styling is ours and there is no URL-length ceiling on how many plots or how
# detailed their boundaries can be.
#
# THE COORDINATES STILL NEVER REACH A BROWSER. The parcel geometry is read,
# projected to pixels and burned into a JPEG server-side. What leaves this
# process is a picture - which is exactly what rules A4/B4 permit, and the
# reason the overlay is composited here rather than handed to a mapping
# library on the page.
# ===========================================================================

def _world_px(lat, lon, zoom, scale):
    """Web Mercator, the projection Google Static Maps actually uses.

    At zoom z the world is 256 * 2^z pixels square, multiplied by scale.
    Getting this wrong puts the boundaries in a field next to the plots, so
    it is verified against a known point rather than assumed.
    """
    n = 256.0 * (2 ** zoom) * scale
    x = (lon + 180.0) / 360.0 * n
    siny = math.sin(math.radians(lat))
    siny = min(max(siny, -0.9999), 0.9999)
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * n
    return x, y


def _fit_zoom(bbox, w, h, scale, pad=0.12):
    """Largest zoom at which the whole scheme still fits, with a margin.

    Chosen here rather than left to Google, because Google only auto-fits
    around markers and we are no longer using markers.
    """
    (min_lon, min_lat, max_lon, max_lat) = bbox
    for z in range(21, 0, -1):
        x1, y1 = _world_px(max_lat, min_lon, z, scale)
        x2, y2 = _world_px(min_lat, max_lon, z, scale)
        if (abs(x2 - x1) <= w * scale * (1 - pad)
                and abs(y2 - y1) <= h * scale * (1 - pad)):
            return z
    return 1


def _frame_and_zoom(bbox, scale=2, maxdim=640, mindim=200, margin=18):
    """-> (w, h, zoom). The picture is shaped like the land, not like a video.

    THE MEASUREMENT THAT PRODUCED THIS. Oak Grove is 688 plots and, in
    Mercator pixels, almost exactly square. Drawn into the old fixed 640x360
    letterbox the whole scheme only fits at zoom 15, where a 450 m2 plot is
    about eight pixels across and no number can be drawn inside it. Counting
    how many plots could carry a legible number:

        640x360   zoom 15     61 of 688   (9%)
        640x480   zoom 15     61 of 688   (9%)
        640x560   zoom 16    666 of 688   (97%)
        640x640   zoom 16    666 of 688   (97%)

    Half the frame was empty sky and it cost a whole zoom level. Nothing
    about the label drawing changed between those rows. The frame was the
    entire difference between a map that answers "which plot is which" and
    one that does not.

    THE ORDER MATTERS, and getting it the other way round is what the first
    attempt did. Choosing the frame from the scheme's aspect and THEN fitting
    a zoom into it leaves slack, because zoom levels are integers: the
    content lands somewhere between filling the frame and filling a quarter
    of it, and on the first render two thirds of the picture was empty.

    So the zoom is chosen first, as the largest that fits inside the biggest
    frame Google will serve, and the frame is then cut to the content at that
    zoom. The scheme fills the picture by construction rather than by luck.
    """
    # The margin is counted ONCE. The first version tested the content
    # against maxdim*(1-pad) and then also grew the frame by (1+pad), paying
    # for the same gutter twice: Oak Grove came back at zoom 16 in a 335 px
    # frame when it fits inside 640 at zoom 17, which is a factor of two of
    # detail thrown away by an arithmetic slip.
    for zoom in range(21, 0, -1):
        x1, y1 = _world_px(bbox[3], bbox[0], zoom, scale)
        x2, y2 = _world_px(bbox[1], bbox[2], zoom, scale)
        dx, dy = abs(x2 - x1) / scale, abs(y2 - y1) / scale
        if dx + margin <= maxdim and dy + margin <= maxdim:
            w = int(max(mindim, min(maxdim, math.ceil(dx) + margin)))
            h = int(max(mindim, min(maxdim, math.ceil(dy) + margin)))
            return w, h, zoom
    return 640, 360, 1


def _scheme_rings(company_id, project):
    """[(ref, [ring, ...], label_lon, label_lat)] - server-side only.

    ST_PointOnSurface, not ST_Centroid: the centroid of an L-shaped or
    crescent plot falls outside it, and a number printed outside its own
    boundary is worse than no number.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT parcel_ref,
                   ST_AsGeoJSON(geom),
                   ST_X(ST_PointOnSurface(geom)),
                   ST_Y(ST_PointOnSurface(geom))
              FROM land.parcels
             WHERE company_id = :cid AND status = 'active'
               AND listing_status NOT IN ('hidden', 'cancelled')
               AND (:proj = '' OR project_name = :proj)
             ORDER BY project_name NULLS LAST, parcel_ref
             LIMIT :lim"""),
            {"cid": company_id, "proj": project or "",
             "lim": INDEX_MAX}).all()

    out = []
    for ref, gj, lx, ly in rows:
        try:
            g = json.loads(gj)
        except (TypeError, ValueError):
            continue
        polys = ([g["coordinates"]] if g.get("type") == "Polygon"
                 else g.get("coordinates", []))
        rings = [poly[0] for poly in polys if poly and poly[0]]
        if rings:
            out.append((ref, rings, float(lx), float(ly)))
    return out


def _latlon_from_world(x, y, zoom, scale):
    """The inverse of _world_px. Pixel on the scheme map back to a coordinate.

    This exists so a buyer can tap a plot on the picture. The tap arrives as
    a position in the image, and the only way to turn that into a plot is to
    turn it back into a point on the ground and ask the database which parcel
    contains it. Doing that here rather than in the browser is what keeps the
    boundaries off the client: the page never learns where anything is, it
    just reports where the finger landed.
    """
    n = 256.0 * (2 ** zoom) * scale
    lon = x / n * 360.0 - 180.0
    lat_rad = (0.5 - y / n) * 4.0 * math.pi
    lat = math.degrees(math.asin(math.tanh(lat_rad / 2.0)))
    return lat, lon


_FRAME_CACHE = {}
_FRAME_CACHE_MAX = 64


def _scheme_frame_geometry(company_id, project, w=640, h=None, scale=2):
    """The frame only: (w, h, zoom, clat, clon). Cached.

    A tap needs the frame and nothing else, and working it out the long way
    means reading 688 polygons out of the database to look at their extent.
    That is a fine price to pay once when drawing a picture and an absurd one
    to pay every time a buyer's finger lands on it.

    Keyed on _updated_tag, which already changes whenever a parcel in the
    scheme changes, so the cache cannot serve a frame from before a plot
    moved. That would silently resolve taps against a stale picture, which is
    exactly the drift _scheme_frame exists to prevent.
    """
    key = (company_id, project or "", w, h, scale,
           _updated_tag(company_id, project=project))
    if key in _FRAME_CACHE:
        return _FRAME_CACHE[key]
    frame = _scheme_frame(company_id, project, w, h, scale)
    got = None if frame is None else frame[1:]
    if len(_FRAME_CACHE) >= _FRAME_CACHE_MAX:
        _FRAME_CACHE.clear()
    _FRAME_CACHE[key] = got
    return got


def _scheme_frame(company_id, project, w=640, h=None, scale=2):
    """-> (plots, w, h, zoom, clat, clon) or None.

    ONE DEFINITION OF THE PICTURE'S GEOMETRY, USED BY BOTH SIDES.

    The drawing needs it to place boundaries. The tap handler needs it to
    work out what was tapped. If the two ever computed it separately and
    drifted by one zoom level or a few pixels, every tap would quietly
    resolve to the wrong plot and a buyer would be reading the analysis of
    somebody else's land, which is the worst failure this product has. So
    there is one function and both callers use it.
    """
    plots = _scheme_rings(company_id, project)
    if not plots:
        return None
    lons = [p[0] for pl in plots for r in pl[1] for p in r]
    lats = [p[1] for pl in plots for r in pl[1] for p in r]
    if not lons:
        return None
    bbox = (min(lons), min(lats), max(lons), max(lats))
    clat, clon = (bbox[1] + bbox[3]) / 2.0, (bbox[0] + bbox[2]) / 2.0
    if h is None:
        w, h, zoom = _frame_and_zoom(bbox, scale)
    else:
        zoom = _fit_zoom(bbox, w, h, scale)
    return plots, w, h, zoom, clat, clon


def _draw_scheme_map(company_id, project, w=640, h=None, scale=2,
                     detail=False):
    """Satellite base from Google, boundaries and numbers drawn on top.

    h=None means "shaped like the land", which is the default for a reason
    measured rather than guessed. See _frame_and_zoom.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[imagery] Pillow not installed - falling back to pins. "
              "Fix with: pip install Pillow", file=sys.stderr)
        return None

    frame = _scheme_frame(company_id, project, w, h, scale)
    if not frame:
        return None
    plots, w, h, zoom, clat, clon = frame

    # DETAIL: THE SAME GROUND, TWICE THE PIXELS.
    #
    # A picture you can zoom is only worth zooming if there is something
    # underneath. At the fitting zoom a 450 m2 plot is thirteen pixels wide,
    # so magnifying it in the browser magnifies the blur.
    #
    # One zoom level in doubles the pixels per metre. Doubling the frame at
    # the same time keeps the coverage IDENTICAL, which is the property that
    # matters: the tap handler works in fractions of the picture, so as long
    # as both versions frame exactly the same ground, a tap means the same
    # thing on either and there is nothing to keep in step.
    #
    # Google serves at most 640 a side, and the detail frame is twice a base
    # frame that already fits inside 640, so it is exactly four tiles of the
    # base size. No arithmetic about remainders, no seams to line up.
    tiles_xy = None
    if detail:
        tiles_xy = (w, h)
        zoom, w, h = zoom + 1, w * 2, h * 2

    import io

    def _fetch(cy, cx, tw, th):
        url = (f"https://maps.googleapis.com/maps/api/staticmap"
               f"?center={cy:.6f},{cx:.6f}&zoom={zoom}"
               f"&size={tw}x{th}&scale={scale}&maptype=satellite"
               f"&key={GOOGLE_KEY}")
        try:
            body, _ = _http_get(url)
        except Exception as e:                                # noqa: BLE001
            print(f"[imagery] scheme base map failed: {e}", file=sys.stderr)
            return None
        if len(body) < 2000:
            peek = body[:300].decode("utf-8", "replace").replace("\n", " ")
            print(f"[imagery] scheme base map is not an image. Google said: "
                  f"{peek!r}", file=sys.stderr)
            return None
        return Image.open(io.BytesIO(body)).convert("RGBA")

    if tiles_xy is None:
        img = _fetch(clat, clon, w, h)
        if img is None:
            return None
    else:
        # Four quarters, each the size of the base frame. Every tile's centre
        # is worked out in world pixels and turned back into a coordinate, so
        # the quarters butt up exactly rather than approximately.
        tw, th = tiles_xy
        img = Image.new("RGBA", (w * scale, h * scale))
        cx0, cy0 = _world_px(clat, clon, zoom, scale)
        x0 = cx0 - (w * scale) / 2.0
        y0 = cy0 - (h * scale) / 2.0
        for row in range(2):
            for col in range(2):
                tx = x0 + (col + 0.5) * tw * scale
                ty = y0 + (row + 0.5) * th * scale
                tlat, tlon = _latlon_from_world(tx, ty, zoom, scale)
                piece = _fetch(tlat, tlon, tw, th)
                if piece is None:
                    return None
                img.paste(piece, (col * tw * scale, row * th * scale))
    W, H = img.size
    cx, cy = _world_px(clat, clon, zoom, scale)

    def to_px(lon, lat):
        x, y = _world_px(lat, lon, zoom, scale)
        return (x - cx + W / 2.0, y - cy + H / 2.0)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Translucent fill so the ground stays readable through it, and a white
    # outline because a coloured line disappears against vegetation.
    for _ref, rings, _lx, _ly in plots:
        for ring in rings:
            pts = [to_px(pt[0], pt[1]) for pt in ring]
            if len(pts) >= 3:
                d.polygon(pts, fill=(107, 191, 138, 70))
                d.line(pts + [pts[0]], fill=(255, 255, 255, 235), width=3)

    # WHAT NUMBER IS DRAWN, AND WHETHER IT IS DRAWN AT ALL.
    #
    # This used to call _marker_label, which gives up after 35 plots. That cap
    # is real, but it belongs to a GOOGLE STATIC MAP MARKER, which carries one
    # character. This map is composited here with Pillow, where "412" costs
    # exactly what "C" costs. The cap stopped applying the day the drawing
    # moved server-side and nobody moved it; on Oak Grove it would have left
    # 653 of 688 plots unnumbered under a caption promising the numbers match
    # the list.
    #
    # The limit that does apply is the plot's size on screen. At a zoom that
    # fits a 100-acre scheme into 640 points, a 450 m2 plot is about twenty
    # pixels across, and a three-digit number does not fit in twenty pixels at
    # any size a person can read. So the number is sized to its own plot and
    # omitted when it will not fit. That is self-limiting in the right
    # direction: a number appears only where it can be read, and where it
    # cannot, its absence is honest. An unreadable smudge is not.
    _font_cache = {}

    def _font(px):
        px = max(7, min(44, int(px)))
        if px not in _font_cache:
            f = None
            for path in (r"C:\Windows\Fonts\arialbd.ttf",
                         r"C:\Windows\Fonts\arial.ttf",
                         "/usr/share/fonts/truetype/dejavu/"
                         "DejaVuSans-Bold.ttf"):
                try:
                    f = ImageFont.truetype(path, px)
                    break
                except (OSError, IOError):
                    continue
            _font_cache[px] = f or ImageFont.load_default()
        return _font_cache[px]

    # EVERY PLOT GETS ITS NUMBER. 1, 2, 3, to the end of the scheme, whatever
    # the plot's size. The floor used to be 11 and it silently skipped 444 of
    # Oak Grove's 688, which put the map back in the same shape as everything
    # else that went wrong on this scheme: a component quietly keeping what
    # suited it. A small number is small. It is still the plot's number, and
    # the reader can zoom.
    #
    # 7 is not a judgement about legibility, it is the smallest size the font
    # renderer produces anything at. Only a plot with no measurable width at
    # all falls through now.
    floor = 7
    ceiling = 26 if scale > 1 else 14

    # ONE SIZE FOR EVERY NUMBER ON THE MAP.
    #
    # Sizing each number to its own plot was wrong, and not only because it
    # looked untidy. Type size is read as emphasis. A 1.8-acre plot carrying a
    # numeral three times the height of its neighbours tells the eye that plot
    # matters more, and nothing about a plot's area makes its NUMBER more
    # important. The map is an index. An index does not rank its entries.
    #
    # The size is still measured rather than hardcoded, because a thirteen-plot
    # scheme and a 688-plot scheme need different numbers and neither should
    # inherit the other's. Each plot's largest comfortable size is computed as
    # before, and the map then uses one size for all of them: low enough in the
    # distribution that it sits inside most plots, not the smallest, which
    # would let a single sliver shrink the whole scheme to nothing.
    measured = []

    for n, (_ref, _rings, lx, ly) in enumerate(plots):
        lab = str(n + 1)
        if not _rings:
            continue
        ring = [to_px(pt[0], pt[1]) for pt in _rings[0] if len(pt) >= 2]
        if len(ring) < 4:
            continue

        # HOW WIDE IS THIS PLOT, MEASURED HOW.
        #
        # The first version used the axis-aligned bounding box, and on this
        # scheme that was wrong in the worst way: Oak Grove is laid out on a
        # diagonal, so a long thin plot has a box that is large in BOTH
        # directions. Every sliver was sized as though it were a square,
        # and the render came back with "78" and "77" printed at forty
        # pixels across plots eight pixels wide, spilling over their
        # neighbours. Rotate a rectangle and its bounding box stops
        # describing it.
        #
        # Area and perimeter do not care which way the plot is turned, and
        # for a rectangle they RECOVER THE SIDES EXACTLY. The two sides sum
        # to half the perimeter and multiply to the area, so they are the
        # roots of t^2 - (P/2)t + A. A plot drawn at 45 degrees measures the
        # same as one drawn square to the world.
        #
        # 2*area/perimeter was the first attempt and it is not the short
        # side: for a 13 by 25 plot it returns 8.4. It only approaches the
        # short side on something very much longer than it is wide, and a
        # residential plot is not that, so every number came out a third too
        # small and 199 of 200 fell below the legibility floor.
        area2 = 0.0
        perim = 0.0
        for i in range(len(ring) - 1):
            (ax, ay), (bx, by) = ring[i], ring[i + 1]
            area2 += ax * by - bx * ay
            perim += math.hypot(bx - ax, by - ay)
        area = abs(area2) / 2.0
        if area <= 0 or perim <= 0:
            continue
        half = perim / 2.0
        disc = half * half - 4.0 * area
        if disc >= 0:
            root = math.sqrt(disc)
            short, long_ = (half - root) / 2.0, (half + root) / 2.0
        else:
            # Not rectangle-like at all. A square of the same area is the
            # honest fallback and never overstates the room available.
            short = long_ = math.sqrt(area)
        if short <= 0:
            continue

        # The glyphs are about 0.6 em wide, so a 3-digit number needs 1.8 ems
        # of length. Height is capped at 0.8 of the short side so a number
        # that fits sits inside its own boundary rather than on it.
        fits = min(short * 0.8, long_ / (0.62 * len(lab)))
        measured.append((lab, to_px(lx, ly), fits))

    if not measured:
        out = Image.alpha_composite(img, overlay).convert("RGB")
        buf = io.BytesIO()
        out.save(buf, format="JPEG", quality=88)
        return buf.getvalue(), "image/jpeg"

    # The 30th percentile: roughly seven plots in ten hold their number
    # comfortably, and the narrow three in ten carry the same numeral slightly
    # proud of their outline. Taking the minimum instead would let Oak Grove's
    # thinnest sliver decide the type size for all 688, which is one plot
    # setting the legibility of the whole scheme.
    #
    # NO PLOT IS SKIPPED for being too small. Dropping a plot is how a scheme
    # quietly acquires holes, and a buyer standing on one of them has no way
    # to look it up. A number that overhangs is readable and correct; a
    # missing one is neither.
    ranked = sorted(m[2] for m in measured)
    size = int(max(floor, min(ceiling, ranked[int(len(ranked) * 0.30)])))
    font = _font(size)

    # A dark halo, because white-on-satellite is legible over grass and
    # invisible over a tin roof. One size now, so one halo.
    halo = 2 if size >= 20 else 1
    rng = range(-halo, halo + 1)
    for lab, (x, y), _fits in measured:
        for ox in rng:
            for oy in rng:
                if ox or oy:
                    d.text((x + ox, y + oy), lab, font=font,
                           fill=(10, 20, 15, 220), anchor="mm")
        d.text((x, y), lab, font=font, fill=(255, 255, 255, 255), anchor="mm")

    out = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=88)
    return buf.getvalue(), "image/jpeg"


def _updated_tag(company_id, ref=None, project=""):
    """A short hash of when these parcels last changed.

    It does TWO jobs and the second one was missing, which is why a rebuilt
    map kept looking like the old one:

      the cache FILENAME   so the server stops serving a picture of
                           boundaries that have been superseded;
      the image URL        so the BROWSER stops serving one. These responses
                           carry Cache-Control: max-age=86400, which is right
                           - a plot's satellite view does not change hourly -
                           and it means a URL that never changes is a picture
                           that never changes, for a day, no matter what the
                           server does.

    Fixing only the disk cache fixed nothing a person could see.
    """
    q = """SELECT coalesce(max(updated_at), now()) FROM land.parcels
            WHERE company_id = :cid AND status = 'active'"""
    params = {"cid": company_id}
    if ref:
        q += " AND parcel_ref = :ref"
        params["ref"] = ref
    else:
        q += " AND (:proj = '' OR project_name = :proj)"
        params["proj"] = project or ""
    try:
        with engine.connect() as conn:
            stamp = conn.execute(text(q), params).scalar()
        return hashlib.sha256(str(stamp).encode()).hexdigest()[:10]
    except Exception:                                         # noqa: BLE001
        return "nostamp"


def _scheme_map_bytes(company_id, project, detail=False):
    """Boundaries with numbers inside them, or pins if that is not possible.

    The fallback is not decoration: Pillow may be absent, and a scheme whose
    parcels have no usable rings would otherwise render nothing at all. A map
    with pins is worse than a map with boundaries and much better than a gap
    on a client's page.
    """
    if not GOOGLE_KEY:
        return None

    slug = re.sub(r"[^A-Za-z0-9]+", "_", project or "all")[:40]
    pts = _scheme_points(company_id, project)
    if not pts:
        return None

    tag = _updated_tag(company_id, project=project)

    # v3: the frame is no longer 16:9 and the numbers are no longer capped at
    # 35, so every picture drawn before this change is wrong in a way _updated_tag
    # cannot see. The tag tracks the DATA; the version tracks THE DRAWING, and
    # a code change that alters the picture has to bust the cache itself or
    # clients keep the old one for a day.
    # The detail render is a separate file, not a replacement. The small one
    # is what loads with the page and it has to stay quick; the big one is
    # fetched only once somebody actually zooms.
    kind = "detail" if detail else "fit"
    cached = IMG_CACHE / f"scheme_v3_{kind}_{slug}_{len(pts)}_{tag}.jpg"
    if cached.exists() and cached.stat().st_size > 0:
        return cached.read_bytes(), "image/jpeg"

    drawn = _draw_scheme_map(company_id, project, detail=detail)
    if drawn:
        IMG_CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(drawn[0])
        return drawn

    marks = []
    for n, (_ref, lon, lat) in enumerate(pts):
        lab = _marker_label(n)
        style = "size:mid|color:0x1b5e43"
        if lab:
            style += f"|label:{lab}"
        marks.append(f"markers={style}|{lat},{lon}")
    url = ("https://maps.googleapis.com/maps/api/staticmap"
           "?size=640x330&scale=2&maptype=hybrid&"
           + "&".join(marks) + f"&key={GOOGLE_KEY}")
    if len(url) > 15500:
        return None
    return _cached_image(f"scheme_pins_{slug}_{len(pts)}.jpg", url)


@app.get("/v1/scheme/map")
def scheme_map(request: Request, project: str = "", k: str = None,
               detail: int = 0, x_api_key: str = Header(None)):
    auth = guard(x_api_key or k, request)
    got = _scheme_map_bytes(auth["company_id"], project, detail=bool(detail))
    if not got:
        raise HTTPException(404, "No map for this scheme.")
    return Response(content=got[0], media_type=got[1],
                    headers={"Cache-Control": "public, max-age=86400"})


# How far outside a boundary a tap still counts, in metres on the ground.
# Fingers are wider than plot boundaries: on a 688-plot scheme a plot is about
# thirteen pixels across, so a tap aimed at one lands on the line between two
# of them often enough to matter. Ten metres is roughly one plot width here,
# close enough to forgive a near miss and far too small to jump a road.
TAP_TOLERANCE_M = 10.0


# ===========================================================================
# THE ONE DOOR IN THE GEOMETRY FIREWALL
#
# report_content.assert_no_geometry() stands, unchanged, and every analysis
# payload still goes through it. Nothing below weakens it. This is a separate,
# narrow endpoint that is allowed to do the one thing that function forbids,
# and it is written down here rather than discovered later by someone
# wondering why the rule seems to have two answers.
#
# WHAT CHANGED AND WHY
#   Njeri chose a live map over a picture, and there is no version of a live
#   map where the browser does not know the shapes. Panning, zooming and
#   clicking a plot all require the outlines client-side. The picture existed
#   precisely to avoid that, and it is still there as the fallback.
#
# WHY THIS IS NOT THE THING A4 PROTECTS AGAINST
#   A4 is about ODbL. The exposure is DISTRIBUTION of an OpenStreetMap-DERIVED
#   database - above all environment.riparian_buffers, which is derived
#   geometry and unambiguously a database. Hand a client that and share-alike
#   attaches to us.
#
#   A seller's own plot outlines are not derived from anything of ours. They
#   drew them, they sent us the KMZ, they publish the site plan, they run
#   site visits to it every Saturday. Publishing them on that seller's own
#   listing is what the listing is for.
#
# THE LINE, STATED SO IT CAN BE CHECKED
#   leaves      the client's own parcel outlines, for that client's own key
#   never       any layer we derived - soils, rainfall, buffers, amenities,
#               anything from environment.* or analytics.* - in any form
#
#   The query below selects land.parcels.geom and nothing else. If it ever
#   grows a join onto a derived table, that is the moment this stops being
#   defensible, and it should be refused in review on those grounds alone.
#
# WHAT IT COSTS THE CLIENT, WHICH IS THEIR CALL AND NOT OURS
#   A competitor can read the outlines out of the page. A seller should be
#   told that plainly before it is switched on, and it is switched on by the
#   presence of a browser key rather than silently for everyone.
# ===========================================================================
SCHEME_PLOTS_SQL = text("""
    SELECT parcel_ref, listing_status,
           ST_AsGeoJSON(geom, 6) AS g
      FROM land.parcels
     WHERE company_id = :cid AND status = 'active'
       AND listing_status NOT IN ('hidden', 'cancelled')
       AND (:proj = '' OR project_name = :proj)
     ORDER BY project_name NULLS LAST, parcel_ref
     LIMIT :lim""")


@app.get("/v1/scheme/plots")
def scheme_plots(request: Request, project: str = "", k: str = None,
                 x_api_key: str = Header(None)):
    """The outlines, for the live map. See the block above before editing.

    Six decimal places is 0.11 m on the ground. The surveyor's own drawing is
    not that precise, so this rounds away nothing real while roughly halving
    what crosses the wire on a 688-plot scheme.

    The ORDER is the same ORDER BY as index_rows and _scheme_rings, because
    the number on a plot is its position in that list. Three queries now
    depend on that single ordering, and any of them changing it silently
    renumbers the scheme.
    """
    auth = guard(x_api_key or k, request)
    if not GOOGLE_EMBED_KEY:
        raise HTTPException(404, "No browser key configured.")

    out, lo_lat, lo_lon, hi_lat, hi_lon = [], 90.0, 180.0, -90.0, -180.0
    with engine.connect() as conn:
        rows = conn.execute(SCHEME_PLOTS_SQL,
                            {"cid": auth["company_id"], "proj": project or "",
                             "lim": INDEX_MAX}).all()
    for n, (ref, state, gj) in enumerate(rows, 1):
        try:
            g = json.loads(gj)
        except (TypeError, ValueError):
            continue
        polys = ([g["coordinates"]] if g.get("type") == "Polygon"
                 else g.get("coordinates", []))
        rings = [p[0] for p in polys if p and p[0]]
        if not rings:
            continue
        for lon, lat in rings[0]:
            lo_lat, hi_lat = min(lo_lat, lat), max(hi_lat, lat)
            lo_lon, hi_lon = min(lo_lon, lon), max(hi_lon, lon)
        out.append({"n": n, "ref": ref, "state": state, "rings": rings})

    if not out:
        raise HTTPException(404, "No plots in this scheme.")
    return {
        "key": GOOGLE_EMBED_KEY,
        "bounds": {"south": lo_lat, "west": lo_lon,
                   "north": hi_lat, "east": hi_lon},
        "plots": out,
    }


@app.get("/v1/scheme/at")
def scheme_at(request: Request, x: float, y: float, project: str = "",
              k: str = None, x_api_key: str = Header(None)):
    """Which plot is at this point on the scheme picture?

    WHY THE BROWSER ASKS INSTEAD OF KNOWING.

    Making the map clickable the ordinary way means giving the page the shape
    of every plot, as an image map or an overlay. That is the client's parcel
    geometry published on the open internet, and it is exactly what B4 exists
    to prevent.

    So the page sends what it does know, which is where the finger landed as
    a fraction of the picture, and gets back a single parcel reference. The
    coordinates are reconstructed here from the same frame the drawing used,
    and the database answers which parcel contains that point. Nothing about
    any boundary crosses the wire in either direction.

    The reply is a reference and nothing else. It is deliberately not the
    plot's analysis: the browser then requests that through the same endpoint
    a card click uses, so there is one path to a plot's detail rather than
    two that can disagree.
    """
    auth = guard(x_api_key or k, request)
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise HTTPException(400, "x and y are fractions of the image, 0 to 1.")

    frame = _scheme_frame_geometry(auth["company_id"], project)
    if not frame:
        raise HTTPException(404, "No map for this scheme.")
    w, h, zoom, clat, clon = frame

    scale = 2
    cx, cy = _world_px(clat, clon, zoom, scale)
    px = cx - (w * scale) / 2.0 + x * w * scale
    py = cy - (h * scale) / 2.0 + y * h * scale
    lat, lon = _latlon_from_world(px, py, zoom, scale)

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT parcel_ref
              FROM land.parcels
             WHERE company_id = :cid AND status = 'active'
               AND listing_status NOT IN ('hidden', 'cancelled')
               AND (:proj = '' OR project_name = :proj)
               AND ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
             LIMIT 1"""),
            {"cid": auth["company_id"], "proj": project or "",
             "lon": lon, "lat": lat}).one_or_none()

        # A tap that lands on a boundary or a footpath belongs to the nearest
        # plot, within one plot's width. Beyond that it belongs to nothing:
        # returning the closest parcel to a tap in an empty field would show
        # a buyer analysis for land they were not pointing at, and a tap that
        # does nothing is the honest outcome.
        if row is None:
            row = conn.execute(text("""
                SELECT parcel_ref
                  FROM land.parcels
                 WHERE company_id = :cid AND status = 'active'
                   AND listing_status NOT IN ('hidden', 'cancelled')
                   AND (:proj = '' OR project_name = :proj)
                   AND ST_DWithin(geom::geography,
                                  ST_SetSRID(ST_MakePoint(:lon, :lat),
                                             4326)::geography, :tol)
                 ORDER BY geom::geography <->
                          ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                 LIMIT 1"""),
                {"cid": auth["company_id"], "proj": project or "",
                 "lon": lon, "lat": lat, "tol": TAP_TOLERANCE_M}).one_or_none()

    if row is None:
        raise HTTPException(404, "No plot at that point.")
    return {"ref": row[0]}


def index_html(rows, api_key="", project="", company_id=None,
               branding=None, total=None):
    if not rows:
        return ('<div class="giq"><div class="slot">'
                'No plots are listed here yet.</div></div>')

    o = ['<div class="giq giq-ix"><style>', CSS, '</style>']
    o.append(seller_strip(branding or {}))
    shown = len(rows)
    total = shown if total is None else int(total)
    more = max(0, total - shown)
    head = esc(project) if project else "All plots"

    # WHAT THIS LINE MAY SAY.
    #
    # It used to read "{available} of {len(rows)} available", and with the
    # page capped at 200 that second number was the page size wearing a
    # total's clothes. On a 688-plot scheme it told a buyer the scheme had
    # 200 plots. We do not print a number we cannot source, and the size of
    # the scheme is exactly the kind of number a buyer repeats to a seller.
    #
    # So when the page is showing everything, it counts what is available.
    # When it is not, it says so in the same breath, because a buyer who
    # cannot see all the plots needs to know that more than we need the
    # sentence to be tidy.
    if more:
        o.append(f'<div class="hd"><div><h3>{head}</h3>'
                 f'<p class="loc">Showing {shown} of {total} plots</p>'
                 f'</div></div>')
    else:
        open_n = sum(1 for r in rows if r["state"] == "available")
        o.append(f'<div class="hd"><div><h3>{head}</h3>'
                 f'<p class="loc">{open_n} of {total} available</p>'
                 f'</div></div>')

    # THE MAP GOES FIRST. A buyer looking at a scheme wants to know where the
    # plots are before anything else, and the numbers on the pins are what
    # tie the picture to the list underneath.
    # THE LIVE MAP, WHEN THERE IS A BROWSER KEY TO DRIVE IT.
    #
    # An empty container and nothing else: no outlines in the markup, no
    # coordinates, no picture. The loader fills it from /v1/scheme/plots once
    # the page is up. If Google fails to load, or the key is wrong, or the
    # buyer is behind something that blocks it, the loader puts the drawn
    # picture back in the same box. A scheme listing must never be a blank
    # rectangle, whatever else has gone wrong.
    if GOOGLE_EMBED_KEY and company_id is not None:
        fb = f"?k={esc(api_key)}" if api_key else "?"
        if project:
            fb += f"&project={esc(project)}"
        fb += f"&v={_updated_tag(company_id, project=project)}"
        o.append(f'<div class="smap smaplive" data-giq-livemap '
                 f'data-giq-project="{esc(project or "")}" '
                 f'data-giq-fallback="/v1/scheme/map{fb}">'
                 f'<div class="smapc">Loading the map</div></div>')
    elif GOOGLE_KEY and company_id is not None:
        if _scheme_map_bytes(company_id, project):
            q = f"?k={esc(api_key)}" if api_key else "?"
            if project:
                q += f"&project={esc(project)}"
            q += f"&v={_updated_tag(company_id, project=project)}"
            # Clicking opens Google Maps centred on the scheme, where a buyer
            # can pan, zoom and switch to the road map. Centred on the first
            # plot, because that is the scheme's own ordering and any
            # computed centroid of a straggling scheme lands in a field.
            # "Numbers match the list below" was true of five plots. On a
            # scheme where a plot is twenty pixels wide, most plots carry no
            # number, and a caption that promises one is a promise the picture
            # does not keep. NUMBERED plots match; the caption now says only
            # that, and says plainly when the map is not showing everything.
            cap = "Drag to move, + and - to zoom, tap a plot to open it"
            if more:
                cap = (f"Drag, zoom, tap a plot. Showing the first {shown} "
                       f"of {total}")
            pts = _scheme_points(company_id, project)
            open_link = ""
            if pts:
                _r, lon0, lat0 = pts[0]
                open_link = (f'<a class="smapo" href="{esc(_gmaps_view(lat0, lon0))}" '
                             f'target="_blank" rel="noopener noreferrer">'
                             f'Open in Google Maps</a>')
            # data-giq-map is what the loader binds the tap to, and it carries
            # the project so the tap is resolved against the same scheme the
            # picture was drawn from. The <img> stays a plain image: no image
            # map, no overlay, no coordinates in the markup.
            # data-giq-detail is the same picture at twice the resolution,
            # over exactly the same ground. The loader swaps it in the first
            # time somebody zooms, so the page still loads with the small
            # one and only pays for the big one if it is wanted.
            o.append(f'<div class="smap"><img loading="lazy" data-giq-map '
                     f'data-giq-project="{esc(project or "")}" '
                     f'data-giq-detail="/v1/scheme/map{q}&detail=1" '
                     f'alt="Map of the plots in this scheme. '
                     f'Tap a plot to open it." '
                     f'src="/v1/scheme/map{q}">'
                     f'<div class="smapz">'
                     f'<button type="button" data-giq-zoom="in" '
                     f'aria-label="Zoom in">+</button>'
                     f'<button type="button" data-giq-zoom="out" '
                     f'aria-label="Zoom out">&#8722;</button>'
                     f'<button type="button" data-giq-zoom="reset" '
                     f'aria-label="Fit the whole scheme">&#9633;</button>'
                     f'</div>'
                     f'<div class="smapc">{esc(cap)}{open_link}</div></div>')

    o.append('<div class="grid">')
    for n, r in enumerate(rows):
        gone = "" if r["state"] == "available" else " gone"
        # data-giq-plot is what the loader listens for. A card is a button,
        # not a link: there is no URL on the seller's site we could guess,
        # and inventing one would break their page.
        o.append(f'<button class="card{gone}" type="button" '
                 f'data-giq-plot="{esc(r["ref"])}">')
        # The same number the map draws. It used to be _marker_label, which
        # runs out at 35, so on a large scheme the map would show "412" over a
        # plot whose card carried no number at all. The badge and the map are
        # one contract or they are noise.
        pin = f'<span class="pin">{n + 1}</span>'
        o.append(f'<span class="cref">{pin}{esc(r["ref"])}</span>')
        o.append(f'<span class="pill{gone}">{esc(r["status"])}</span>')
        bits = [x for x in (r["size"], r["price"]) if x]
        if bits:
            o.append(f'<span class="cmeta">{esc(" · ".join(bits))}</span>')
        if r["score"] is None:
            o.append('<span class="cscore none">Not rated</span>')
        else:
            use = f' · best for {esc(r["use"])}' if r["use"] else ""
            o.append(f'<span class="cscore"><b>{r["score"]}</b> '
                     f'{esc(r["label"])}{use}</span>')
        o.append('</button>')
    o.append('</div>')
    o.append('<div class="ixf">Tap a plot to see what the land is.</div>')
    o.append('</div>')
    return "".join(o)


DEMO_PAGE = BASE / "demo_page.html"


@app.get("/demo", response_class=HTMLResponse)
def demo(k: str = "", site: str = ""):
    """A stand-in seller's page, served from this origin.

    It exists so that testing needs no file editing. Because the page comes
    from the same host as the widget, its script tag is a relative path and
    the tunnel hostname - which changes on every restart - is never written
    into a file. The same URL works on localhost and through the tunnel.

    The key arrives in the query string and is echoed into the page, escaped.
    That is not a hole: it is the key the page would carry anyway, and it is
    checked on every widget call exactly as it always is. Nothing here is
    authenticated, because nothing here is data - it is scenery around two
    empty divs.
    """
    page = DEMO_PAGE
    if site:
        # A per-prospect demo page. The file is picked by name, and the name
        # is scrubbed to letters and digits first: this route is public and
        # unauthenticated, so an unfiltered value here would let anyone read
        # any file on the disk by asking for ../../.env.
        safe = re.sub(r"[^A-Za-z0-9_-]", "", site)[:40]
        cand = BASE / f"demo_{safe}.html"
        if not safe or not cand.exists():
            raise HTTPException(404, f"No demo page for '{site}'.")
        page = cand
    if not page.exists():
        raise HTTPException(404, "demo_page.html is missing.")
    if not k:
        return HTMLResponse(
            "<pre style='font:14px/1.6 monospace;padding:28px'>"
            "Add an API key to the address.\n\n"
            "  /demo?k=pk_test_...\n\n"
            "Mint one with:  python mint_key.py --company \"ZZ TEST\""
            "</pre>", status_code=400)
    html = page.read_text(encoding="utf-8").replace("{{KEY}}", esc(k))
    return HTMLResponse(html)


@app.get("/v1/scheme/embed", response_class=HTMLResponse)
def scheme_embed(request: Request, project: str = "", k: str = None,
                 x_api_key: str = Header(None)):
    """Every plot this key can see, as a grid. The scheme-page half."""
    t0 = time.time()
    auth = guard(x_api_key or k, request)
    rows, total = index_rows(auth["company_id"], project)
    ms = int((time.time() - t0) * 1000)
    log_call(auth, request, 200, ms)
    return HTMLResponse(index_html(rows, x_api_key or k or "", project,
                                   auth["company_id"],
                                   fetch_branding(auth["company_id"]),
                                   total=total))


CSS = """
.giq{--ink:#16201b;--dim:#5c6a62;--line:#e2e6e0;--bg:#fff;--soft:#f4f7f4;
 --brand:#1b5e43;--brandsoft:#e7f0ea;--warn:#a85e24;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
 color:var(--ink);line-height:1.5;font-size:15px;background:var(--bg);
 border:1px solid var(--line);border-radius:10px;overflow:hidden;
 max-width:100%;box-sizing:border-box}
.giq *{box-sizing:border-box}
.giq .hd{display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap;
 align-items:flex-start;padding:18px 20px;border-bottom:1px solid var(--line)}
.giq .hd h3{margin:0 0 3px;font-size:19px;font-weight:650;letter-spacing:-.01em}
.giq .hd .loc{margin:0;font-size:13.5px;color:var(--dim)}
.giq .dial{display:flex;align-items:center;gap:11px}
.giq .dial svg{width:62px;height:62px;transform:rotate(-90deg);flex:none}
.giq .dial .n{font-size:24px;font-weight:700;line-height:1;letter-spacing:-.02em}
.giq .dial .l{font-size:12px;color:var(--dim);margin-top:2px}
.giq .keys{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
 gap:1px;background:var(--line)}
.giq .key{background:var(--bg);padding:13px 16px}
.giq .key .k{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
 color:var(--dim);font-weight:650;margin-bottom:4px}
.giq .key .v{font-size:16px;font-weight:650;letter-spacing:-.01em}
.giq .key .n{font-size:12px;color:var(--dim);margin-top:3px;line-height:1.4}
.giq .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));
 gap:1px;background:var(--line);border-top:1px solid var(--line)}
.giq .col{background:var(--bg);padding:15px 18px 17px}
.giq .col h4{margin:0 0 10px;font-size:10.5px;letter-spacing:.09em;
 text-transform:uppercase;color:var(--dim);font-weight:650}
.giq .r{display:flex;justify-content:space-between;gap:10px;padding:5px 0;
 font-size:13.5px;border-bottom:1px solid var(--soft)}
.giq .r:last-child{border-bottom:0}
.giq .r span{color:var(--dim);text-align:right;white-space:nowrap}
.giq .r b{font-weight:500}
.giq .slot{background:var(--soft);border-top:1px solid var(--line);
 padding:26px 20px;text-align:center;color:var(--dim);font-size:13px}
.giq .seller{--seller:var(--brand);display:flex;align-items:center;gap:10px;
 flex-wrap:wrap;padding:9px 20px;background:var(--soft);
 border-bottom:1px solid var(--line);border-left:3px solid var(--seller);
 font-size:12px;color:var(--dim)}
.giq .seller .slogo{height:22px;width:auto;max-width:120px;object-fit:contain;
 display:block}
.giq .seller .sname{font-weight:600;color:var(--ink)}
.giq .seller .sby{margin-left:auto;letter-spacing:.05em;
 text-transform:uppercase;font-size:10.5px;font-weight:650;
 color:var(--brand);white-space:nowrap}
.giq .imgs{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
 gap:1px;background:var(--line);border-top:1px solid var(--line)}
.giq .imgs .tile{display:block;margin:0;background:var(--bg);position:relative;
 text-decoration:none;color:inherit}
.giq .imgs img{display:block;width:100%;height:auto;aspect-ratio:16/9;
 object-fit:cover;background:var(--soft)}
.giq .imgs .cap{position:absolute;left:0;bottom:0;right:0;
 display:flex;justify-content:space-between;align-items:center;gap:10px;
 padding:7px 11px;font-size:11px;letter-spacing:.05em;text-transform:uppercase;
 color:#fff;background:linear-gradient(transparent,rgba(0,0,0,.68))}
.giq .imgs .cap em{font-style:normal;font-weight:600;opacity:.85;
 white-space:nowrap}
.giq .imgs .tile:hover .cap em{text-decoration:underline;opacity:1}
.giq .imgs .tile:focus-visible{outline:2px solid var(--brand);outline-offset:-2px}
.giq .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));
 gap:1px;background:var(--line)}
.giq .card{display:grid;gap:5px;text-align:left;background:var(--bg);
 border:0;padding:15px 17px 17px;font:inherit;color:inherit;cursor:pointer;
 transition:background .12s}
.giq .card:hover{background:var(--soft)}
.giq .card:focus-visible{outline:2px solid var(--brand);outline-offset:-2px}
.giq .card .cref{font-weight:650;font-size:15.5px;letter-spacing:-.01em}
.giq .card .cmeta{font-size:13px;color:var(--dim)}
.giq .card .cscore{font-size:13px;color:var(--dim);margin-top:3px}
.giq .card .cscore b{font-size:17px;color:var(--brand);font-weight:700}
.giq .card .cscore.none{font-style:italic}
.giq .card.gone{opacity:.62}
.giq .card .pill{justify-self:start}
.giq .ixf{padding:11px 20px;font-size:12px;color:var(--dim);
 border-top:1px solid var(--line);background:var(--soft)}
.giq .smap{position:relative;border-top:1px solid var(--line);
 border-bottom:1px solid var(--line);background:var(--soft)}
/* NO FIXED ASPECT RATIO, AND NO object-fit:cover. The picture is now shaped
   like the scheme (see _frame_and_zoom), and cover would crop a square site
   back into a letterbox - throwing away the plots at the top and bottom,
   which on Oak Grove is most of them. The server decides the shape; the page
   shows what it was sent. */
.giq .smap img{display:block;width:100%;height:auto}
/* The scheme map is a window onto a bigger picture. overflow:hidden is what
   makes it pan instead of pushing the client's page sideways, and
   touch-action:none stops a phone reading a drag on it as a page scroll. */
.giq .smap{overflow:hidden}
.giq .smap img[data-giq-map]{cursor:grab;transform-origin:0 0;
 touch-action:none;-webkit-user-select:none;user-select:none}
.giq .smap img[data-giq-map].giq-drag{cursor:grabbing}
.giq .smapz{position:absolute;top:10px;right:10px;display:flex;
 flex-direction:column;gap:5px;z-index:2}
.giq .smapz button{width:32px;height:32px;border:0;border-radius:6px;
 background:rgba(12,22,16,.72);color:#fff;font-size:17px;line-height:1;
 cursor:pointer;font-family:inherit;padding:0}
.giq .smapz button:hover{background:rgba(12,22,16,.92)}
/* The live map needs a height of its own: it has no image inside it to give
   it one. Tall enough to read a scheme, capped so it never eats a phone. */
.giq .smaplive{height:min(72vh,560px);background:var(--soft)}
.giq .smaplive .gm-style img{max-width:none}
.giq .smaplive .smapc{pointer-events:none}
.giq .smaplive .smapc a{pointer-events:auto}
/* The satellite / map switch on the plot page. */
.giq .livet{position:absolute;top:10px;left:10px;display:flex;gap:0;z-index:2;
 border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.3)}
.giq .livet button{border:0;padding:7px 13px;font-size:11px;font-family:inherit;
 letter-spacing:.04em;text-transform:uppercase;cursor:pointer;
 background:rgba(255,255,255,.92);color:#1b3a2a}
.giq .livet button.on{background:#14532d;color:#fff}
/* The interactive map. A fixed aspect rather than a fixed height, so it is
   not a letterbox slot on a phone and not a wall on a desktop. */
.giq .live{position:relative;border-top:1px solid var(--line)}
.giq .live iframe{display:block;width:100%;aspect-ratio:4/3;max-height:420px;
 border:0}
/* Every pane is the same shape, so switching between them does not make the
   client's page jump by a couple of hundred pixels under the reader. */
.giq .live [data-giq-pane]{position:relative}
.giq .live [data-giq-pane] .tile{display:block;position:relative;
 text-decoration:none}
.giq .live [data-giq-pane] img{display:block;width:100%;aspect-ratio:4/3;
 max-height:420px;object-fit:cover}
.giq .live [data-giq-pane][hidden]{display:none}
.giq .livec{padding:7px 12px;font-size:11px;letter-spacing:.05em;
 text-transform:uppercase;color:var(--muted);background:var(--soft);
 border-top:1px solid var(--line);display:flex;
 justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
/* Attribution is a licence condition, not decoration. It is quiet but it is
   never hidden, and it never gets display:none. */
.giq .livec a{color:var(--muted);text-decoration:none;white-space:nowrap}
.giq .livec a:hover{text-decoration:underline}
.giq .smapc{position:absolute;left:0;right:0;bottom:0;padding:7px 12px;
 display:flex;justify-content:space-between;align-items:center;gap:10px;
 font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:#fff;
 background:linear-gradient(transparent,rgba(0,0,0,.66))}
.giq .smapo{color:#fff;font-weight:600;text-decoration:none;white-space:nowrap;
 opacity:.9}
.giq .smapo:hover{text-decoration:underline;opacity:1}
.giq .card .pin{display:inline-flex;align-items:center;justify-content:center;
 width:20px;height:20px;margin-right:8px;border-radius:50%;
 background:var(--brand);color:#fff;font-size:11.5px;font-weight:700;
 vertical-align:middle}
.giq .back{display:inline-flex;align-items:center;gap:6px;background:none;
 border:0;font:inherit;font-size:13.5px;font-weight:600;color:var(--brand);
 cursor:pointer;padding:12px 20px}
.giq .back:hover{text-decoration:underline}
.giq .acts{display:flex;gap:9px;flex-wrap:wrap;padding:14px 20px;
 border-top:1px solid var(--line)}
.giq .acts a{font-size:13.5px;font-weight:600;text-decoration:none;
 padding:9px 15px;border-radius:6px;border:1px solid var(--brand);
 color:var(--brand)}
.giq .acts a.p{background:var(--brand);color:#fff}
.giq .sch{border-top:1px solid var(--line);padding:15px 20px}
.giq .sch .top{display:flex;justify-content:space-between;gap:12px;
 flex-wrap:wrap;align-items:baseline;margin-bottom:9px}
.giq .sch .top b{font-size:15px}
.giq .pill{display:inline-block;font-size:11px;font-weight:650;padding:2px 8px;
 border-radius:20px;background:var(--brandsoft);color:var(--brand)}
.giq .pill.gone{background:#eef0ee;color:#7c877f}
.giq .pill.dep{background:#f7ede2;color:var(--warn)}
.giq .ft{padding:11px 20px;border-top:1px solid var(--line);
 font-size:11.5px;color:var(--dim);background:var(--soft)}
@media (prefers-color-scheme:dark){
 .giq{--ink:#e9ede6;--dim:#a2afa6;--line:#2a342d;--bg:#141a16;--soft:#1b221d;
      --brand:#5fb18c;--brandsoft:#16281f;--warn:#d2914f}
 .giq .pill.gone{background:#232a25;color:#8b968d}
 .giq .r{border-bottom-color:#1e2620}
}
"""


def esc(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ===========================================================================
# SATELLITE AND STREET VIEW
#
# WHY THE SERVER FETCHES THESE AND THE BROWSER NEVER SEES A COORDINATE
#
#   The obvious way to put a satellite image on a page is an <img> pointing
#   at Google with the parcel's latitude and longitude in the URL. That would
#   publish the parcel's position into a page we do not control, which is
#   exactly what rules A4/B4 forbid and what assert_no_geometry() exists to
#   prevent. A point is geometry.
#
#   So the browser asks US for /v1/plots/<ref>/satellite, we look the
#   coordinate up server-side, fetch the picture from Google, and stream back
#   the bytes. The client receives a JPEG. The coordinate never leaves this
#   process, and the same firewall that governs the values governs the
#   imagery.
#
# WHY THE IMAGES ARE CACHED ON DISK
#
#   Google bills per request. A widget on a busy listing page would otherwise
#   bill once per page view, forever, for a picture of ground that does not
#   move. Cached by parcel_ref, and a parcel's position is not a thing that
#   changes - if it did, the parcel is superseded and gets a new id anyway.
#
# WHY THE KEY TRAVELS IN THE QUERY STRING HERE
#
#   An <img> tag cannot send an X-API-Key header. The embed key is already
#   public - it sits in the client's page source, which is what an embed key
#   IS - so putting it in an image URL discloses nothing new. It is still
#   checked exactly as the other endpoints check it, and rate limiting will
#   cover both when it is built.
# ===========================================================================

GOOGLE_KEY = (os.getenv("GOOGLE_MAPS_KEY") or "").strip()

# A SECOND KEY, AND WHY IT IS NOT OPTIONAL.
#
# GOOGLE_MAPS_KEY never leaves this server. Every picture is fetched here and
# streamed to the browser, so the key stays behind the API and a stranger
# cannot spend her Google credit with it. That is deliberate and it is why
# the imagery is proxied at all.
#
# An embedded interactive map is different in kind: the iframe URL carries a
# key and that URL sits in the page source of a public listing, where anyone
# can read it. Putting GOOGLE_MAPS_KEY there would publish the key that bills
# Static Maps and Street View on every plot page on the internet.
#
# So the interactive map uses its OWN key and there is no fallback to the
# server key. If GOOGLE_MAPS_EMBED_KEY is unset the map simply does not
# appear. In the Google Cloud console that key must be restricted to the Maps
# Embed API only, and to the seller's domains. The Embed API is not billed,
# so a restricted embed key that leaks costs nothing, which is the whole
# point of separating them.
GOOGLE_EMBED_KEY = ((os.getenv("GOOGLE_MAPS_BROWSER_KEY")
                     or os.getenv("GOOGLE_MAPS_EMBED_KEY") or "").strip())
if GOOGLE_EMBED_KEY and GOOGLE_EMBED_KEY == GOOGLE_KEY:
    print("[imagery] GOOGLE_MAPS_EMBED_KEY is the same value as "
          "GOOGLE_MAPS_KEY. Refusing to use it: that would publish the "
          "billed key in every listing's page source. Create a second key "
          "restricted to the Maps Embed API.", file=sys.stderr)
    GOOGLE_EMBED_KEY = ""

IMG_CACHE = BASE / "cache" / "img"
IMG_TIMEOUT = 12

SAT_URL = ("https://maps.googleapis.com/maps/api/staticmap"
           "?center={lat},{lon}&zoom=17&size=640x360&scale=2"
           "&maptype=satellite&key={key}")
SV_URL = ("https://maps.googleapis.com/maps/api/streetview"
          "?location={lat},{lon}&size=640x360&fov=80&key={key}")
SV_META = ("https://maps.googleapis.com/maps/api/streetview/metadata"
           "?location={lat},{lon}&key={key}")


def _parcel_point(company_id, ref):
    """(lon, lat) of the parcel centroid. NEVER returned to a caller."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT ST_X(ST_Centroid(geom)), ST_Y(ST_Centroid(geom))
              FROM land.parcels
             WHERE company_id = :c AND parcel_ref = :r AND status = 'active'
             LIMIT 1"""), {"c": company_id, "r": ref}).one_or_none()
    return (float(row[0]), float(row[1])) if row else None


def _http_get(url):
    """-> (body, content_type). Raises, but with GOOGLE'S OWN WORDS attached.

    urllib raises HTTPError on a 4xx and the message is "HTTP Error 403:
    Forbidden", which says nothing. Google puts the actual reason in the
    RESPONSE BODY - "billing has not been enabled", "this API project is not
    authorized to use this API", "the provided API key is expired" - and that
    sentence is the whole diagnosis. Throwing it away turns a five-second fix
    into an afternoon.
    """
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(url, timeout=IMG_TIMEOUT) as r:
            return r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace").strip()[:400]
        except Exception:                                     # noqa: BLE001
            pass
        raise RuntimeError(f"HTTP {e.code} from Google - {detail or e.reason}")


def _cached_image(name, url):
    """-> (bytes, content_type) or None. Disk first, Google once."""
    IMG_CACHE.mkdir(parents=True, exist_ok=True)
    path = IMG_CACHE / name
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes(), "image/jpeg"
    try:
        body, ctype = _http_get(url)
    except Exception as e:                                    # noqa: BLE001
        print(f"[imagery] fetch failed for {name}: {e}", file=sys.stderr)
        return None
    # Google answers some errors with a 200 and a tiny image saying so, and
    # others with plain text. Anything this small is not a photograph and must
    # not be cached as one - but print what came back, because that is the
    # only place the reason exists.
    if len(body) < 2000:
        peek = body[:300].decode("utf-8", "replace").replace("\n", " ")
        print(f"[imagery] {name}: only {len(body)} bytes, not an image. "
              f"Google said: {peek!r}", file=sys.stderr)
        return None
    path.write_bytes(body)
    return body, ctype or "image/jpeg"


def _streetview_ok(ref, lat, lon):
    """Does Street View actually cover this spot?

    Most Kenyan land for sale is not on a Street View road, and Google
    answers that with a grey 'no imagery' placeholder rather than an error.
    Putting that on a client's listing looks broken. The metadata endpoint is
    free and answers the question properly, so it is asked first and the
    answer is cached beside the images.
    """
    if not GOOGLE_KEY:
        return False
    IMG_CACHE.mkdir(parents=True, exist_ok=True)
    flag = IMG_CACHE / f"{ref}.sv.txt"
    if flag.exists():
        return flag.read_text().strip() == "OK"
    try:
        body, _ = _http_get(SV_META.format(lat=lat, lon=lon, key=GOOGLE_KEY))
        status = json.loads(body.decode()).get("status", "")
    except Exception as e:                                    # noqa: BLE001
        print(f"[imagery] street view metadata failed: {e}", file=sys.stderr)
        return False
    flag.write_text(status)
    return status == "OK"


def _img_endpoint(ref, company_id, kind):
    pt = _parcel_point(company_id, ref)
    if not pt or not GOOGLE_KEY:
        return None
    lon, lat = pt
    if kind == "satellite":
        return _cached_image(f"{ref}.sat.jpg",
                             SAT_URL.format(lat=lat, lon=lon, key=GOOGLE_KEY))
    if not _streetview_ok(ref, lat, lon):
        return None
    return _cached_image(f"{ref}.sv.jpg",
                         SV_URL.format(lat=lat, lon=lon, key=GOOGLE_KEY))


@app.get("/v1/plots/{ref}/satellite")
def plot_satellite(ref: str, request: Request, k: str = None,
                   x_api_key: str = Header(None)):
    auth = guard(x_api_key or k, request)
    got = _img_endpoint(ref, auth["company_id"], "satellite")
    if not got:
        raise HTTPException(404, "No satellite image for this plot.")
    return Response(content=got[0], media_type=got[1],
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/v1/plots/{ref}/streetview")
def plot_streetview(ref: str, request: Request, k: str = None,
                    x_api_key: str = Header(None)):
    auth = guard(x_api_key or k, request)
    got = _img_endpoint(ref, auth["company_id"], "streetview")
    if not got:
        raise HTTPException(404, "No street view for this plot.")
    return Response(content=got[0], media_type=got[1],
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------
# LINKING OUT TO GOOGLE MAPS, AND WHY THAT IS NOT A BREACH OF B4
#
# A static tile cannot pan or zoom, and "Get directions" cannot work, unless
# the plot's coordinate reaches the browser. Rule B4 - ship values and
# pictures, never geometry - is why the images are proxied through this
# server in the first place.
#
# The rule's PURPOSE is ODbL. Checklist A4 is about OpenStreetMap-derived
# layers, above all environment.riparian_buffers, which is derived geometry
# and therefore unambiguously a database. Hand a client those and we have
# conveyed a database; share-alike attaches. That has not changed and must
# not.
#
# A CLIENT'S OWN PARCEL CENTROID IS NOT THAT. They drew it, they sent us the
# KMZ, they publish the location themselves, and they run site visits to it
# every Saturday. Withholding a plot's position from the buyers of that plot
# protects nothing and breaks the single thing a land listing exists to do.
#
# So the line is drawn where the exposure actually is:
#
#   our derived layers      NEVER leave. Unchanged, enforced by
#                           assert_no_geometry() on every payload.
#   the pictures            still fetched server-side and streamed, so no
#                           coordinate is needed to display them.
#   the client's own point  used to build an outbound Google Maps link.
#
# Everything interactive therefore happens in Google Maps proper - which is
# better than a cramped iframe, opens the Maps app on a phone, and costs
# nothing, because the Embed and directions URLs are not billed.
# ---------------------------------------------------------------------------
def _gmaps_view(lat, lon):
    return (f"https://www.google.com/maps/@?api=1&map_action=map"
            f"&center={lat:.6f},{lon:.6f}&zoom=18&basemap=satellite")


def _gmaps_dir(lat, lon):
    return (f"https://www.google.com/maps/dir/?api=1"
            f"&destination={lat:.6f},{lon:.6f}")


def _imagery_html(ref, api_key, company_id):
    """ONE BOX. UP TO THREE VIEWS OF THE SAME PLACE. ONE SWITCH.

    There used to be a still photograph and a movable map stacked on top of
    each other, and Njeri's reaction was the correct one: there is no point
    in there being two. They answer the same question, and a buyer had to
    scroll past the first to reach the second and then wonder which one was
    authoritative.

    So the panel holds up to three views of the same ground and shows one at
    a time:

        Satellite   the imagery
        Map         roads and place names, which is what tells you what is
                    next door and how you would reach it
        Street      the photograph from the nearest road, when there is one

    Every pane is built up front and hidden, not fetched on demand. Switching
    is then instant and, more importantly, an iframe that has already loaded
    is not thrown away and reloaded every time somebody flicks between two
    views to compare them.

    WHICH SOURCE FILLS THE PANES DEPENDS ON WHETHER THERE IS AN EMBED KEY,
    and the buyer should never be able to tell. With one, both map panes are
    Google and both move. Without one, Satellite is our own still picture and
    Map is OpenStreetMap, which moves but has no imagery. Same box, same
    switch, same two labels.
    """
    if not GOOGLE_KEY:
        return ('<div class="slot">Satellite view and Street View appear here '
                'once a Google Maps key is configured.</div>')
    pt = _parcel_point(company_id, ref) if ref else None
    if not pt:
        return ""
    lon, lat = pt
    v = _updated_tag(company_id, ref=ref)
    q = (f"?k={esc(api_key)}&v={v}" if api_key else f"?v={v}")
    view = esc(_gmaps_view(lat, lon))

    tabs, panes, credit = [], [], ""

    def tab(key, label, first):
        cls = ' class="on"' if first else ''
        tabs.append(f'<button type="button" data-giq-view="{key}"{cls}>'
                    f'{label}</button>')

    if GOOGLE_EMBED_KEY:
        base = (f"https://www.google.com/maps/embed/v1/place"
                f"?key={GOOGLE_EMBED_KEY}&q={lat:.6f},{lon:.6f}&zoom=17")
        panes.append(
            f'<div data-giq-pane="sat"><iframe src="{esc(base)}'
            f'&maptype=satellite" loading="lazy" allowfullscreen '
            f'referrerpolicy="no-referrer-when-downgrade" '
            f'title="Satellite map around this plot"></iframe></div>')
        panes.append(
            f'<div data-giq-pane="map" hidden><iframe src="{esc(base)}'
            f'&maptype=roadmap" loading="lazy" allowfullscreen '
            f'referrerpolicy="no-referrer-when-downgrade" '
            f'title="Street map around this plot"></iframe></div>')
    else:
        panes.append(
            f'<div data-giq-pane="sat">'
            f'<a class="tile" href="{view}" target="_blank" '
            f'rel="noopener noreferrer">'
            f'<img loading="lazy" alt="Satellite view of this plot" '
            f'src="/v1/plots/{esc(ref)}/satellite{q}">'
            f'<span class="cap">Satellite view '
            f'<em>Open in Google Maps</em></span></a></div>')
        # About 400 m each way, which is the scale at which a buyer is asking
        # "what is next to it" rather than "where in Kenya is it".
        d = 0.0035
        osm = (f"https://www.openstreetmap.org/export/embed.html"
               f"?bbox={lon - d:.6f},{lat - d:.6f},{lon + d:.6f},{lat + d:.6f}"
               f"&layer=mapnik&marker={lat:.6f},{lon:.6f}")
        panes.append(
            f'<div data-giq-pane="map" hidden><iframe src="{esc(osm)}" '
            f'loading="lazy" allowfullscreen '
            f'referrerpolicy="no-referrer-when-downgrade" '
            f'title="Street map around this plot"></iframe></div>')
        # Attribution is a licence condition of using their embed. It stays
        # visible whichever pane is open, because working out which pane is
        # showing in order to hide a credit is effort spent in the wrong
        # direction.
        credit = ('<a href="https://www.openstreetmap.org/copyright" '
                  'target="_blank" rel="noopener noreferrer">'
                  'Map data \u00a9 OpenStreetMap contributors</a>')

    tab("sat", "Satellite", True)
    tab("map", "Map", False)

    if _streetview_ok(ref, lat, lon):
        sv = esc(f"https://www.google.com/maps/@?api=1&map_action=pano"
                 f"&viewpoint={lat:.6f},{lon:.6f}")
        panes.append(
            f'<div data-giq-pane="street" hidden>'
            f'<a class="tile" href="{sv}" target="_blank" '
            f'rel="noopener noreferrer">'
            f'<img loading="lazy" alt="Street view near this plot" '
            f'src="/v1/plots/{esc(ref)}/streetview{q}">'
            f'<span class="cap">Nearest street view '
            f'<em>Walk around it</em></span></a></div>')
        tab("street", "Street", False)

    return (f'<div class="live">'
            f'<div class="livet">{"".join(tabs)}</div>'
            f'{"".join(panes)}'
            f'<div class="livec">Drag the map to see what is around the plot'
            f'{credit}</div></div>')


def _actions_html(ref, company_id, branding=None):
    """Get directions, and the seller's own call to action.

    On a phone the directions link opens the Google Maps app with the plot as
    destination and the buyer's own position as origin, which is exactly what
    somebody reading a land listing on a matatu is trying to do.
    """
    b = branding or {}
    pt = _parcel_point(company_id, ref) if ref else None
    rows = []
    if pt:
        lon, lat = pt
        rows.append(f'<a class="p" href="{esc(_gmaps_dir(lat, lon))}" '
                    f'target="_blank" rel="noopener noreferrer">'
                    f'Get directions</a>')

    # THE BUTTON EXISTS ONLY WHEN IT WORKS.
    #
    # It pointed at "#" from the day the listing view was built, which was
    # right while there was nowhere for it to go, and becomes a defect the
    # moment a real seller's buyer clicks it. There is now no state in which
    # it is present and dead: no site_visit_url, no button.
    if b.get("visit"):
        rows.append(f'<a href="{esc(b["visit"])}" target="_blank" '
                    f'rel="noopener noreferrer">Book a site visit</a>')

    if not rows:
        return ""
    return '<div class="acts">' + "".join(rows) + '</div>'


# ===========================================================================
# BRANDING - THE SELLER'S NAME ON THE PLOT, NOT ON THE ANALYSIS
#
# THE DECISION THIS IMPLEMENTS
#   The widget could blend into a seller's site - their colours, their fonts,
#   indistinguishable from their own copy. It sells better that way, and it
#   is the wrong choice.
#
#   The product is an INDEPENDENT assessment. A buyer reading "this soil may
#   be black cotton, get a test before you agree a budget" needs to see that
#   the seller did not write it. A panel styled entirely by the seller is a
#   panel the buyer reads as the seller's own marketing, and then the caution
#   is worth nothing - which is also exactly why section 2 keeps the verdicts
#   off a seller's page in the first place.
#
#   So: the seller's identity appears, prominently, attached to THE PLOT.
#   The analysis keeps Geocode's own face.
#
# WHAT THE SELLER CONTROLS AND WHAT THEY DO NOT
#   logo_url, primary_color   the "listed by" strip only
#   site_visit_url            where their own call-to-action goes
#   report_footer             their wording in the footer
#   the analysis panel        nothing. Not the colours, not the words.
#
#   primary_color deliberately does not reach the score dial, the answers or
#   the cards. A seller who can restyle the assessment will eventually
#   restyle it to look like approval.
#
# EVERY VALUE HERE IS CLIENT-CONTROLLED AND GOES INTO HTML OR CSS
#   So each is validated against a whitelist rather than escaped and hoped
#   for. A colour that is not a hex colour, or a URL whose scheme is not
#   expected, is DROPPED - the element is omitted and the panel renders
#   without it. `esc()` protects the text; these checks protect the
#   attributes, which is where escaping alone is not enough.
# ===========================================================================

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_ACTION_SCHEMES = ("https://", "http://", "tel:", "mailto:")


def safe_color(v):
    """A hex colour, or nothing. Never anything else near a style attribute."""
    v = (v or "").strip()
    return v if _HEX.match(v) else None


def safe_img_url(v):
    """https only.

    An http image on an https page is blocked as mixed content, so the tag
    would render as a broken icon on every client site served over TLS -
    which is all of them. Omitting it is better: the company name is always
    rendered beside the logo, so this degrades to text.
    """
    v = (v or "").strip()
    return v if v.lower().startswith("https://") else None


def safe_action_url(v):
    """A link scheme a browser will follow and a person intended.

    javascript: and data: are the reason this is a whitelist and not a
    blacklist. This value comes from a row a client can influence, and it
    lands in an href.
    """
    v = (v or "").strip()
    return v if any(v.lower().startswith(s) for s in _ACTION_SCHEMES) else None


def fetch_branding(company_id):
    """-> dict of validated, render-ready branding. Never raises."""
    blank = {"name": None, "logo": None, "accent": None, "footer": "",
             "visit": None}
    if company_id is None:
        return blank
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT c.name, b.logo_url, b.primary_color, b.report_footer,
                       b.site_visit_url
                  FROM clients.companies c
                  LEFT JOIN clients.branding b ON b.company_id = c.company_id
                 WHERE c.company_id = :c
                 LIMIT 1"""), {"c": company_id}).one_or_none()
    except Exception as e:                                    # noqa: BLE001
        # site_visit_url is absent until v1.12 is applied. A widget that dies
        # because a migration has not run yet is worse than one without a
        # button, so this degrades instead of failing.
        print(f"[branding] {e}", file=sys.stderr)
        return blank
    if not row:
        return blank
    return {"name": row[0],
            "logo": safe_img_url(row[1]),
            "accent": safe_color(row[2]),
            "footer": row[3] or "",
            "visit": safe_action_url(row[4])}


def seller_strip(b):
    """Nothing. Kept as a function on purpose - see below.

    This used to render "Listed by <seller>" beside "Independent analysis by
    Geocode". Njeri removed both, and the reasoning is hers to make: the
    widget sits on the seller's own site, under the seller's own name, so
    "listed by" repeats what the page already said, and the Geocode line puts
    our branding on their listing without being asked.

    IT IS STILL A FUNCTION, and every caller still calls it, because the
    alternative is deleting the calls and rediscovering the whole question
    the first time a client asks to be credited. Making it return nothing is
    one line to reverse. Ripping it out is an afternoon.

    Worth writing down for whoever revisits it: the independence line was not
    decoration. An assessment carried on a seller's page is worth more to a
    buyer if it plainly is not the seller's, and that line was what said so.
    If it comes back, that is why.
    """
    return ""


def listing_html(rep, footer="", api_key="", company_id=None, branding=None):
    b = branding if branding is not None else {"name": None}
    o = ['<div class="giq"><style>', CSS, '</style>']
    o.append(seller_strip(b))

    # ---- header: identity, and the score if this plot has one -------------
    o.append('<div class="hd"><div>')
    o.append(f'<h3>{esc(rep["ref"] or "Plot")}</h3>')
    loc = " · ".join([x for x in (rep.get("project"), rep.get("size")) if x])
    if loc:
        o.append(f'<p class="loc">{esc(loc)}</p>')
    o.append('</div>')
    sc = rep.get("score")
    if sc:
        pct = max(0.0, min(100.0, sc["value"])) / 100.0
        dash = 175.9
        o.append('<div class="dial"><svg viewBox="0 0 64 64">'
                 '<circle cx="32" cy="32" r="28" fill="none" '
                 'stroke="var(--line)" stroke-width="7"/>'
                 f'<circle cx="32" cy="32" r="28" fill="none" '
                 f'stroke="var(--brand)" stroke-width="7" '
                 f'stroke-dasharray="{dash:.1f}" '
                 f'stroke-dashoffset="{dash * (1 - pct):.1f}"/></svg>'
                 f'<div><div class="n">{sc["value"]:.0f}</div>'
                 f'<div class="l">{esc(sc["label"])}</div></div></div>')
    o.append('</div>')

    # ---- key facts --------------------------------------------------------
    keys = []
    if rep.get("size"):
        keys.append(("Plot size", rep["size"], "As supplied by the seller"))
    if rep.get("price"):
        keys.append(("Price", rep["price"], None))
    if rep.get("status"):
        keys.append(("Status", rep["status"], None))
    for f in rep.get("facts", []):
        keys.append((f["k"], f["v"], f.get("n")))
    if keys:
        o.append('<div class="keys">')
        for k, v, n in keys:
            o.append(f'<div class="key"><div class="k">{esc(k)}</div>'
                     f'<div class="v">{esc(v)}</div>'
                     + (f'<div class="n">{esc(n)}</div>' if n else "")
                     + '</div>')
        o.append('</div>')

    # ---- the four columns -------------------------------------------------
    def col(title, rows):
        if not rows:
            return ""
        h = [f'<div class="col"><h4>{esc(title)}</h4>']
        for r in rows:
            # Join on what is actually present. A row with no travel time
            # (the mast) was rendering a leading "· 1.0 km away".
            right = " · ".join([x for x in (r.get("travel"), r.get("spelled"))
                                if x])
            h.append(f'<div class="r"><b>{esc(r["what"])}</b>'
                     f'<span>{esc(right)}</span></div>')
        h.append('</div>')
        return "".join(h)

    net = rep.get("network") or {}
    net_rows = []
    if net.get("has_4g"):
        net_rows.append({"what": "4G data", "travel": "Available",
                         "spelled": "in this area"})
    if net.get("has_2g"):
        net_rows.append({"what": "Calls and SMS", "travel": "Available",
                         "spelled": "in this area"})
    # "Nearest mast - 1.0 km away" is REMOVED from the seller's page.
    #
    # Rule D4 pairs the sublocation coverage percentage with dist_tower_m
    # because the percentage is an area figure and the mast is the
    # point-specific half. That reasoning is about not overclaiming coverage,
    # and it is satisfied by the wording already used - "Available - in this
    # area" says plainly that it is an area statement.
    #
    # What the mast row added was a distance to a crowd-estimated OpenCellID
    # position, at confidence 2, which no land buyer can act on. They want to
    # know whether their phone will work. A number they cannot use, carrying a
    # caveat they will not read, is not more honest - it is just more.
    #
    # The value stays in the database and in the PDF report, where the reader
    # has paid for depth.

    cols = (col("Access", rep.get("access"))
            + col("Amenities nearby", rep.get("amenities"))
            + col("Landmarks", rep.get("landmarks"))
            + col("Mobile network", net_rows))
    if cols:
        o.append('<div class="cols">' + cols + '</div>')

    # ---- imagery + actions -------------------------------------------------
    o.append(_imagery_html(rep.get("ref"), api_key, company_id))
    o.append(_actions_html(rep.get("ref"), company_id, b))

    # ---- the rest of the scheme -------------------------------------------
    sch = rep.get("scheme") or []
    if len(sch) > 1:
        open_n = sum(1 for r in sch if r["state"] == "available")
        o.append('<div class="sch"><div class="top">'
                 f'<b>{open_n} of {len(sch)} plots in this scheme available</b>'
                 '</div>')
        for r in sch:
            cls = ("gone" if r["state"] in ("sold", "off_market")
                   else "dep" if r["state"] in ("reserved", "deposit_paid")
                   else "")
            bits = " · ".join([x for x in (r.get("size"), r.get("price")) if x])
            o.append(f'<div class="r"><b>{esc(r["ref"])}'
                     + (f' <span class="pill {cls}">{esc(r["status"])}</span>'
                        if r.get("status") else "")
                     + f'</b><span>{esc(bits)}</span></div>')
        o.append('</div>')

    o.append('<div class="ft">' + esc(rep.get("footer") or "")
             + (f' {esc(footer)}' if footer else "")
             + ' Analysis by Geocode Spatial Solutions Ltd. '
               'Map data © OpenStreetMap contributors, ODbL.</div>')
    o.append('</div>')
    return "".join(o)


@app.get("/v1/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True, "api_version": API_VERSION}
