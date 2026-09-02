r"""
============================================================================
MINT AN API KEY
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY YOU CANNOT JUST LOOK THE OLD ONE UP

  clients.api_keys stores a SHA-256 of the key and never the key itself,
  decided in session 2 so that a leaked database dump is not a set of working
  credentials. That is the right decision and this is its cost: a key that
  was not written down when it was minted is gone. Not hard to recover -
  gone. Minting a new one is the only path.

  So this prints the key ONCE, to the terminal, and never again. Put it
  somewhere before you close the window.

WHAT A KEY IS, AND WHAT IT IS NOT

  It is public by nature. It sits in the `data-key` attribute of a script tag
  on a client's website, which means it is visible to anyone who views the
  page source, and that is not a flaw - it is what an embed widget is.

  What makes that acceptable is that the key can only ask for one company's
  parcels, can only read, and will eventually be rate-limited. It is an
  identifier with a scope, not a secret. Treat a leaked key as a support
  matter - revoke and re-mint - rather than an incident.

RUNS AS THE SUPERUSER, DELIBERATELY

  landiq_api cannot INSERT into clients.api_keys, by design: the component on
  the internet must not be able to mint its own credentials. This is a
  workbench tool and reads 03_etl/.env.

USAGE
  python mint_key.py --list
  python mint_key.py --company "ZZ TEST - Geocode Internal Verification"
  python mint_key.py --company "Oak Grove Ltd" --label "their website" --live
============================================================================
"""
import os
import sys
import hashlib
import secrets
import argparse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent
ENV_DIR = BASE.parent / "03_etl"


def connect():
    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")


def columns(conn, schema, table):
    """-> {column_name: data_type}.

    TYPES, not just names. The first version of this asked only which columns
    existed and then passed 'embed' to clients.api_keys.scopes, which is
    text[] - so the INSERT failed on a malformed array literal after the key
    had already been generated.

    Knowing a column is there is not knowing what it holds. That is the same
    error as reading the raster catalogue's `path` when the column is
    `storage_url`, one level further down.
    """
    return {r[0]: r[1] for r in conn.execute(text("""
        SELECT column_name, data_type FROM information_schema.columns
         WHERE table_schema = :s AND table_name = :t"""),
        {"s": schema, "t": table}).all()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", help="company name, or part of it")
    ap.add_argument("--label", default=None,
                    help="what this key is for - shown in --list")
    ap.add_argument("--scopes", default="embed",
                    help="default: embed")
    ap.add_argument("--live", action="store_true",
                    help="prefix pk_live_ instead of pk_test_")
    ap.add_argument("--list", action="store_true", dest="do_list")
    a = ap.parse_args()

    engine = connect()

    with engine.connect() as conn:
        cols = columns(conn, "clients", "api_keys")
        if not cols:
            sys.exit("ERROR: clients.api_keys does not exist.")

        if a.do_list or not a.company:
            rows = conn.execute(text("""
                SELECT c.name, k.api_key_id, k.scopes, k.revoked,
                       k.expires_at
                  FROM clients.api_keys k
                  JOIN clients.companies c ON c.company_id = k.company_id
                 ORDER BY c.name, k.api_key_id""")).all()
            print(f"\n{len(rows)} key(s). The key STRINGS are not stored and "
                  f"cannot be shown.\n")
            for name, kid, scopes, revoked, exp in rows:
                state = "REVOKED" if revoked else "live"
                print(f"  {name:<44} {str(kid)[:8]}  {scopes or '-':<10} "
                      f"{state}{'  expires ' + str(exp) if exp else ''}")
            if not a.company:
                print("\nTo mint one:  python mint_key.py --company \"<name>\"")
                return

        hits = conn.execute(text("""
            SELECT company_id, name, is_active FROM clients.companies
             WHERE name ILIKE :q ORDER BY name"""),
            {"q": f"%{a.company}%"}).all()

    if not hits:
        sys.exit(f"No company matching '{a.company}'. Try --list.")
    if len(hits) > 1:
        print("More than one company matches. Be more specific:")
        for _, name, _ in hits:
            print(f"   {name}")
        sys.exit(1)

    company_id, name, is_active = hits[0]
    if not is_active:
        print(f"NOTE: '{name}' is NOT active. The key will be minted and the "
              f"API will refuse it until clients.companies.is_active is true.")

    # 32 bytes of urandom. The prefix is for humans reading a page source and
    # carries no meaning to the API - the hash is the whole credential.
    key = ("pk_live_" if a.live else "pk_test_") + secrets.token_urlsafe(32)
    digest = hashlib.sha256(key.encode()).hexdigest()

    # Build the INSERT from the columns that actually exist, rather than
    # assuming a shape. A wrong column name here would fail after the key was
    # generated and leave the operator unsure whether it had been stored.
    values = {"company_id": company_id, "key_hash": digest}
    if "scopes" in cols:
        # text[] takes a Python list; psycopg2 adapts it. A plain string here
        # is what broke the first run.
        wanted = [s.strip() for s in a.scopes.split(",") if s.strip()]
        values["scopes"] = wanted if cols["scopes"] == "ARRAY" else a.scopes
    if "revoked" in cols:
        values["revoked"] = False
    for label_col in ("label", "name", "description"):
        if label_col in cols and a.label:
            values[label_col] = a.label
            break

    missing = {"company_id", "key_hash"} - set(cols)
    if missing:
        sys.exit(f"ERROR: clients.api_keys is missing {missing}. "
                 f"Columns present: {sorted(cols)}")

    collist = ", ".join(values)
    vallist = ", ".join(f":{c}" for c in values)
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO clients.api_keys ({collist}) VALUES ({vallist})"),
            values)

    print("\n" + "=" * 72)
    print("KEY MINTED. IT IS SHOWN ONCE AND IS NOT RECOVERABLE.")
    print("=" * 72)
    print(f"\n  company : {name}")
    print(f"  key     : {key}\n")
    print("=" * 72)
    print("SEE IT WORKING - open this in a browser:\n")
    print(f"  http://127.0.0.1:8000/demo?k={key}\n")
    print("Through the tunnel, the same path on the trycloudflare address:\n")
    print(f"  https://<your-tunnel>.trycloudflare.com/demo?k={key}\n")
    print("=" * 72)
    print("What a real client pastes into their own page:\n")
    print('  <div id="geocode-plot" data-plot-ref="PLOT-457"></div>')
    print('  <div id="geocode-scheme" data-scheme="OAK GROVE"></div>')
    print(f'  <script src="https://<host>/v1.js" data-key="{key}"></script>')
    print("\nOr from the command line:\n")
    print(f'  curl.exe -H "X-API-Key: {key}" '
          f'http://127.0.0.1:8000/v1/plots/PLOT-457')
    # The FULL hash, because a truncated one with an ellipsis is a command
    # that cannot be run - which is the failure this project keeps finding in
    # its own documentation.
    print("\nTo revoke it later, copy this line as it stands:\n")
    print(f"  UPDATE clients.api_keys SET revoked = true "
          f"WHERE key_hash = '{digest}';")
    print("=" * 72)


if __name__ == "__main__":
    main()
