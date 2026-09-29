r"""
============================================================================
WHY IS THE SCHEME MAP SHOWING PINS INSTEAD OF BOUNDARIES?
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS EXISTS

  `_draw_scheme_map` returns None for six different reasons and the widget
  responds to every one of them identically - by falling back to pins. That
  fallback is right on a client's page, where a map with pins beats a gap,
  and it is useless to the person trying to work out what went wrong.

  This calls the same function directly and says which of the six it was.

  It also writes the picture to disk, so "did it draw?" is answered by
  looking at it rather than by inferring from an absence.

USAGE
  python check_scheme_map.py --project "OAK GROVE"
  python check_scheme_map.py --company "ZZ TEST" --project "OAK GROVE"
============================================================================
"""
import os
import sys
import argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default=None, help="name, or part of it")
    ap.add_argument("--project", default="", help="scheme name, e.g. OAK GROVE")
    ap.add_argument("--out", default=str(BASE / "scheme_map_test.jpg"))
    a = ap.parse_args()

    print("=" * 70)
    print("SCHEME MAP CHECK")
    print("=" * 70)

    # 1. Pillow, the reason the fallback exists at all.
    try:
        from PIL import Image  # noqa: F401
        import PIL
        print(f"  Pillow          : {PIL.__version__}")
    except ImportError:
        print("  Pillow          : NOT INSTALLED")
        print("\n  This alone forces the pin fallback. Fix with:")
        print("    ..\\03_etl\\venv\\Scripts\\python.exe -m pip install Pillow")
        sys.exit(1)

    # Importing the API runs its startup checks, which is deliberate: if the
    # credentials or the Maps key are wrong, that is the answer and it will
    # say so here exactly as it does in the server window.
    import api_01_embed as api
    from sqlalchemy import text

    print(f"  Google Maps key : "
          f"{'set' if api.GOOGLE_KEY else 'NOT SET - this forces pins'}")
    if not api.GOOGLE_KEY:
        sys.exit(1)

    with api.engine.connect() as conn:
        q = "SELECT company_id, name FROM clients.companies"
        params = {}
        if a.company:
            q += " WHERE name ILIKE :q"
            params["q"] = f"%{a.company}%"
        q += " ORDER BY name"
        hits = conn.execute(text(q), params).all()
    if not hits:
        sys.exit("  No companies found.")
    if len(hits) > 1 and a.company:
        print("  More than one company matches:")
        for _, n in hits:
            print(f"     {n}")
        sys.exit(1)
    company_id, name = hits[0]
    print(f"  company         : {name}")
    print(f"  project         : {a.project or '(all plots)'}")

    # 2. Geometry. The most common real cause after Pillow: rings that come
    #    back empty, which draws nothing and looks exactly like a failure.
    rings = api._scheme_rings(company_id, a.project)
    print(f"\n  parcels with usable rings : {len(rings)}")
    if not rings:
        print("\n  NO RINGS. _scheme_rings found no exterior rings for these")
        print("  parcels. Either the project name does not match exactly")
        print("  (it is case-sensitive here), or the geometry is not")
        print("  polygonal. Check with:")
        print("    SELECT DISTINCT project_name FROM land.parcels")
        print("     WHERE status = 'active';")
        sys.exit(1)
    for ref, rs, lx, ly in rings[:8]:
        print(f"     {ref:<16} {len(rs)} ring(s), "
              f"{sum(len(r) for r in rs)} vertices, "
              f"label at {ly:.5f},{lx:.5f}")
    if len(rings) > 8:
        print(f"     ... and {len(rings) - 8} more")

    # 3. The draw itself, including the Google fetch inside it.
    print("\n  drawing (this calls Google for the satellite base)...")
    drawn = api._draw_scheme_map(company_id, a.project)
    if not drawn:
        print("\n  DRAW RETURNED NOTHING.")
        print("  The reason was printed above by the API itself - a Google")
        print("  error, a base image that was not an image, or no plots.")
        print("  If nothing was printed, run check_maps_key.py.")
        sys.exit(1)

    body, ctype = drawn
    Path(a.out).write_bytes(body)
    print(f"\n  DREW IT: {len(body):,} bytes, {ctype}")
    print(f"  written to {a.out}")
    print("\n  Open that file. If the boundaries are on the plots and the")
    print("  numbers are inside them, the drawing works and anything you")
    print("  still see in the browser is a CACHED image - hard-refresh with")
    print("  Ctrl+F5, or check that the <img> URL now carries &v=.")
    print("=" * 70)


if __name__ == "__main__":
    main()
