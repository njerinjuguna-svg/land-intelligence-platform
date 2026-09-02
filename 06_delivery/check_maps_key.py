r"""
============================================================================
WHAT DOES GOOGLE ACTUALLY SAY ABOUT THIS KEY?
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS EXISTS

  The widget shows a broken image and the page cannot tell you why. The
  reason is a sentence Google puts in the response body - "billing has not
  been enabled on this project", "this API project is not authorized to use
  this API", "the provided API key is expired" - and it never reaches the
  browser, because by then it is just a failed <img>.

  This asks Google the same questions the API asks, with the same key from
  the same file, and prints the answer verbatim. No interpretation, no
  guessing which of the four usual causes it is.

RUNS AGAINST A REAL PARCEL
  It uses a real plot's coordinates when it can, because "does the key work"
  and "does the key work for the place we need" are different questions, and
  Street View in particular is answered per location.

USAGE
  python check_maps_key.py
  python check_maps_key.py --ref PLOT-457
============================================================================
"""
import os
import sys
import json
import argparse
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
LOCAL_ENV = BASE / ".env"
ETL_ENV = BASE.parent / "03_etl" / ".env"
TIMEOUT = 15

# Nairobi city centre, if no parcel can be read. Any coordinate proves the
# key; only a real one proves the plot.
FALLBACK = (-1.286389, 36.817223)


def get(url):
    """-> (http_status, body_bytes, content_type). Never raises."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read(), e.headers.get("Content-Type", "")
        except Exception:                                     # noqa: BLE001
            return e.code, b"", ""
    except Exception as e:                                    # noqa: BLE001
        return 0, str(e).encode(), "error"


def show(title, status, body, ctype):
    print(f"\n{'-' * 70}\n{title}\n{'-' * 70}")
    print(f"  HTTP {status}   {ctype}   {len(body)} bytes")
    looks_image = ctype.startswith("image/") and len(body) > 2000
    if looks_image:
        print("  OK - a real image came back.")
        return True
    text = body[:600].decode("utf-8", "replace").strip()
    print(f"  NOT AN IMAGE. Google said:\n")
    for line in (text or "(empty response)").splitlines():
        print(f"      {line}")
    return False


def parcel_point(ref):
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        return None
    load_dotenv(ETL_ENV)
    pw = os.getenv("DB_PASSWORD")
    if not pw:
        return None
    try:
        eng = create_engine(
            f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
            f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
            f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")
        with eng.connect() as conn:
            q = ("SELECT ST_Y(ST_Centroid(geom)), ST_X(ST_Centroid(geom)) "
                 "FROM land.parcels WHERE status = 'active'")
            if ref:
                q += " AND parcel_ref = :r"
            q += " ORDER BY parcel_ref LIMIT 1"
            row = conn.execute(text(q), ({"r": ref} if ref else {})).one_or_none()
        return (float(row[0]), float(row[1])) if row else None
    except Exception:                                         # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None, help="a parcel_ref to test against")
    a = ap.parse_args()

    env_file = LOCAL_ENV if LOCAL_ENV.exists() else ETL_ENV
    load_dotenv(env_file)
    key = (os.getenv("GOOGLE_MAPS_KEY") or "").strip()

    print("=" * 70)
    print("GOOGLE MAPS KEY CHECK")
    print("=" * 70)
    print(f"  reading   : {env_file}")

    if not LOCAL_ENV.exists():
        print(f"\n  06_delivery\\.env DOES NOT EXIST.")
        print(f"  The widget reads THAT file, not the ETL's. Copy")
        print(f"  .env.example to .env in 06_delivery and put the key there.")
        sys.exit(1)

    if not key:
        print("\n  GOOGLE_MAPS_KEY is empty or missing in that file.")
        print("  Add a line exactly like this, with no quotes and no spaces")
        print("  around the '=':\n")
        print("      GOOGLE_MAPS_KEY=AIzaSy...\n")
        sys.exit(1)

    print(f"  key       : {key[:6]}...{key[-4:]}  ({len(key)} chars)")
    if not key.startswith("AIza"):
        print("  NOTE: Google browser/server keys normally start 'AIza'. "
              "This may be the wrong value.")

    pt = parcel_point(a.ref)
    if pt:
        lat, lon = pt
        print(f"  testing at: {a.ref or 'first active parcel'}  "
              f"({lat:.5f}, {lon:.5f})")
    else:
        lat, lon = FALLBACK
        print(f"  testing at: Nairobi centre (could not read a parcel)")

    ok_sat = show(
        "1. MAPS STATIC API  - the satellite picture and the scheme map",
        *get(f"https://maps.googleapis.com/maps/api/staticmap"
             f"?center={lat},{lon}&zoom=17&size=400x300&maptype=satellite"
             f"&key={key}"))

    status, body, ctype = get(
        f"https://maps.googleapis.com/maps/api/streetview/metadata"
        f"?location={lat},{lon}&key={key}")
    print(f"\n{'-' * 70}\n2. STREET VIEW STATIC API - coverage at this plot"
          f"\n{'-' * 70}")
    print(f"  HTTP {status}   {len(body)} bytes")
    sv_status = ""
    try:
        meta = json.loads(body.decode())
        sv_status = meta.get("status", "")
        print(f"  status: {sv_status}")
        if meta.get("error_message"):
            print(f"  error : {meta['error_message']}")
    except Exception:                                         # noqa: BLE001
        print(f"  {body[:300].decode('utf-8', 'replace')}")

    print("\n" + "=" * 70)
    if ok_sat:
        print("SATELLITE AND SCHEME MAP WILL WORK.")
    else:
        print("SATELLITE WILL NOT WORK. The message above is the reason.")
        print()
        print("The four that account for almost all of these:")
        print("  'billing ... not enabled'   -> attach a billing account to")
        print("                                 the project. Maps has a free")
        print("                                 monthly credit; a card is")
        print("                                 still required to enable it.")
        print("  'not authorized to use'     -> enable Maps Static API on")
        print("                                 THIS project (Library).")
        print("  'referer'/'IP' restriction  -> the key is restricted to a")
        print("                                 site or address the server is")
        print("                                 not. Our requests come from")
        print("                                 the SERVER, not the browser.")
        print("  'expired' / 'invalid'       -> wrong or revoked key.")

    if sv_status == "OK":
        print("STREET VIEW: imagery exists at this plot - the panel will show.")
    elif sv_status == "ZERO_RESULTS":
        print("STREET VIEW: no imagery at this plot. NOT AN ERROR - the panel")
        print("             is simply left out. Most Kenyan land for sale is")
        print("             not on a Street View road.")
    elif sv_status:
        print(f"STREET VIEW: {sv_status} - see the message above.")
    print("=" * 70)
    sys.exit(0 if ok_sat else 1)


if __name__ == "__main__":
    main()
