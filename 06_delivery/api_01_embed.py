r"""
============================================================================
EMBED API v0.1 — the endpoint a client's website calls
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
    API of geometry   this IS conveyance — the highest exposure there is

  So the widget is the product and the geometry never crosses the boundary.
  `report_content.assert_no_geometry()` enforces that on every response,
  because "remember not to select geom" is a reminder and this is a control.

THE ONE REAL INTEGRATION POINT IS PLOT IDENTITY
  Their site says "Plot 457"; our database says `parcel_ref`. That mapping is
  agreed at onboarding and it is where the conversation with their developer
  actually happens. Serving the wrong plot's analysis to a buyer is the worst
  failure this product has, so the lookup is scoped to the calling company and
  an unknown ref is a 404 — never a nearest match, never a guess.

RUN IT
  pip install fastapi uvicorn
  uvicorn api_01_embed:app --reload --port 8000
  curl -H "X-API-Key: <key>" http://localhost:8000/v1/plots/PLOT-457
============================================================================
"""

import os
import sys
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
ENV_DIR = BASE.parent / "03_etl"
API_VERSION = "0.1.0"

load_dotenv(ENV_DIR / ".env")
_pw = os.getenv("DB_PASSWORD")
if not _pw or _pw == "put_your_password_here":
    sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
engine = create_engine(
    f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{_pw}"
    f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
    f"/{os.getenv('DB_NAME','land_intelligence_kenya')}",
    pool_pre_ping=True)

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
    return Response(LOADER.read_text(encoding="utf-8"),
                    media_type="application/javascript",
                    headers={"Cache-Control": "public, max-age=300"})


# ---------------------------------------------------------------------------
# Auth. The key is never stored — only its hash.
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
    always an IP address — it is 'testclient' under FastAPI's test client, and
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
# `i.*` would carry p.geom if the join brought it — it does not, because
# parcel_intelligence holds no geometry column. assert_no_geometry() is the
# backstop for the day somebody adds one.
#
# EVERY PARCEL COLUMN IS ALIASED. `p.area_sqm, ... i.*` names a column and
# then splats a table holding a column of the same name; the row is keyed BY
# NAME, the duplicate collapses, and the LAST one wins. In the PDF generator
# that silently sourced the plot size from parcel_intelligence instead of
# land.parcels, and every report printed no acreage at all — no error, no
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
        print(f"   ! 401 {request.url.path} — {why}")
        log_call(None, request, 401, 0)
        raise HTTPException(401, AUTH_REFUSED)
    return auth


@app.get("/v1/plots/{ref}")
def plot_json(ref: str, request: Request, x_api_key: str = Header(None)):
    """The report as data. Values only — never geometry."""
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
    with engine.connect() as conn:
        b = conn.execute(text("""
            SELECT report_footer FROM clients.branding
             WHERE company_id = :c LIMIT 1"""),
            {"c": auth["company_id"]}).one_or_none()
    log_call(auth, request, 200, ms)
    return HTMLResponse(listing_html(rep, b[0] if b and b[0] else ""))


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


def listing_html(rep, footer=""):
    o = ['<div class="giq"><style>', CSS, '</style>']

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
    if net.get("mast"):
        net_rows.append({"what": "Nearest mast", "travel": "",
                         "spelled": net["mast"]})

    cols = (col("Access", rep.get("access"))
            + col("Amenities nearby", rep.get("amenities"))
            + col("Landmarks", rep.get("landmarks"))
            + col("Mobile network", net_rows))
    if cols:
        o.append('<div class="cols">' + cols + '</div>')

    # ---- imagery + actions -------------------------------------------------
    o.append('<div class="slot">Satellite view and Street View appear here '
             'once a Google Maps key is configured.</div>')
    o.append('<div class="acts">'
             '<a class="p" href="#">Get directions</a>'
             '<a href="#">Book a site visit</a></div>')

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
