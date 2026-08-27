r"""
============================================================================
BUYER REPORT PDF v0.1
Land Intelligence Platform - Geocode Spatial Solutions Ltd

ANALYSIS ONLY. NO IMAGES. That is checklist B4, decided in session 7, and it
is the reason this file is simple: every imagery licensing question — Google's
caching and printed-output terms, tile attribution inside a document we sell,
Mapillary's share-alike — drops out of the deliverable the moment the PDF
carries no map. Imagery lives on the seller's platform, where a buyer goes for
directions and Street View.

  DO NOT ADD A MAP TO THIS PDF without reopening B4. It would reintroduce
  every one of those questions into the one artefact we charge money for.

WHY ReportLab AND NOT AN HTML-TO-PDF CONVERTER
  WeasyPrint needs GTK on Windows and this project runs on Windows. ReportLab
  is pip-installable, self-contained, and has no system dependencies. The
  layout is plainer; the deployment is not a fight.

THE WORDS COME FROM report_content.py
  This file chooses fonts and spacing. It does not choose wording. The embed
  widget and this PDF must say the same thing about the same plot, and the day
  they disagree about a flood class is the day a client stops trusting both.

EVERY REPORT PINS ITS INPUTS
  reports.reports carries intel_version and score_version, so a PDF can be
  regenerated identically, and a report built on superseded intelligence is
  detectable rather than merely old.

RUN IT
  pip install reportlab
  python pdf_01_report.py --parcel PLOT-457
  python pdf_01_report.py --all --out ../04_docs/reports
============================================================================
"""

import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_content import build_report, assert_no_geometry

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, KeepTogether)
except ImportError:
    sys.exit("ERROR: pip install reportlab")

BASE = Path(__file__).resolve().parent
ENV_DIR = BASE.parent / "03_etl"
REPORT_VERSION = "0.1.0"

INK = colors.HexColor("#12211a")
MUTED = colors.HexColor("#54615a")
LINE = colors.HexColor("#dfe4e0")
PANEL = colors.HexColor("#f3f6f3")
TONE = {"yes": colors.HexColor("#0a7d0a"), "careful": colors.HexColor("#8a6200"),
        "no": colors.HexColor("#c0332f"), "unsure": colors.HexColor("#6e7973")}


def styles():
    s = getSampleStyleSheet()
    def mk(n, **kw):
        base = dict(name=n, fontName="Helvetica", textColor=INK, leading=14,
                    alignment=TA_LEFT)
        base.update(kw)
        return ParagraphStyle(**base)
    return {
        "h1": mk("h1", fontName="Helvetica-Bold", fontSize=19, leading=23,
                 spaceAfter=2),
        "sub": mk("sub", fontSize=10, textColor=MUTED, spaceAfter=12),
        "h2": mk("h2", fontName="Helvetica-Bold", fontSize=12, leading=15,
                 spaceBefore=15, spaceAfter=7),
        "ask": mk("ask", fontName="Helvetica-Bold", fontSize=11, leading=14),
        "ans": mk("ans", fontName="Helvetica-Bold", fontSize=12, leading=15,
                  spaceBefore=2),
        "body": mk("body", fontSize=10, leading=14, textColor=MUTED),
        "means": mk("means", fontSize=10, leading=14),
        "small": mk("small", fontSize=8.4, leading=11.6, textColor=MUTED),
        "chk": mk("chk", fontSize=10, leading=13.5),
        "chkwhy": mk("chkwhy", fontSize=8.8, leading=12, textColor=MUTED),
    }


def panel(flowables, pad=8, bg=PANEL, border=None):
    t = Table([[flowables]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.6, border or bg),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad)]))
    return t


def build_pdf(rep, out_path, branding=None):
    S = styles()
    story = []
    footer_text = (branding or {}).get("report_footer") or ""

    story.append(Paragraph(rep["ref"] or "Land report", S["h1"]))
    size = rep.get("size")
    if size and rep.get("size_measured"):
        # Say whose figure it is. A seller quoting an eighth of an acre and a
        # report quoting 0.13 acres is an argument nobody needs to have in
        # front of a buyer, and "our measurement" ends it in two words.
        size += " (our measurement)"
    bits = [b for b in (size, rep.get("project")) if b]
    story.append(Paragraph(" · ".join(bits) if bits else "&nbsp;", S["sub"]))

    if rep["withheld"]:
        story.append(panel([
            Paragraph("<b>%s</b>" % rep["withheld"]["title"], S["ans"]),
            Spacer(1, 4),
            Paragraph(rep["withheld"]["text"], S["body"])],
            bg=colors.HexColor("#fdf3f3"),
            border=colors.HexColor("#c0332f")))
    else:
        sc = rep.get("score")
        if sc:
            # The strings come from report_content. This file composed them
            # itself once and produced "98 / 100 — Good best suited to
            # residential use" - the band and the clause each read correctly
            # and there was nothing between them. Neither renderer writes
            # sentences now.
            head = [Paragraph("<b>%s</b>&nbsp;&nbsp;<font size=9 "
                              "color='#54615a'>%s</font>"
                              % (sc["headline"], sc.get("use_line") or ""),
                              S["ans"])]
            if sc.get("not_for_line"):
                head += [Spacer(1, 4),
                         Paragraph('<font color="#c0332f"><b>%s</b></font>'
                                   % sc["not_for_line"], S["means"])]
            head += [Spacer(1, 3), Paragraph(sc["note"], S["small"])]
            story.append(panel(head))
            story.append(Spacer(1, 4))

        story.append(Paragraph("The four things people ask", S["h2"]))
        for q in rep["questions"]:
            block = [
                Paragraph(q["ask"], S["ask"]),
                # ReportLab wants '#rrggbb'; .hexval() returns '0xrrggbb'.
                # Stripping two characters produced 'c0332f', which it
                # rejects outright - caught on the first build, which is
                # what building it here rather than shipping it was for.
                Paragraph('<font color="#%s">%s</font>'
                          % (TONE.get(q["tone"], MUTED).hexval()[2:],
                             q["answer"]), S["ans"]),
                Spacer(1, 2),
                Paragraph(q["because"], S["body"]),
                Spacer(1, 5),
                panel([Paragraph("<b>What this means for you</b>", S["small"]),
                       Spacer(1, 2),
                       Paragraph(q["means"], S["means"])]),
                Spacer(1, 3),
                Paragraph(q["confidence_text"], S["small"]),
                Spacer(1, 11),
            ]
            story.append(KeepTogether(block))

    if rep["nearby"]:
        story.append(Paragraph("What is nearby", S["h2"]))
        if rep.get("nearby_caveat"):
            story.append(Paragraph(rep["nearby_caveat"], S["small"]))
            story.append(Spacer(1, 6))

        # `contained` rather than `metres == 0`. The distinction is decided in
        # report_content, where it knows whether the boundary is trustworthy;
        # a renderer testing the number itself cannot know that and this one
        # got it wrong on PLOT-950.
        on = [n for n in rep["nearby"] if n.get("contained")]
        rest = [n for n in rep["nearby"] if not n.get("contained")]
        if on:
            # Was: "On the plot itself: main road. Not nearby — on the land."
            # The second sentence was there to stop a reader skimming the
            # number 0, and instead read as a fragment somebody forgot to
            # finish. One sentence carries the same point.
            tail = ("this crosses the plot rather than sitting near it."
                    if len(on) == 1 else
                    "these cross the plot rather than sitting near it.")
            story.append(Paragraph(
                "<b>On the land itself:</b> "
                + ", ".join(n["what"].lower() for n in on)
                + " — " + tail, S["means"]))
            story.append(Spacer(1, 6))
        if rest:
            # A river is not a convenience. Sorting the whole list by distance
            # put "River · 2 min walk · 161 m away" at the TOP of Athi Plains'
            # amenities, which reads as a selling point and is a setback and a
            # flood path. Features go last, under their own note.
            feats = [n for n in rest if n.get("kind") == "feature"]
            rest = [n for n in rest if n.get("kind") != "feature"] + feats
            data = [[Paragraph(n["what"]
                               + (" <font size=8 color='#8a6200'>(a limit on "
                                  "where you can build, not a convenience)"
                                  "</font>"
                                  if n.get("kind") == "feature" else ""),
                               S["means"]),
                     Paragraph(n["travel"], S["means"]),
                     Paragraph(n["spelled"], S["small"])] for n in rest]
            t = Table(data, colWidths=[75 * mm, 45 * mm, 45 * mm])
            t.setStyle(TableStyle([
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            story.append(t)
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Straight-line distance to the nearest mapped feature, not road "
            "distance. Health facilities are recorded at the centre of their "
            "ward rather than at the building, so treat those as approximate.",
            S["small"]))

    story.append(Paragraph("Before you pay", S["h2"]))
    for n, c in enumerate(rep["checklist"], 1):
        story.append(KeepTogether([
            Paragraph(f"<b>{n}.</b> {c['do']}", S["chk"]),
            Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;" + c["why"], S["chkwhy"]),
            Spacer(1, 7)]))

    story.append(Spacer(1, 6))
    story.append(panel([Paragraph("<b>How we worked this out, and what this "
                                  "report is not</b>", S["small"]),
                        Spacer(1, 4),
                        Paragraph(" ".join(rep["limits"]), S["small"])]))

    g = rep["generated_from"]
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Generated {date.today().isoformat()} · report format "
        f"v{REPORT_VERSION} · intelligence v{g.get('intelligence_version')} · "
        f"scoring {g.get('model_version')} v{g.get('score_version')}"
        + (f"<br/>{footer_text}" if footer_text else "") +
        "<br/>Geocode Spatial Solutions Ltd. Roads, rivers and riparian "
        "buffers &copy; OpenStreetMap contributors, ODbL 1.0. Terrain from "
        "Copernicus GLO-30. Rainfall from CHIRPS. Soils from SoilGrids and "
        "iSDAsoil.", S["small"]))

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=18 * mm,
        title=f"Land report — {rep['ref']}",
        author="Geocode Spatial Solutions Ltd",
        subject="Land intelligence report — analysis only, no imagery (B4)")
    doc.build(story)
    return out_path


# THE MISSING PLOT SIZE, AND THE DIAGNOSIS I ALMOST SHIPPED INSTEAD.
#
# The first four PDFs printed no acreage. Not a wrong figure - the line was
# simply absent on all twenty. The subtitle renders `size · project` and
# collapsed silently to `project` when size came back None.
#
# My first explanation was that `p.area_sqm, ... i.*` names a column and then
# splats a table holding a column of the same name, that a result row is keyed
# BY NAME so the duplicate collapses and the last one wins, and that
# `r["area_sqm"]` had therefore never been reading land.parcels at all. It is
# a real bug shape, it matched the symptom exactly, it is the third cousin of
# the `admin_name` fan-out and the nightlights catalogue collision, and I had
# written the comment before I checked.
#
# IT IS NOT WHAT HAPPENED. analytics.parcel_intelligence has 86 columns and
# `area_sqm` is not one of them; the only name it shares with land.parcels is
# `parcel_id`. Nothing was being shadowed. **land.parcels.area_sqm is simply
# NULL** - it is a nullable column nobody populates at load, while `geom` is
# NOT NULL and has carried the answer the whole time.
#
#     Rule E2 again, and it does not stop applying because the guess is a
#     good one. Query it, don't recall it. A confident wrong cause, written
#     into a comment, outlives the bug it misdescribes.
#
# TWO THINGS CHANGED HERE, FOR TWO DIFFERENT REASONS.
#
# 1. Size now comes from the geometry, not from the column. ST_Area on
#    geography returns metres on the ellipsoid - the same basis every distance
#    in this report already uses. A stored area can be stale or absent; the
#    boundary cannot, because it is the thing we were given. The column is
#    still preferred when present: if a client states an area, we quote theirs
#    and do not silently substitute our own measurement of their plot.
#
# 2. Every parcel column is aliased anyway. Not for area_sqm - for
#    `parcel_id`, which IS shared, and which `i.*` therefore supplies. On any
#    parcel with no intelligence row the LEFT JOIN makes that NULL and the
#    reports.reports INSERT writes a null key or fails outright. That one is
#    real, and it is exactly the bug I invented for area_sqm, sitting one
#    column over. Nothing to the left of a `.*` goes unaliased.
SQL = text("""
    SELECT p.parcel_ref   AS p_parcel_ref,
           p.project_name AS p_project_name,
           p.area_sqm     AS p_area_sqm,
           ST_Area(p.geom::geography)   AS p_area_calc_sqm,
           p.confidence   AS p_confidence,
           p.parcel_id    AS p_parcel_id,
           p.company_id   AS p_company_id,
           i.*, s.overall_score, s.residential_score,
           s.agricultural_score, s.commercial_score, s.investment_score,
           s.score_breakdown, s.model_version, s.version AS score_version
      FROM land.parcels p
      LEFT JOIN analytics.parcel_intelligence i
             ON i.parcel_id = p.parcel_id AND i.status = 'active'
      LEFT JOIN analytics.suitability_scores s
             ON s.parcel_id = p.parcel_id AND s.status = 'active'
     WHERE p.status = 'active'
""")


def main():
    only = None
    if "--parcel" in sys.argv:
        only = sys.argv[sys.argv.index("--parcel") + 1]
    out_dir = Path(sys.argv[sys.argv.index("--out") + 1]) \
        if "--out" in sys.argv else BASE / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")

    q = SQL.text + (" AND p.parcel_ref = :ref" if only else "") \
        + " ORDER BY p.parcel_ref"
    with engine.connect() as conn:
        rows = conn.execute(text(q),
                            ({"ref": only} if only else {})).mappings().all()
    if not rows:
        sys.exit("No parcels found." + (f" Unknown ref '{only}'." if only else ""))

    print(f"Buyer report PDF {REPORT_VERSION} — {len(rows)} parcel(s)")
    made = 0
    for r in rows:
        r = dict(r)
        score = {"overall_score": r.get("overall_score"),
                 "residential_score": r.get("residential_score"),
                 "agricultural_score": r.get("agricultural_score"),
                 "commercial_score": r.get("commercial_score"),
                 "investment_score": r.get("investment_score"),
                 "score_breakdown": r.get("score_breakdown"),
                 "model_version": r.get("model_version"),
                 "version": r.get("score_version")}
        parcel = {"parcel_ref": r["p_parcel_ref"],
                  "project_name": r.get("p_project_name"),
                  "area_sqm": r.get("p_area_sqm"),
                  "area_calc_sqm": r.get("p_area_calc_sqm")}
        rep = assert_no_geometry(build_report(r, score, parcel))

        with engine.connect() as conn:
            b = conn.execute(text("""
                SELECT report_footer FROM clients.branding
                 WHERE company_id = :c LIMIT 1"""),
                {"c": r.get("p_company_id")}).one_or_none()
        path = out_dir / f"{r['p_parcel_ref']}.pdf"
        build_pdf(rep, path, {"report_footer": b[0]} if b else None)

        # The report row pins the versions it was built from, so it can be
        # regenerated identically and a stale one is detectable.
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO reports.reports
                    (parcel_id, company_id, report_type, intel_version,
                     score_version, pdf_url, report_status, generated_at)
                VALUES (:p, :c, 'full', :iv, :sv, :u, 'ready', now())"""),
                {"p": r["p_parcel_id"], "c": r.get("p_company_id"),
                 "iv": r.get("version"), "sv": r.get("score_version"),
                 "u": str(path)})
        made += 1
        flag = "  (analysis withheld)" if rep["withheld"] else ""
        print(f"   {r['p_parcel_ref']:22} {path.name}{flag}")

    print(f"\nDONE. {made} report(s) in {out_dir}")


if __name__ == "__main__":
    main()
