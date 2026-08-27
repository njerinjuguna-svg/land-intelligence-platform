r"""
============================================================================
ENRICHMENT ENGINE v0.1 - VERTICAL SLICE
Land Intelligence Platform - Geocode Spatial Solutions Ltd

THIS IS THE PRODUCT. Everything before it was assembling the inputs.

WHAT IT DOES
  For each parcel in land.parcels, sample every relevant layer under and
  around the parcel FOOTPRINT, and write one row to
  analytics.parcel_intelligence.

WHY A VERTICAL SLICE AND NOT ALL TWENTY LAYERS AT ONCE
  This version covers four layer families - roads, flood, soils, rainfall -
  but covers them COMPLETELY: run logging, composition and range columns,
  per-field confidence, per-field source lineage, and the product rules that
  apply to each. The hard parts are the ones that are hard to retrofit.

  Adding the remaining layers is then mechanical: write a sample_* function,
  add it to the LAYERS list. That is the same move that worked for the raster
  ETLs - get the pattern right once, then repeat it.

FOOTPRINT, NOT CENTROID. THIS IS NOT NEGOTIABLE.
  Lesson 18, and lesson 21 which repeated it after it was written down: a
  test that probes one cell tests the coordinate, not the place. Budalangi
  read 11.4 m HAND on its own cell and 0.0 m read across a neighbourhood.
  Garissa reads Very low on its own pixel with Very high 300 m away.

  A 50-acre plot does not have AN elevation. It has a range, and the range is
  the buildability signal. So every layer here is sampled across the polygon,
  and the composition/range columns (schema v1.1) carry the distribution.

THE CATALOGUE IS THE TRUTH ABOUT A FILE
  Raster paths are NEVER hardcoded. Every layer is looked up in
  metadata.raster_catalog by `variable`, and the row supplies the path, the
  confidence and the raster_id that goes into field_sources. If a raster is
  re-run and re-catalogued, this engine follows it automatically.

  Rasters with status <> 'active' are IGNORED. That is what quarantines
  landcover_change without any special case here.

PRODUCT RULES ENFORCED IN THIS VERSION
  D1  flood is MODELLED  - recorded in field_sources, must reach the report
  D2  worst class within a radius, not the cell - both are written
  D3  permanent water is a land-cover fact AND its own risk signal
  D7  black cotton needs SoilGrids Vertisols OR iSDA clay, never one alone
  C5  rainfall runs wet - confidence capped, noted on the field

How to run (from 05_enrichment, with the 03_etl venv active):
  python enrich_01_engine.py --dry-run     <- prints, writes nothing
  python enrich_01_engine.py
  python enrich_01_engine.py --parcel TEST-GARISSA-01
============================================================================
"""

import os
import sys
import json
from pathlib import Path

# PostgreSQL sets PROJ_LIB / GDAL_DATA system-wide to ITS older copies and
# hijacks rasterio. Documented in session 4; affects every reprojecting
# script on this laptop. Must happen BEFORE rasterio is imported.
for _k in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_k, None)

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import rasterio
    from rasterio.mask import mask as rio_mask
except ImportError as e:
    sys.exit(f"ERROR: missing dependency ({e}). With the venv active: "
             f"pip install rasterio")

BASE = Path(__file__).resolve().parent
ENV_DIR = BASE.parent / "03_etl"          # .env lives with the ETL scripts
ENGINE_VERSION = "0.1.0-slice"

# Radius for "worst class nearby". Rule D2. Recorded on every row rather than
# assumed, because a class without its radius is not reproducible.
FLOOD_RADIUS_M = 1000.0
# How far out to look for permanent water before giving up and returning NULL.
WATER_SEARCH_M = 5000.0
# A flood class must cover this share of the PARCEL to set flood_risk_class.
# 10% of a plot is a corner you cannot build on, which is worth saying; 2% is
# a pixel on the boundary, which is not.
PARCEL_MIN_PCT = 10.0
# Kenya-wide share in High or Very high, from the run 77 country-clipped
# distribution (5.61 + 6.93). The baseline that makes a neighbourhood figure
# readable: below this is not a warning, it is Tuesday.
NATIONAL_HIGH_PLUS_PCT = 12.5

# TWO CONSTANTS WERE DELETED HERE, AND THE REASON MATTERS MORE THAN THEY DID.
#
#   NEARBY_MIN_PCT = 2.0   a minimum neighbourhood share for the flood class
#   FLAT_SLOPE_DEG = 3.0   a landform arm for the black cotton rule
#
# Both described controls that no longer run, and neither approach was merely
# abandoned - both were MEASURED AND REJECTED:
#
#   neighbourhood share - Karen 4.31% very_high against Garissa 4.48%. No
#       threshold on that number separates them at ANY value, so the class
#       comes from the PARCEL instead (PROGRESS.md lesson 33).
#   slope as a black cotton discriminator - Karen 1.04 deg against Athi
#       2.94 deg. Karen is the FLATTER of the two, so the signal points the
#       WRONG WAY (PROGRESS.md lesson 34, checklist C16).
#
# Do not reintroduce either without new evidence. Checklist E13: a constant
# with a justifying comment and no reference gets read later as a description
# of what the code does.

# Radius for the built-up share. THE COLUMN IS NAMED built_up_pct_1km AND THE
# NAME IS A PROMISE - it is the share of a 1 km neighbourhood, not of the
# parcel. A 0.2 ha plot with one house on it is "100% built", which says
# nothing; the surrounding kilometre says whether this is town, edge or
# country, which is what a land buyer is asking.
#
# Deliberately NOT reusing FLOOD_RADIUS_M even though both are 1000 m today.
# Two unrelated quantities sharing one constant means changing the flood
# radius silently redefines a column whose name says 1km. main() checks this
# value against the column name and says so if they part company.
BUILTUP_RADIUS_M = 1000.0

# How far to look for each vector feature before returning NULL. These are
# honest ceilings, not guesses: past them the answer for a Kenyan land buyer
# is "there isn't one", and "the nearest hospital is 63 km away" is a
# different statement from a distance, not a more precise one.
#
# EVERY NULL FROM THESE RECORDS ITS RADIUS in field_sources, so a report can
# say "no school within 25 km" rather than printing a blank that reads as
# zero. A blank and a zero are opposite claims.
SEARCH_M = {
    "river": 25_000.0, "school": 25_000.0, "health": 40_000.0,
    "water_point": 25_000.0, "protected_area": 50_000.0,
    "tower": 25_000.0,
}

# Below this, a coverage percentage is a SLIVER ARTEFACT, not a measurement.
# The first run of the coverage layer returned Telkom 4G at 6.8e-07% and
# 3.5e-07% - the parcel centroid clipping a hairline overlap between adjacent
# polygons. "Telkom coverage: 0.0000007%" is not a small number, it is a
# geometry accident wearing a decimal point, and a report that prints it has
# said something false about an operator.
COVERAGE_SLIVER_PCT = 0.01

FLOOD_CLASSES = {1: "very_low", 2: "low", 3: "moderate", 4: "high",
                 5: "very_high", 6: "permanent_water"}
FLOOD_SEVERITY = {"very_low": 1, "low": 2, "moderate": 3, "high": 4,
                  "very_high": 5}

# WRB Reference Soil Groups, alphabetical, as SoilGrids codes them (0-29).
# Copied from etl_22, which verifies the legend by checking that soils which
# cannot occur in Kenya (Cryosols, Podzols) stay under 1%.
WRB = ["Acrisols", "Albeluvisols", "Alisols", "Andosols", "Arenosols",
       "Calcisols", "Cambisols", "Chernozems", "Cryosols", "Durisols",
       "Ferralsols", "Fluvisols", "Gleysols", "Gypsisols", "Histosols",
       "Kastanozems", "Leptosols", "Lixisols", "Luvisols", "Nitisols",
       "Phaeozems", "Planosols", "Plinthosols", "Podzols", "Regosols",
       "Solonchaks", "Solonetz", "Stagnosols", "Umbrisols", "Vertisols"]

# USDA texture classes as iSDA codes them, 1-12, 0 = nodata. From etl_17.
TEXTURE = {1: "Clay", 2: "Silty Clay", 3: "Sandy Clay", 4: "Clay Loam",
           5: "Silty Clay Loam", 6: "Sandy Clay Loam", 7: "Loam",
           8: "Silt Loam", 9: "Sandy Loam", 10: "Silt", 11: "Loamy Sand",
           12: "Sand"}
# Texture classes that genuinely indicate SHRINK-SWELL clay. Rule D7.
#
# NARROWED after run 1. The first version included Clay Loam (4) and Silty
# Clay Loam (5), and the result was Karen flagged as possible black cotton -
# Karen is Nitisols, the deep red coffee soil - and the Aberdares flagged on
# Andosols, which is volcanic highland.
#
# Session 5 measured Clay Loam at 15.0% of Kenya OUTSIDE Vertisols and 28.9%
# within. It is the commonest texture in the country and barely enriched under
# the soils it was supposed to indicate, so it carries almost no diagnostic
# weight. "Any clay-bearing" was 78.8% outside Vertisols - a threshold nearly
# everything meets cannot discriminate (lesson 19, rule E3).
#
# Clay and Silty Clay are the classes that actually crack and swell.
CLAY_TEXTURES = {1, 2}

# ESA WorldCover 2021 v200, from etl_19. 0 = nodata.
WORLDCOVER = {10: "Tree cover", 20: "Shrubland", 30: "Grassland",
              40: "Cropland", 50: "Built-up",
              60: "Bare / sparse vegetation", 70: "Snow and ice",
              80: "Permanent water", 90: "Herbaceous wetland",
              95: "Mangroves", 100: "Moss and lichen"}

# Impact Observatory 9-class, from etl_29. 0 = nodata.
#
# IO's "Rangeland" ABSORBS WorldCover's Shrubland AND Grassland, so the two
# products cannot be compared class by class and this engine does not try.
# Both are written, side by side. Where they disagree, that disagreement is
# information a buyer should see, not something to hide behind one number.
IO_CLASSES = {1: "Water", 2: "Trees", 4: "Flooded vegetation", 5: "Crops",
              7: "Built", 8: "Bare", 9: "Snow/ice", 10: "Clouds",
              11: "Rangeland"}

# Classes a reader is most likely to misread as "this is not farmland".
# RULE D6 says never conclude that from land cover alone: WorldCover
# under-detects smallholder mosaic farming, and NDVI showed up to 4.2x the
# mapped cropland area is as green as cropland. When the dominant class is one
# of these, the engine attaches the rule to the field rather than trusting the
# report to remember it.
NOT_FARMLAND_TRAP = {"Shrubland", "Grassland", "Bare / sparse vegetation",
                     "Rangeland", "Bare"}

# Physical range for NDVI. A COG whose scale tag is missing returns stored
# integers - NDVI reads 2100 instead of 0.21 - and that looks like data. The
# engine REFUSES a value outside this window rather than guessing a scale
# factor, because a silently rescaled number is exactly the confident wrong
# answer this project exists to avoid.
NDVI_RANGE = (-1.0, 1.0)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
def sources_index(engine):
    """source_id -> {source, licence, redistribution_allowed}.

    LICENCE LINEAGE IS RESOLVED AT RUN TIME, NEVER HARDCODED HERE.

    This is what makes the A1 and A4 questions answerable PER FIELD instead of
    per product. environment.protected_areas holds both OSM features and WDPA
    features; WDPA is NON-COMMERCIAL. Which one answered a given parcel is a
    fact about that row, not about the layer, and it is written onto the field
    so a report can be filtered rather than a whole layer withdrawn.

    When KWS data replaces WDPA under A1, or the rivers are re-cut from our own
    DEM under A4, every field_sources entry follows automatically. Hardcoding
    "ODbL-1.0" in this file would mean editing the engine to tell the truth
    after a source swap - which is how a licence claim goes stale.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT source_id, name, license, redistribution_allowed
            FROM metadata.sources
        """)).fetchall()
    return {int(r[0]): {"source": r[1], "licence": r[2],
                        "redistribution_allowed": r[3]} for r in rows}


def load_catalogue(engine):
    """variable -> {path, confidence, raster_id, nodata, year}. ACTIVE only.

    Status filtering is what quarantines a condemned layer. landcover_change
    sits at pending_review and therefore never reaches this engine, with no
    special case written here.

    ONE VARIABLE MUST NAME ONE RASTER, AND ONE DOES NOT.
      etl_26_nightlights.py writes a catalogue row PER YEAR, all under
      variable = 'nightlights'. "Keep the newest raster_id" then silently
      resolves to whichever year happened to be catalogued last - a choice
      nothing states, nothing tests, and nobody made.

      Harmless today only because nightlights is not yet sampled. It stops
      being harmless the moment that layer is added, which is why this is
      fixed BEFORE the layer rather than with it.

      Compare etl_29, which does it correctly: landcover_io_2017, _2023 and
      _2024 are three distinct variables, each unambiguous.

    THE FIX IS NOT TO PICK BETTER - IT IS TO REFUSE TO PICK SILENTLY.
      Newest-wins is still right for a layer that was genuinely RE-RUN, which
      is the common case. So the rule stays, and the collision is COUNTED and
      RETURNED. main() prints it, and any variable listed there must be read
      from its own table rather than sampled from here.

      Same shape as every other fix in this project: the control moves from a
      comment into something the code cannot pass over in silence.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT variable, storage_url, confidence, raster_id, nodata_value,
                   temporal_start
            FROM metadata.raster_catalog
            WHERE status = 'active'
            ORDER BY raster_id DESC
        """)).fetchall()
    cat, collisions = {}, {}
    for variable, url, conf, rid, nod, tstart in rows:
        if variable in cat:
            # A RE-RUN, or AN AMBIGUITY? This engine cannot tell the two
            # apart, so it keeps the newest and reports that it had to choose.
            collisions[variable] = collisions.get(variable, 1) + 1
            continue
        cat[variable] = {"path": url, "confidence": conf,
                         "raster_id": rid, "nodata": nod,
                         "year": tstart.year if tstart else None}
    # Returned under a name no `variable` could collide with. main() pops it
    # before the catalogue is used, so no sampler ever sees it.
    cat["__collisions__"] = collisions
    return cat


def sample(path, geom_geojson, nodata_hint=None):
    """Clip a raster to a polygon. Returns (values_1d, scale) or (None, 1.0).

    all_touched=True: a small parcel can fall between cell centres entirely,
    and returning nothing for a real plot is worse than including a cell it
    partly overlaps.
    """
    try:
        with rasterio.open(path) as src:
            arr, _ = rio_mask(src, [geom_geojson], crop=True, filled=True,
                              nodata=src.nodata if src.nodata is not None
                              else (nodata_hint if nodata_hint is not None
                                    else 0),
                              all_touched=True)
            scale = src.scales[0] if src.scales else 1.0
            nod = src.nodata if src.nodata is not None else nodata_hint
        a = arr[0].astype("float64")
        if nod is not None:
            a = a[a != nod]
        a = a[np.isfinite(a)]
        return (a if a.size else None), float(scale)
    except BaseException as exc:
        print(f"      ! could not sample {Path(path).name}: "
              f"{type(exc).__name__}: {exc}")
        return None, 1.0


def composition(values, names):
    """-> ({class: percent}, dominant, n_pixels).

    n_pixels is returned because a percentage without its sample size invites
    false confidence. Karen is 8,093 m2 sampled at 30 m: NINE PIXELS. "33.3%
    Clay" from nine pixels is three pixels, and three pixels is noise wearing
    a decimal point. Every composition here carries its n so a reader can tell
    a distribution from an accident.
    """
    if values is None or values.size == 0:
        return None, None, 0
    codes, counts = np.unique(values.astype(int), return_counts=True)
    total = float(counts.sum())
    comp = {}
    for c, n in zip(codes, counts):
        label = names.get(int(c)) if isinstance(names, dict) else (
            names[int(c)] if 0 <= int(c) < len(names) else None)
        if label is None:
            label = f"code_{int(c)}"
        comp[label] = round(100.0 * float(n) / total, 2)
    dominant = max(comp, key=comp.get)
    return comp, dominant, int(total)


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------
def layer_roads(engine, parcel_id, out, conf, src):
    """Vector distances, computed in PostGIS on geography so metres are real.

    ODbL NOTE: transport.roads is OpenStreetMap. This produces a DISTANCE - an
    inference containing no OSM data - which is the weakest share-alike
    exposure in the stack (see LICENSING_OPTIONS_MEMO.md). It stays swappable:
    change this one query and nothing else in the engine cares.
    """
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
              (SELECT round(ST_Distance(p.geom::geography, r.geom::geography))
                 FROM transport.roads r
                WHERE ST_DWithin(p.geom::geography, r.geom::geography, 25000)
                ORDER BY p.geom <-> r.geom LIMIT 1),
              (SELECT round(ST_Distance(p.geom::geography, r.geom::geography))
                 FROM transport.roads r
                WHERE r.road_class IN ('motorway','trunk','primary','secondary')
                  AND ST_DWithin(p.geom::geography, r.geom::geography, 50000)
                ORDER BY p.geom <-> r.geom LIMIT 1)
            FROM land.parcels p WHERE p.parcel_id = :pid
        """), {"pid": parcel_id}).one_or_none()
    if row:
        if row[0] is not None:
            out["dist_any_road_m"] = float(row[0])
            conf["dist_any_road_m"] = 4
            src["dist_any_road_m"] = {"layer": "transport.roads",
                                      "source": "OpenStreetMap/Geofabrik",
                                      "licence": "ODbL-1.0"}
        if row[1] is not None:
            out["dist_paved_road_m"] = float(row[1])
            conf["dist_paved_road_m"] = 3   # OSM surface tags are absent
            src["dist_paved_road_m"] = {"layer": "transport.roads",
                                        "note": "class-based, NOT surface: "
                                                "Geofabrik carries no surface "
                                                "attribute"}


def layer_flood(cat, geom, geom_buf, out, conf, src):
    """Rule D2: the worst class NEARBY, and the parcel's own cells, separately.

    They are expected to disagree - Garissa town sits on a terrace with Very
    high a few hundred metres away. If they never disagree, the radius is not
    being applied.
    """
    entry = cat.get("flood_hazard")
    if not entry:
        return
    cell_vals, _ = sample(entry["path"], geom)
    near_vals, _ = sample(entry["path"], geom_buf)

    comp, dominant, npix = composition(cell_vals, FLOOD_CLASSES)
    if comp:
        out["flood_risk_breakdown"] = json.dumps(comp)
        out["flood_risk_class_cell"] = dominant
        src["flood_risk_breakdown"] = {
            "n_pixels": npix, "pixel_m": 93,
            "warning": ("SMALL SAMPLE - percentages from this few cells are "
                        "not a distribution" if npix < 20 else None)}

    # THE CLASS COMES FROM THE PARCEL, NOT THE NEIGHBOURHOOD.
    #
    # Run 2 still returned very_high almost everywhere. Karen's 1 km buffer is
    # 4.31% very_high; Garissa's is 4.48%. Nearly identical numbers, opposite
    # meanings - so the neighbourhood share cannot separate them, because the
    # channel network is a similar fraction of the area everywhere (C10).
    #
    # The signal was on the land all along. Garissa's own footprint is 25%
    # very_high while its DOMINANT class is 'low'. Reporting the dominant
    # class buried a quarter of the parcel; reporting the neighbourhood
    # maximum flagged the whole country. Both were wrong in opposite
    # directions.
    #
    # So: the worst class covering a MATERIAL SHARE OF THE PARCEL sets
    # flood_risk_class. Nearby is kept as context, compared against the
    # national baseline, never as the headline.
    if comp:
        material = {k: v for k, v in comp.items()
                    if v >= PARCEL_MIN_PCT and k in FLOOD_SEVERITY}
        if material:
            out["flood_risk_class"] = max(material,
                                          key=lambda n: FLOOD_SEVERITY[n])
        elif dominant == "permanent_water":
            out["flood_risk_class"] = "permanent_water"
        else:
            out["flood_risk_class"] = dominant

    if near_vals is not None and near_vals.size:
        # A SINGLE CELL MUST NOT SET THE CLASS. Run 1 of this engine returned
        # very_high for 11 of 12 parcels, including Karen - 100% very_low on
        # its own footprint, prime residential land. A false flood warning
        # there is the most commercially damaging error this platform can make.
        #
        # Cause: max() over any class present in the buffer. Channel cells are
        # set to HAND = 0 and therefore classify Very high (checklist C10 -
        # over half the top class is the watercourse itself), and there is a
        # channel within 1 km of almost anywhere in Kenya. So "worst nearby"
        # evaluated to very_high everywhere, which flags everything and
        # therefore distinguishes nothing. Rule D2 was being obeyed literally
        # and defeated in substance.
        #
        # A class must now occupy a MEANINGFUL SHARE of the surroundings, and
        # the share is always reported alongside it. "Very high covering 0.2%
        # of the area 800 m away" and "28% of the surroundings are Very high"
        # are different statements and must not collapse to the same word.
        codes, counts = np.unique(near_vals.astype(int), return_counts=True)
        total = float(counts.sum())
        # RULE D3: class 6 is a LAND-COVER FACT, not a severity level. Excluded
        # from the worst-class calculation and surfaced separately as
        # dist_permanent_water_m. Folding it in would render a lake as "beyond
        # very high", which is a category error.
        shares = {FLOOD_CLASSES[int(c)]: 100.0 * float(n) / total
                  for c, n in zip(codes, counts)
                  if int(c) in FLOOD_CLASSES and int(c) != 6}
        # Nearby, as CONTEXT. Reported against the national baseline so the
        # number means something.
        #
        # MIND THE DENOMINATOR - this comment used to get it wrong. The
        # quantity below is High PLUS Very high, so it must be read against
        # NATIONAL_HIGH_PLUS_PCT = 12.5% (5.61 + 6.93), NOT against the 6.93%
        # that is Very high alone. The code was always right; the comment
        # reasoned against the wrong figure, which made every worked example
        # in it roughly twice the true multiple.
        #
        # So: a neighbourhood at 4% is about a THIRD of the national rate and
        # warns of nothing, while TEST-KANO-01 at 51% and TEST-TANADELTA-01 at
        # 44% are three to four times it. Those two numbers are measured, from
        # the run this comment was corrected in - not illustrations.
        vh = shares.get("very_high", 0.0) + shares.get("high", 0.0)
        out["flood_nearby_pct"] = round(vh, 2)
        src["flood_nearby"] = {
            "classes": {k: round(v, 2) for k, v in sorted(shares.items())},
            "meaning": "share of the surroundings in High or Very high",
            "national_baseline_pct": NATIONAL_HIGH_PLUS_PCT,
            "reading": ("ELEVATED" if vh >= 2 * NATIONAL_HIGH_PLUS_PCT
                        else "typical" if vh >= 0.5 * NATIONAL_HIGH_PLUS_PCT
                        else "below average"),
            "caveat": "channel cells sit at HAND=0 and classify Very high, so "
                      "a few per cent is the background rate almost anywhere "
                      "in Kenya, not a warning (checklist C10)"}

    out["flood_search_radius_m"] = FLOOD_RADIUS_M
    conf["flood_risk_class"] = entry["confidence"] or 3
    src["flood_risk_class"] = {
        "raster_id": entry["raster_id"],
        "MODELLED": True,
        "rule_D1": "Modelled, not measured. Must be stated in any "
                   "buyer-facing use and is not a substitute for a site "
                   "visit or hydrological study.",
        "rule_D2": f"worst class within {FLOOD_RADIUS_M:.0f} m, not the cell",
        "caveat": "depth-area exponent B=0.3 is from general literature, NOT "
                  "fitted to Kenyan gauge records (checklist B2)"}


def layer_permanent_water(cat, geom_water, centroid, out, conf, src):
    """RULE D3: proximity to permanent water is its OWN risk signal.

    This is what carries Budalangi's warning. Budalangi reads only Moderate on
    HAND because it floods by DIKE FAILURE, which height-above-drainage
    structurally cannot see - the village genuinely sits several metres above
    the channel. The hazard class understates it; this column does not.
    """
    entry = cat.get("flood_hazard")
    if not entry:
        return
    try:
        with rasterio.open(entry["path"]) as srcr:
            arr, tf = rio_mask(srcr, [geom_water], crop=True, filled=True,
                               nodata=0, all_touched=True)
        a = arr[0]
        rows, cols = np.where(a == 6)
        if rows.size == 0:
            out["dist_permanent_water_m"] = None
            src["dist_permanent_water_m"] = {
                "result": f"no permanent water within {WATER_SEARCH_M:.0f} m",
                "rule_D3": "NULL here means 'none found in range', NOT 'safe'"}
            return
        xs, ys = rasterio.transform.xy(tf, rows, cols)
        clon, clat = centroid
        # metre-equivalent degrees at this latitude; fine for a minimum over a
        # few km, and avoids a per-cell geography call on thousands of cells
        dx = (np.asarray(xs) - clon) * 111320.0 * np.cos(np.radians(clat))
        dy = (np.asarray(ys) - clat) * 110574.0
        out["dist_permanent_water_m"] = float(np.sqrt(dx * dx + dy * dy).min())
        conf["dist_permanent_water_m"] = entry["confidence"] or 3
        src["dist_permanent_water_m"] = {
            "raster_id": entry["raster_id"],
            "rule_D3": "Permanent water is a LAND-COVER FACT, never 'beyond "
                       "very high' - but it is NOT benign. This is the "
                       "Budalangi signal: HAND cannot see dike failure."}
    except BaseException as exc:
        print(f"      ! permanent water search failed: {type(exc).__name__}")


def layer_soils(cat, geom, out, conf, src):
    """Soil type, pH, texture - and RULE D7 black cotton from BOTH layers."""
    vertisol_pct = clay_pct = None

    e = cat.get("soil_type")
    if e:
        vals, _ = sample(e["path"], geom)
        comp, dominant, npix = composition(vals, WRB)
        if comp:
            out["soil_composition"] = json.dumps(comp)
            out["soil_type"] = dominant
            vertisol_pct = comp.get("Vertisols", 0.0)
            conf["soil_type"] = e["confidence"] or 3
            src["soil_type"] = {
                "raster_id": e["raster_id"], "n_pixels": npix,
                "small_sample": npix < 20,
                "caveat": "SoilGrids publishes the MOST PROBABLE class, which "
                          "favours common groups. Dependable for a strong "
                          "signal, not for fine agricultural distinction."}

    e = cat.get("texture")
    if e is None:
        e = cat.get("texture_class")
    if e:
        vals, _ = sample(e["path"], geom)
        comp, dominant, npix = composition(vals, TEXTURE)
        if comp:
            out["soil_texture"] = dominant
            clay_pct = sum(v for k, v in comp.items()
                           if k in {TEXTURE[c] for c in CLAY_TEXTURES})
            conf["soil_texture"] = e["confidence"] or 3
            src["soil_texture"] = {"raster_id": e["raster_id"],
                                   "n_pixels": npix,
                                   "small_sample": npix < 20,
                                   "composition": comp}

    e = cat.get("ph")
    if e:
        vals, scale = sample(e["path"], geom)
        if vals is not None:
            out["soil_ph"] = round(float(np.mean(vals)) * scale, 2)
            conf["soil_ph"] = e["confidence"] or 3
            src["soil_ph"] = {"raster_id": e["raster_id"]}

    return vertisol_pct, clay_pct


# Ground flat enough that the black cotton taxonomy check cannot clear it.
# Degrees, because slope_mean_pct holds degrees (the column name predates the
# layer). 3.5 deg was living as a bare literal in TWO places in
# report_content.py and in NEITHER place in the engine that knows the rule.
# That is a reminder, not a control - so the engine now decides and the
# renderers ask the row.
BLACK_COTTON_FLAT_DEG = 3.5

# FIELDS WE DO NOT SOURCE, AND WHY - so that a NULL can be read.
#
# A NULL means two completely different things and nothing in the row said
# which: "we searched 25 km and found none" (dist_water_point_m carries its
# search_radius_m and is honest) versus "no such layer exists in this
# database" (dist_power_line_m carried nothing at all). A renderer cannot
# tell them apart, so it drops both - which is safe but means a report can
# never say "no power line within X km" even when that is the fact a buyer
# most wants.
#
# These entries are written into field_sources for every parcel. They are
# claims about OUR COVERAGE, not about the ground, and they must never be
# rendered as a statement about the parcel.
#
# Checklist references are only given where one exists. Where no source has
# been identified at all, this says so rather than inventing a reference.
NOT_SOURCED = {
    "dist_power_line_m": ("Kenya Power transmission and distribution data has "
                          "been requested and not received. Checklist A5."),
    "dist_transformer_m": ("Kenya Power transformer locations - same request, "
                           "same status. Checklist A5."),
    "dist_water_line_m": ("WASREB / Majidata reticulation. Buried mains are "
                          "absent from OSM by their nature, so there is no "
                          "open substitute. Checklist B7."),
    "dist_sewer_m": ("WASREB / Majidata sewerage. Same reason, same letter. "
                     "Checklist B7."),
    "zoning_class": ("County zoning is held by each county government and is "
                     "not published in machine-readable form. Checklist B6."),
    "dist_fiber_m": ("No source identified. Operator fibre routes are not "
                     "published and no checklist item is open for them."),
    "in_wetland": ("No wetland inventory loaded. RAMSAR covers designated "
                   "sites only and would answer False almost everywhere, "
                   "which reads as a clearance we cannot give."),
    "landslide_risk_class": ("No landslide susceptibility layer loaded. The "
                             "DEM could support one; nothing has been built "
                             "or validated."),
    "travel_time_town_min": ("Needs routing over the road network, not a "
                             "straight-line distance. Not built."),
    "elevation_mean_m": "Derivable from the DEM already held. Not computed.",
    "elevation_min_m": "Derivable from the DEM already held. Not computed.",
    "elevation_max_m": "Derivable from the DEM already held. Not computed.",
    "slope_max_pct": "Derivable from the slope raster already held. Not computed.",
    "aspect_dominant": "Derivable from the DEM already held. Not computed.",
    "twi_mean": "Derivable from the DEM already held. Not computed.",
    "soil_drainage": ("SoilGrids publishes no drainage class. Would have to be "
                      "inferred from texture and landform, which is a "
                      "judgement this engine does not make."),
    "soil_depth_class": ("SoilGrids depth-to-bedrock exists but is not loaded "
                         "or validated."),
    "soil_fertility": ("A composite judgement, not a measurement. Not defined "
                       "and deliberately not guessed."),
    "temp_mean_c": "No temperature raster loaded.",
    "solar_kwh_m2_day": "No solar irradiance raster loaded.",
    # Conditional entries. stamp_not_sourced only writes where the field came
    # back NULL and no layer claimed it, so these disappear by themselves on
    # any parcel where the value IS answered.
    "dist_protected_area_m": (
        "in_protected_area was answered, but only a COMMERCIALLY USABLE "
        "source can supply a distance we are allowed to publish, and none "
        "answered for this parcel. WDPA may know and is non-commercial. "
        "Checklist A1."),
    "coverage_4g_pct_safaricom": (
        "PER-OPERATOR 4G IS NOT SHIPPED AND WILL NOT BE until the CA "
        "confirms attribution - measured, all 10,357 Safaricom polygons "
        "ST_Equals a Telkom polygon and the source layers are two separately "
        "named CA files with identical polygon counts and identical total "
        "area. One measurement, two operator labels, and we do not know "
        "whose network it describes. Checklist A2/B1."),
    "coverage_4g_pct_telkom": (
        "PER-OPERATOR 4G IS NOT SHIPPED AND WILL NOT BE until the CA "
        "confirms attribution - see coverage_4g_pct_safaricom. Checklist "
        "A2/B1."),
}


def stamp_not_sourced(out, src):
    """Write the coverage reason for every field we hold no source for.

    Only stamps a field the layers did not answer. If a layer ever starts
    answering one of these, its own field_sources entry wins and the field
    silently leaves this set - which is the correct behaviour and needs no
    edit here.
    """
    for col, why in NOT_SOURCED.items():
        if out.get(col) is None and col not in src:
            src[col] = {"not_sourced": True, "reason": why,
                        "READ_AS": "A NULL here is a gap in OUR DATA, not a "
                                   "finding about this parcel. It must never "
                                   "be rendered as an absence on the ground."}


def layer_black_cotton(cat, geom, vertisol_pct, clay_pct, out, conf, src):
    """RULE D7, with a THIRD signal added after run 2 exposed the flaw.

    Run 1 flagged Karen as possible black cotton. Karen is NITISOLS - the deep
    red coffee soil of the central highlands. Clay-rich, certainly, but the
    clay is kaolinite: it does not shrink and swell.

    THAT IS THE HOLE IN A TWO-LAYER RULE. Texture measures how MUCH clay is
    present. Black cotton is about WHICH clay - smectite, which expands. Both
    Nitisols (Karen, safe) and the Athi-Kapiti plains (real black cotton) read
    clay-rich, so texture cannot separate them, and tightening the texture
    threshold to fix Karen made the Athi case return 'none' - losing the one
    case rule D7 exists for.

    THE THIRD SIGNAL IS LANDFORM. Vertisols form on FLAT, seasonally
    waterlogged ground where water sits and clay accumulates. The Athi-Kapiti
    plains are flat. Karen sits on the Ngong slopes. Slope is a layer we
    already hold, at confidence 4 - higher than either soil layer.

    This is the same move as the flood layer's catchment scaling: when two
    signals cannot be reconciled, the missing term is usually physical.
    """
    slope_mean = None
    e = cat.get("slope")
    if e:
        vals, scale = sample(e["path"], geom)
        if vals is not None:
            slope_mean = float(np.mean(vals)) * scale
            out["slope_mean_pct"] = round(slope_mean, 2)
            conf["slope_mean_pct"] = e["confidence"] or 4
            src["slope_mean_pct"] = {"raster_id": e["raster_id"],
                                     "units": "degrees (NOT percent - the "
                                              "column name predates the "
                                              "layer)"}

    if vertisol_pct is None and clay_pct is None:
        # No soil data at all. black_cotton_risk stays NULL, and the
        # inconclusive flag must still be TRUE - failing closed. A NULL flag
        # would be falsy at every renderer, which is the one reading of "we
        # have no idea" that must never happen here.
        out["black_cotton_inconclusive"] = True
        src["black_cotton_inconclusive"] = {
            "basis": "no soil data for this parcel - neither SoilGrids "
                     "taxonomy nor iSDA texture returned a value",
            "MEANING": "THE CHECK DID NOT RUN. A soil test is needed and "
                       "nothing here may be presented as a clearance.",
            "checklist": "C16"}
        return
    v = (vertisol_pct or 0.0) >= 20.0                 # SoilGrids says Vertisol

    # VERTISOLS ONLY. Three formulations were tried and measured:
    #
    #   1. Vertisols OR clay texture (classes 1-5)
    #        -> flagged Karen (Nitisols, deep red coffee soil, stable clay)
    #           and the Aberdares (Andosols, volcanic)
    #   2. Vertisols OR clay texture (classes 1-2 only)
    #        -> lost the Athi-Kapiti case entirely, which is the ONE case
    #           rule D7 exists for
    #   3. Vertisols OR (clay AND flat ground)
    #        -> still lost Athi, still flagged Karen
    #
    # The measurements say why, and they are decisive:
    #
    #       parcel   soil       texture     clay%   slope
    #       Athi     Luvisols   Clay Loam   < 30    2.94 deg   <- IS black cotton
    #       Karen    Nitisols   Clay Loam   >= 30   1.04 deg   <- IS NOT
    #
    # BOTH DISCRIMINATORS POINT THE WRONG WAY. Texture says Karen is the
    # clayer of the two; slope says Karen is the flatter. Adding a third
    # signal did not help because the third signal disagrees as well.
    #
    # Rule E6: "if you have changed the same constant twice, stop changing it.
    # If no value satisfies the constraints, the model is wrong, not the
    # constant." Three formulations is past that line.
    #
    # SoilGrids + iSDA + slope CANNOT separate these two cases. So this column
    # now reports only what is reliable - the taxonomy - and the Athi-Kapiti
    # under-detection is carried as a NAMED GAP rather than papered over. A
    # verdict that is wrong on prime Nairobi land is worse than an honest
    # absence of one.
    out["black_cotton_risk"] = "likely" if v else "none"
    conf["black_cotton_risk"] = 3 if v else 2
    src["black_cotton_risk"] = {
        "rule_D7_STATUS": "PARTIALLY IMPLEMENTED - taxonomy arm only",
        "basis": "SoilGrids Vertisols share of the parcel",
        "vertisols_pct": vertisol_pct,
        "clay_texture_pct": clay_pct,
        "slope_deg": round(slope_mean, 2) if slope_mean is not None else None,
        "KNOWN GAP": "'none' does NOT mean 'no black cotton'. SoilGrids maps "
                     "the Athi-Kapiti plains as Luvisols on two separate "
                     "probes, and those plains ARE classic black cotton AND "
                     "are where Nairobi peri-urban selling is most active. "
                     "Measured on the test parcels, iSDA texture and slope "
                     "both point the WRONG WAY between Athi and Karen, so "
                     "neither can rescue the miss. Checklist C16.",
        "buyer_facing_rule": "Where this reads 'none' on flat peri-urban land "
                             "around Nairobi, the report must say the check is "
                             "inconclusive - NOT that the ground is safe."}

    # THE RULE ABOVE IS NOW A COLUMN, because prose in field_sources cannot
    # stop a renderer. Until now the 3.5 deg test lived twice in
    # report_content.py and nowhere here, so the engine that knows why the
    # rule exists was not the thing applying it.
    #
    # FAILS TOWARD INCONCLUSIVE. Unknown slope counts as flat: if we cannot
    # see the landform we certainly cannot clear the soil, and the whole point
    # of C16 is that 'none' is not a clearance.
    #
    # This fires on Karen too, which is Nitisols and genuinely stable. That is
    # accepted and it is not a bug: SoilGrids cannot separate Karen from Athi
    # on any signal we hold (see the table above), so the honest statement on
    # flat ground is that the check does not settle it. Over-flagging costs a
    # seller one line of caution. Under-flagging puts a house on ground that
    # moves.
    #
    # Geography is deliberately NOT part of the test. 'Peri-urban Nairobi' has
    # no boundary in this database, and inventing one would be a claim we
    # cannot source (D20).
    out["black_cotton_inconclusive"] = bool(
        not v and (slope_mean is None or slope_mean < BLACK_COTTON_FLAT_DEG))
    if out["black_cotton_inconclusive"]:
        why_slope = ("slope unknown" if slope_mean is None
                     else "slope %.2f deg < %.1f deg"
                          % (slope_mean, BLACK_COTTON_FLAT_DEG))
        src["black_cotton_inconclusive"] = {
            "basis": "black_cotton_risk = 'none' AND " + why_slope,
            "threshold_deg": BLACK_COTTON_FLAT_DEG,
            "MEANING": "THE CHECK DID NOT SETTLE IT. Not 'safe', not "
                       "'expansive'. The report must say a soil test is "
                       "needed and must not present 'none' as a clearance.",
            "checklist": "C16"}


def layer_rainfall(cat, geom, out, conf, src):
    """Normal, range, and the drought signal a mean conceals."""
    e = cat.get("rainfall")
    if e:
        vals, scale = sample(e["path"], geom)
        if vals is not None:
            v = vals * scale
            out["rainfall_normal_mm_yr"] = round(float(np.mean(v)), 1)
            out["rainfall_min_mm_yr"] = round(float(np.min(v)), 1)
            out["rainfall_max_mm_yr"] = round(float(np.max(v)), 1)
            conf["rainfall_normal_mm_yr"] = e["confidence"] or 3
            src["rainfall_normal_mm_yr"] = {
                "raster_id": e["raster_id"],
                "rule_C5": "THIS LAYER RUNS WET, about +145 mm across 16 "
                           "reference towns. Not calibrated - do not quote to "
                           "a precision it has not earned.",
                "note": f"min/max over {v.size} CHIRPS cells at ~5 km. A "
                        f"parcel inside one cell SHOULD return min = max = "
                        f"mean; a spread there would be invented."}

    for variable, column in (("rainfall_recent_mean", "rainfall_recent_mm_yr"),
                             ("rainfall_anomaly_pct", "rainfall_anomaly_pct"),
                             ("rainfall_driest_year_pct",
                              "rainfall_driest_year_pct"),
                             ("rainfall_max5day_mean",
                              "rainfall_max5day_mean_mm"),
                             ("rainfall_max5day_p90",
                              "rainfall_max5day_p90_mm")):
        e = cat.get(variable)
        if not e:
            continue
        vals, scale = sample(e["path"], geom)
        if vals is None:
            continue
        out[column] = round(float(np.mean(vals * scale)), 1)
        conf[column] = e["confidence"] or 3
        src[column] = {"raster_id": e["raster_id"]}

    if "rainfall_max5day_mean_mm" in out:
        out["flood_forcing_max5day_mm"] = out["rainfall_max5day_mean_mm"]
        src["flood_forcing_max5day_mm"] = {
            "purpose": "susceptibility x forcing. HAND says where water goes; "
                       "this says how much arrives. Present as TWO numbers, "
                       "never merged into one score with invented weights.",
            "caveat": "CHIRPS v2.0 fixed pentads UNDER-ESTIMATE a true rolling "
                      "5-day maximum by roughly 10-20%. Not design rainfall."}


def layer_ndvi(cat, geom, out, conf, src):
    """Greenness. The other half of rule D6, and checklist C6's caveat."""
    e = cat.get("ndvi")
    if not e:
        return
    vals, scale = sample(e["path"], geom, nodata_hint=e.get("nodata"))
    if vals is None:
        return
    mean = round(float(np.mean(vals)) * scale, 3)
    lo, hi = NDVI_RANGE
    if not (lo <= mean <= hi):
        # DO NOT GUESS THE SCALE. Refuse the value and name the fault.
        print(f"      ! ndvi_mean = {mean} is outside [{lo}, {hi}] - "
              f"NOT WRITTEN")
        src["ndvi_mean"] = {
            "raster_id": e["raster_id"],
            "REFUSED": f"raw mean {mean} outside the physical NDVI range "
                       f"[{lo}, {hi}]. Almost certainly a missing scale tag "
                       f"on the COG (etl_23 stores Int16 with scale 0.0001). "
                       f"The engine does not invent a scale factor - fix the "
                       f"raster or the catalogue row."}
        return
    out["ndvi_mean"] = mean
    out["ndvi_year"] = e.get("year")
    conf["ndvi_mean"] = e["confidence"] or 4
    src["ndvi_mean"] = {
        "raster_id": e["raster_id"], "year": e.get("year"),
        "n_pixels": int(vals.size),
        "min": round(float(np.min(vals)) * scale, 3),
        "max": round(float(np.max(vals)) * scale, 3),
        "rule_C6": "SINGLE YEAR, NOT A NORMAL. 2024 was wet after the 2020-23 "
                   "drought, so this reads greener than a typical year. Do "
                   "not present it as the parcel's usual condition until a "
                   "multi-year composite exists.",
        "rule_D6": "This is the layer that shows land cover under-detects "
                   "smallholder farming - up to 4.2x the mapped cropland area "
                   "is as green as cropland. Use NDVI + rainfall + soil "
                   "TOGETHER, never land cover alone, to say anything about "
                   "whether a parcel can be farmed."}


def layer_landcover(cat, geom, out, conf, src):
    """BOTH producers, side by side, never reconciled into one word.

    WorldCover 2021 at 10 m and Impact Observatory at ~93 m are not comparable
    class by class - IO's Rangeland absorbs WorldCover's Shrubland AND
    Grassland. Collapsing them into a single "land cover" answer would be
    inventing agreement that the products do not have.
    """
    e = cat.get("landcover")
    if e:
        vals, _ = sample(e["path"], geom, nodata_hint=e.get("nodata"))
        comp, dominant, npix = composition(vals, WORLDCOVER)
        if comp:
            out["landcover_composition"] = json.dumps(comp)
            out["landcover_class_worldcover"] = dominant
            conf["landcover_class_worldcover"] = e["confidence"] or 4
            src["landcover_class_worldcover"] = {
                "raster_id": e["raster_id"], "n_pixels": npix, "pixel_m": 10,
                "small_sample": npix < 20,
                "producer": "ESA WorldCover 2021 v200",
                "dominant_pct": comp.get(dominant),
                "rule_D6": ("DOMINANT CLASS IS NOT A VERDICT ON FARMABILITY. "
                            "WorldCover under-detects smallholder mosaic "
                            "farming. Check ndvi_mean before this class goes "
                            "anywhere near the word 'farmland'."
                            if dominant in NOT_FARMLAND_TRAP else None),
                "rule_C9": "ESA has published nothing after 2021 v200. This "
                           "class is four years old; recent conversion will "
                           "be absent."}

    # Impact Observatory: take the LATEST year present. Each year is its own
    # variable (landcover_io_2017 / _2023 / _2024), which is what a catalogue
    # variable is supposed to be - contrast 'nightlights', which is not.
    io_vars = sorted(v for v in cat
                     if v.startswith("landcover_io_") and v[13:].isdigit())
    if io_vars:
        latest = io_vars[-1]
        e = cat[latest]
        vals, _ = sample(e["path"], geom, nodata_hint=e.get("nodata"))
        comp, dominant, npix = composition(vals, IO_CLASSES)
        if comp:
            out["landcover_class_io"] = dominant
            out["landcover_io_year"] = int(latest[13:])
            conf["landcover_class_io"] = e["confidence"] or 4
            src["landcover_class_io"] = {
                "raster_id": e["raster_id"], "n_pixels": npix, "pixel_m": 93,
                "small_sample": npix < 20, "composition": comp,
                "producer": f"Impact Observatory {latest[13:]}",
                "years_available": [int(v[13:]) for v in io_vars],
                "rule_C13": "IO IS NOT TEMPORALLY CONSISTENT. The yearly "
                            "snapshots ship; landcover_change is quarantined "
                            "at pending_review because class shifts arrive as "
                            "STEPS at single year boundaries - a retrained "
                            "classifier, not ground change. NEVER compute a "
                            "change between two of these years here.",
                "vs_worldcover": "IO 'Rangeland' = WorldCover Shrubland PLUS "
                                 "Grassland. The two cannot be compared class "
                                 "by class and this engine does not try. Where "
                                 "they disagree, show both."}


def layer_builtup(cat, geom_buf, buf_area_m2, out, conf, src):
    """RULE D8, in its general form.

    D8 says a full GHSL cell is 8,606 m2 - not 8,548 - and the fraction must
    be capped at 1.0, because GHSL is computed on Mollweide and regridded, and
    the wrong divisor makes a parcel read "101% built".

    The general form of that rule is: SUM the square metres, divide by the
    TRUE AREA of the region as PostGIS measures it on the geography type, then
    cap. Counting cells and multiplying by a nominal cell size is precisely
    how the 8,548 error happens - so this never does that.

    THE NEIGHBOURHOOD, NOT THE PARCEL. See BUILTUP_RADIUS_M.
    """
    e = cat.get("builtup")
    if not e or not buf_area_m2:
        return
    vals, _ = sample(e["path"], geom_buf, nodata_hint=e.get("nodata"))
    if vals is None:
        return
    built_m2 = float(np.sum(vals))
    frac = built_m2 / float(buf_area_m2)
    out["built_up_pct_1km"] = round(100.0 * min(frac, 1.0), 2)
    conf["built_up_pct_1km"] = e["confidence"] or 4
    src["built_up_pct_1km"] = {
        "raster_id": e["raster_id"],
        "radius_m": BUILTUP_RADIUS_M,
        "built_m2": round(built_m2),
        "area_m2": round(float(buf_area_m2)),
        "rule_D8_capped": frac > 1.0,
        "units": "GHSL stores SQUARE METRES OF BUILT SURFACE per cell, NOT a "
                 "percentage. Summed here and divided by the TRUE geography "
                 "area of the buffer, then capped at 100%.",
        "epoch": "GHS-BUILT-S R2023A epoch 2020 - an OBSERVED epoch, not a "
                 "projection, and five years old. New estates will be absent, "
                 "which matters most on exactly the peri-urban land that "
                 "sells fastest.",
        "shape": "a NEIGHBOURHOOD figure, like mobile coverage - phrase it "
                 "that way, never as a property of the parcel"}
    if frac > 1.0:
        print(f"      ! built-up came to {100 * frac:.1f}% before the D8 cap "
              f"- check the divisor")


def layer_environment(engine, parcel_id, out, conf, src, srcidx):
    """Riparian buffers, rivers, protected areas.

    THE SHARPEST LICENCE EXPOSURE IN THE PRODUCT IS IN THIS FUNCTION, and the
    engine states it on the field rather than leaving it in a memo:

      environment.riparian_buffers is DERIVED GEOMETRY cut from OSM rivers.
      That makes it unambiguously a database under ODbL, and it is also the
      differentiator (checklist A4, HIGH exposure).

      environment.protected_areas holds BOTH OSM and WDPA features, and WDPA
      is NON-COMMERCIAL (checklist A1). Which one answered is resolved from
      metadata.sources at run time and named on the field.
    """
    # ---- riparian buffer: the most consequential boolean the engine writes
    with engine.connect() as conn:
        rip = conn.execute(text("""
            SELECT round((100 * ST_Area(ST_Intersection(
                            ST_Union(b.geom), p.geom)::geography)
                          / NULLIF(ST_Area(p.geom::geography), 0))::numeric, 2),
                   min(b.buffer_width_m), min(b.confidence),
                   string_agg(DISTINCT b.legal_basis, '; '),
                   min(b.source_id)
              FROM land.parcels p
              JOIN environment.riparian_buffers b
                ON b.status = 'active' AND ST_Intersects(b.geom, p.geom)
             WHERE p.parcel_id = :pid
             GROUP BY p.geom
        """), {"pid": parcel_id}).one_or_none()
    if rip:
        out["in_riparian_buffer"] = True
        conf["in_riparian_buffer"] = rip[2] or 3
        src["in_riparian_buffer"] = {
            "layer": "environment.riparian_buffers",
            "pct_of_parcel_inside": float(rip[0] or 0),
            "narrowest_buffer_m": float(rip[1]) if rip[1] is not None else None,
            "legal_basis": rip[3],
            **srcidx.get(rip[4] or -1, {}),
            "MEANING": "A riparian reserve is LAND YOU MAY NOT BUILD ON. This "
                       "is the most consequential boolean this engine writes, "
                       "and it must always be shown WITH THE SHARE of the "
                       "parcel affected - 3% clipped off a corner and 60% of "
                       "the plot are different properties, and 'true' says "
                       "the same thing about both.",
            "rule_A4": "DERIVED FROM OSM RIVERS - ODbL share-alike, and the "
                       "HIGH-exposure item in LICENSING_OPTIONS_MEMO.md. "
                       "Replacing the river network (WRA, checklist B2) "
                       "removes this exposure entirely.",
            "caveat": "widths are the EMCA statutory 6 m / 30 m applied to a "
                      "MAPPED CENTRELINE. A real reserve is measured from the "
                      "bank by a surveyor, and the bank is not the centreline."}
    else:
        out["in_riparian_buffer"] = False
        src["in_riparian_buffer"] = {
            "layer": "environment.riparian_buffers",
            "result": "no mapped riparian buffer intersects this parcel",
            "NOT_A_CLEARANCE": "FALSE HERE MEANS 'NO MAPPED WATERCOURSE', NOT "
                               "'NO RESERVE APPLIES'. OSM's coverage of "
                               "seasonal watercourses is incomplete, and "
                               "river_class has been NULL since session 2 "
                               "(checklist B2), so we cannot even say which "
                               "mapped channels are perennial. A buyer must "
                               "not read this as permission to build."}

    # ---- nearest river
    with engine.connect() as conn:
        rv = conn.execute(text("""
            SELECT round(ST_Distance(p.geom::geography, r.geom::geography)),
                   r.name, r.river_class, r.waterway_type, r.source_id,
                   r.confidence
              FROM land.parcels p, environment.rivers r
             WHERE p.parcel_id = :pid AND r.status = 'active'
               AND ST_DWithin(p.geom::geography, r.geom::geography, :d)
             ORDER BY p.geom <-> r.geom LIMIT 1
        """), {"pid": parcel_id, "d": SEARCH_M["river"]}).one_or_none()
    if rv:
        out["dist_river_m"] = float(rv[0])
        conf["dist_river_m"] = rv[5] or 3
        src["dist_river_m"] = {
            "layer": "environment.rivers", "name": rv[1],
            "river_class": rv[2], "waterway_type": rv[3],
            **srcidx.get(rv[4] or -1, {}),
            "search_radius_m": SEARCH_M["river"],
            "rule_B2": "river_class HAS BEEN NULL SINCE SESSION 2. We cannot "
                       "distinguish a perennial river from a seasonal luggah, "
                       "and that difference is most of what a buyer is asking. "
                       "WRA is the source for it."}
        if out["dist_river_m"] == 0.0:
            src["dist_river_m"]["INSIDE_THE_PARCEL"] = (
                "0 m IS CONTAINMENT: A WATERCOURSE CROSSES THIS PARCEL. That "
                "is one of the most consequential facts about a plot in this "
                "market - it carries a riparian reserve, it constrains the "
                "build, and it is why in_riparian_buffer must be read "
                "alongside this. Never render it as '0 m'.")
    else:
        src["dist_river_m"] = {
            "layer": "environment.rivers",
            "result": f"no mapped river within {SEARCH_M['river']:.0f} m",
            "NOT_ZERO": "a blank is NOT MAPPED WITHIN RANGE. Never render it "
                        "as 0 m or as 'no river nearby' without the radius."}

    # ---- protected areas: checklist A1 lives here
    #
    # A1 WAS DOWNGRADED FROM A BLOCKER TO A LATER IMPROVEMENT, AND THAT
    # DECISION ONLY HOLDS IF THIS QUERY STOPS PREFERRING WDPA.
    #
    # environment.protected_areas holds BOTH the OSM layer (etl_06, ODbL,
    # confidence 3) and WDPA (etl_09, NON-COMMERCIAL). The original query took
    # the nearest feature from either, and WDPA won on 19 of 20 parcels simply
    # because it is denser. So the field a buyer sees has been answered by
    # data we may not sell, on almost every parcel.
    #
    # While A1 was an open blocker that was tolerable - the letter was coming.
    # Once A1 is deferred, "we will fix the licence later" becomes "we ship
    # non-commercial data indefinitely", which is a different and worse
    # position. The fix is not to send the letter faster; it is to stop
    # depending on the source.
    #
    # So: commercially usable sources answer the field. WDPA is still queried,
    # SEPARATELY, and where the two disagree that disagreement is recorded on
    # the field rather than discarded - it is the honest measure of what
    # deferring A1 costs us, and the evidence for reopening it later.
    with engine.connect() as conn:
        bad_ids = [sid for sid, meta in (srcidx or {}).items()
                   if "wdpa" in str(meta.get("source", "")).lower()
                   or "wdpa" in str(meta.get("licence", "")).lower()
                   or meta.get("redistribution_allowed") is False]
        PA_SQL = """
            SELECT ST_Intersects(a.geom, p.geom),
                   round(ST_Distance(p.geom::geography, a.geom::geography)),
                   a.name, a.area_type, a.authority, a.source_id, a.confidence
              FROM land.parcels p, environment.protected_areas a
             WHERE p.parcel_id = :pid AND a.status = 'active'
               AND ST_DWithin(p.geom::geography, a.geom::geography, :d)
               {clause}
             ORDER BY p.geom <-> a.geom LIMIT 1"""
        args = {"pid": parcel_id, "d": SEARCH_M["protected_area"]}
        pa = conn.execute(
            text(PA_SQL.format(
                clause="AND a.source_id <> ALL(:bad)" if bad_ids else "")),
            {**args, **({"bad": bad_ids} if bad_ids else {})}).one_or_none()
        pa_nc = None
        if bad_ids:
            pa_nc = conn.execute(
                text(PA_SQL.format(clause="AND a.source_id = ANY(:bad)")),
                {**args, "bad": bad_ids}).one_or_none()

    if pa:
        lic = srcidx.get(pa[5] or -1, {})
        non_commercial = "wdpa" in str(lic.get("source", "")).lower() \
            or "wdpa" in str(lic.get("licence", "")).lower() \
            or lic.get("redistribution_allowed") is False
        out["in_protected_area"] = bool(pa[0])
        out["dist_protected_area_m"] = 0.0 if pa[0] else float(pa[1])
        conf["in_protected_area"] = pa[6] or 2
        src["in_protected_area"] = {
            "layer": "environment.protected_areas", "name": pa[2],
            "area_type": pa[3], "authority": pa[4], **lic,
            "search_radius_m": SEARCH_M["protected_area"],
            "rule_A1": ("*** THIS ANSWER CAME FROM A SOURCE THAT IS NOT "
                        "CLEARED FOR COMMERCIAL REDISTRIBUTION. Do not ship "
                        "this field in a paid report until KWS data replaces "
                        "it or written clearance is on file. Checklist A1. ***"
                        if non_commercial else
                        "source is commercially usable per metadata.sources; "
                        "re-check A1 if this layer is ever reloaded"),
            "caveat": "area_type is inferred from the feature NAME where OSM "
                      "supplied no class. PROXIMITY TO A PARK IS NOT A LEGAL "
                      "DETERMINATION - the gazette notice is."}
        if bool(pa[0]):
            src["in_protected_area"]["INSIDE_THE_PARCEL"] = (
                "dist_protected_area_m = 0 BECAUSE THE PARCEL INTERSECTS THE "
                "PROTECTED AREA, not because it is 0 m away. Land inside a "
                "gazetted area is normally not saleable at all - this is a "
                "stop-work finding, not a proximity score.")
        # WHAT DEFERRING A1 ACTUALLY COSTS, MEASURED PER PARCEL.
        # WDPA is denser than the OSM layer, so on some parcels it sees a
        # protected area that OSM does not. Silently dropping WDPA would turn
        # those into a quiet "no" - the worst possible outcome, because
        # `in_protected_area = False` is what lets a parcel be SCORED and sold.
        # Where the two sources disagree, the disagreement is written onto the
        # field. It is the evidence for reopening A1, and it means the day KWS
        # arrives we can say exactly which parcels change.
        if pa_nc is not None and bool(pa_nc[0]) and not bool(pa[0]):
            src["in_protected_area"]["A1_SOURCES_DISAGREE"] = (
                "COMMERCIAL SOURCES SAY NO; WDPA SAYS YES. WDPA places this "
                f"parcel INSIDE '{pa_nc[2]}' ({pa_nc[3]}). WDPA is not "
                "cleared for commercial redistribution so it cannot answer "
                "the field, but it is not therefore wrong. TREAT THIS PARCEL "
                "AS UNRESOLVED, not as clear ground, until KWS data or "
                "written WDPA clearance settles it. Checklist A1.")
            conf["in_protected_area"] = min(conf.get("in_protected_area", 2), 2)
        src["dist_protected_area_m"] = src["in_protected_area"]
    # THE CONDITION IS `INSIDE`, NOT `FOUND ANYTHING`.
    #
    # The first version of this branch read `elif pa_nc is not None:` - true
    # whenever WDPA had ANY feature inside the search radius, which is tens
    # of kilometres. On the twenty test parcels that fired on nineteen, and
    # the run blocked Karen, Ruai and every OAK GROVE plot as "protected area
    # unresolved". A park 20 km away is not an unresolved question about this
    # parcel; it is a clear no.
    #
    # Two errors in the same twenty lines, in opposite directions: the first
    # turned parks into saleable land, the second turned Nairobi suburbs into
    # parks. Both came from treating a THREE-state answer - inside / not
    # inside / cannot tell - as if it had two. The state machine is now
    # written out explicitly rather than inferred from what happened to be
    # non-None:
    #
    #     commercial source answered          -> use it (note if WDPA differs)
    #     silent, and WDPA says INSIDE        -> UNRESOLVED, block the score
    #     silent, and WDPA says near or none  -> False, and that is an answer
    elif pa_nc is not None and bool(pa_nc[0]):
        # THE FAILURE THIS BRANCH EXISTS FOR, AND IT WAS SHIPPED BROKEN ONCE.
        #
        # When commercial sources find NOTHING and WDPA finds the parcel
        # inside a park, the first version of this change fell through to the
        # plain "no protected area nearby" branch below and wrote
        # `in_protected_area = False` in silence. The disagreement note was
        # written inside `if pa:` and could never run here.
        #
        # That is the worst possible outcome and it is not a near miss - it
        # happened. TEST-ABERDARES-01, TEST-KAKAMEGA-01 and
        # TEST-TANADELTA-01 had been correctly BLOCKED from scoring on WDPA
        # boundaries. After the change they read False, and `False` is
        # precisely what lets a parcel be scored, priced and sold. Three
        # national parks and a gazetted forest became saleable land because a
        # licence question was deferred.
        #
        # A source we may not PUBLISH is not a source we may not KNOW. WDPA
        # cannot answer the field. It can still stop us answering it wrongly.
        out["in_protected_area"] = None
        out["dist_protected_area_m"] = None
        conf["in_protected_area"] = 1
        src["in_protected_area"] = {
            "layer": "environment.protected_areas",
            "RESULT": "UNRESOLVED - deliberately NOT False.",
            "why": ("No commercially usable source covers this parcel, and "
                    f"WDPA places it INSIDE '{pa_nc[2]}' ({pa_nc[3]}). WDPA "
                    "is not cleared for commercial redistribution so it "
                    "cannot answer the field."),
            "DO_NOT_READ_AS_CLEAR": (
                "A NULL here means WE DO NOT KNOW. It must not be scored, "
                "and it must not be shown to a buyer as 'not in a protected "
                "area'. Land inside a gazetted area is normally not saleable "
                "at all, so the cost of guessing wrong is total."),
            "unblocks_when": "KWS data lands (A1), or written WDPA clearance."}
    else:
        out["in_protected_area"] = False
        src["in_protected_area"] = {
            "layer": "environment.protected_areas",
            "result": f"no protected area within "
                      f"{SEARCH_M['protected_area']:.0f} m",
            "note": ("Checked against commercially usable sources AND, "
                     "separately, against WDPA. Neither places this parcel "
                     "INSIDE a protected area, so False is an answer rather "
                     "than an absence of one. dist_protected_area_m may be "
                     "NULL even so: only a commercially usable source can "
                     "supply a distance we are allowed to publish.")}


def layer_admin_stats(engine, parcel_id, out, conf, src):
    """Population and nightlights. BOTH WARD-LEVEL, BOTH FROM THEIR OWN TABLE.

    NOT FROM THE RASTER CATALOGUE. cat['nightlights'] names five active
    rasters, one per year, so sampling it would silently return whichever year
    was catalogued last (checklist E11 - this is the defect the engine now
    reports at startup). demographics.nightlights_stats is keyed properly by
    admin_level / admin_code / period, so it is the only correct source.

    THE WARD IS RESOLVED SPATIALLY, and with the SAME COALESCE that etl_21 and
    etl_26 used to build the codes: COALESCE(ward_code, 'LIP-W'||id). Joining
    on land.parcels.ward_code instead would return NULL for every parcel a
    client uploads without one, and it would do it silently.
    """
    with engine.connect() as conn:
        ward = conn.execute(text("""
            SELECT COALESCE(w.ward_code, 'LIP-W' || w.id::text) AS code,
                   w.name, w.ward_code IS NULL AS provisional
              FROM land.parcels p
              JOIN admin.wards w
                ON w.status = 'active'
               AND ST_Intersects(w.geom, ST_Centroid(p.geom))
             WHERE p.parcel_id = :pid
             LIMIT 1
        """), {"pid": parcel_id}).one_or_none()
    if ward is None:
        src["ward_lookup"] = {
            "result": "NO WARD CONTAINS THIS PARCEL'S CENTROID",
            "consequence": "population and nightlights cannot be looked up",
            "check": "is the parcel outside Kenya, or is its geometry wrong? "
                     "This should be impossible for a real Kenyan plot."}
        return
    code, ward_name, provisional = ward
    ward_note = {
        "ward": ward_name, "ward_code": code,
        "provisional_code": bool(provisional),
        "rule_C4": ("THIS WARD CARRIES A PROVISIONAL 'LIP-W' CODE, not an "
                    "official IEBC one. 1,425 wards are in this state. Search "
                    "'LIP-W' before any external join or hand-off."
                    if provisional else None)}

    with engine.connect() as conn:
        pop = conn.execute(text("""
            SELECT density_per_km2, population, year, confidence
              FROM demographics.population_stats
             WHERE admin_level = 'ward' AND admin_code = :c
               AND status = 'active'
             ORDER BY year DESC LIMIT 1
        """), {"c": code}).one_or_none()
        nl = conn.execute(text("""
            SELECT radiance_mean, trend_radiance_yr, period, confidence
              FROM demographics.nightlights_stats
             WHERE admin_level = 'ward' AND admin_code = :c
               AND status = 'active'
             ORDER BY period DESC LIMIT 1
        """), {"c": code}).one_or_none()

    if pop and pop[0] is not None:
        out["pop_density_km2"] = float(pop[0])
        # NOT NULL DEFAULT FALSE in the schema, but written EXPLICITLY here.
        # The whole point of the column is that somebody had to decide it, and
        # a default that happens to be right still records no decision.
        out["pop_is_census_calibrated"] = False
        conf["pop_density_km2"] = pop[3] or 3
        src["pop_density_km2"] = {
            **ward_note, "year": pop[2], "ward_population": pop[1],
            "rule_D9": "PREFER RELATIVE COMPARISONS. 'More people near A than "
                       "B' is supportable. An absolute count is not, until the "
                       "KNBS census is loaded.",
            "rule_C3": "WorldPop IS NOT CENSUS-CALIBRATED: +16% against the "
                       "2019 census nationally, and +209% in Mandera. This is "
                       "a modelled distribution, not a headcount.",
            "shape": "a WARD density, not a density at the parcel. A large "
                     "rural ward averages a trading centre and empty bush "
                     "into one number."}
        src["pop_is_census_calibrated"] = src["pop_density_km2"]
    else:
        src["pop_density_km2"] = {**ward_note,
                                  "result": "no population row for this ward"}

    if nl and nl[0] is not None:
        out["nightlights_admin_unit"] = f"ward:{code}"
        out["nightlights_radiance_mean"] = float(nl[0])
        if nl[1] is not None:
            out["nightlights_trend_radiance_yr"] = float(nl[1])
        conf["nightlights_radiance_mean"] = nl[3] or 4
        note = {
            **ward_note, "period": nl[2],
            "source": "demographics.nightlights_stats - NOT the raster "
                      "catalogue, where variable='nightlights' names five "
                      "rasters and cannot be sampled unambiguously (E11)",
            "rule_D10": "trend_radiance_yr is a SUM and scales with unit "
                        "area. NEVER rank a large ward against a small one on "
                        "it directly.",
            "rule_D11": "trend_pct_yr is deliberately NULL and is not read "
                        "here. A percentage rate from a near-zero base ranked "
                        "rural electrification above the peri-urban land "
                        "market.",
            "rule_D13": "radiance is NOT linear in economic activity. VIIRS "
                        "compresses bright cores and SNPP's sensor degraded "
                        "across the series. Direction, not level."}
        for c in ("nightlights_radiance_mean", "nightlights_admin_unit",
                  "nightlights_trend_radiance_yr"):
            if c in out:
                src[c] = note
    else:
        # C7: three of 1,425 wards return nothing in ANY year. A NULL here is
        # one of two opposite statements and the report must not merge them.
        src["nightlights_radiance_mean"] = {
            **ward_note,
            "result": "NO NIGHTLIGHTS DATA FOR THIS WARD IN ANY YEAR",
            "rule_C7": "3 of 1,425 wards return nothing in any year. This is "
                       "ABSENCE OF DATA, NOT DARKNESS. Never render it as "
                       "'unlit' - that is a claim about the place, and this "
                       "is a fact about the file."}


def layer_coverage(engine, parcel_id, out, conf, src, srcidx):
    """RULE D4 and D5. Mobile coverage is a SUBLOCATION percentage.

    The polygon containing this parcel is a sublocation, and its coverage_pct
    is the share of THAT AREA that is covered. It is not a statement about the
    parcel and must never be phrased as one.

    Paired with dist_tower_m, which IS point-specific - that pairing is the
    whole of rule D4.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT c.technology, c.operator, c.coverage_pct, c.admin_level,
                   c.admin_name, c.source_date, c.confidence, c.source_id
              FROM land.parcels p
              JOIN connectivity.coverage c
                ON c.status = 'active'
               AND ST_Intersects(c.geom, ST_Centroid(p.geom))
             WHERE p.parcel_id = :pid
        """), {"pid": parcel_id}).all()

    seen = {(str(t).lower(), str(o)): r for t, o, *r in
            ((r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in rows)}
    mapping = {("2g", "all"): "coverage_2g_pct",
               ("4g", "all"): "coverage_4g_pct",
               ("4g", "Safaricom"): "coverage_4g_pct_safaricom",
               ("4g", "Telkom"): "coverage_4g_pct_telkom"}
    wrote = False
    for key, column in mapping.items():
        hit = seen.get(key)
        if not hit or hit[0] is None:
            continue
        pct = float(hit[0])
        if 0.0 < pct < COVERAGE_SLIVER_PCT:
            # Not written. Recorded, with the raw value, so the artefact is
            # discoverable rather than deleted.
            src[column] = {
                "REFUSED": f"raw value {pct!r}% is below "
                           f"{COVERAGE_SLIVER_PCT}% and is a SLIVER ARTEFACT: "
                           f"the parcel centroid clipped a hairline overlap "
                           f"between adjacent coverage polygons. Reporting it "
                           f"would state an operator percentage that was "
                           f"never measured.",
                "technology": key[0], "operator": key[1]}
            print(f"      ! {column} = {pct!r}% - sliver artefact, NOT WRITTEN")
            continue
        out[column] = pct
        conf[column] = hit[4] or 3
        wrote = True

    # THE VINTAGE MUST BELONG TO THE HEADLINE NUMBER, and there is only one
    # column for it. First draft took whichever "all" row came first in the
    # mapping dict, which was 2G - so a parcel showed a 2023 4G percentage
    # stamped with a Jan-2022 date. Wrong, and quietly so.
    #
    # This is rule D12 pressing on the schema: the technologies have
    # DIFFERENT vintages and one column cannot hold them. So the column
    # carries the 4G date (4G is the headline figure a buyer reads), and
    # EVERY per-technology vintage is written into field_sources so nothing
    # is lost to the single-column shape.
    vintages = {f"{t}/{o}": (h[3].isoformat() if h[3] else None)
                for (t, o), h in seen.items()}
    head = seen.get(("4g", "all")) or seen.get(("2g", "all"))
    if head:
        out["coverage_admin_level"] = head[1]
        out["coverage_admin_name"] = head[2]
        out["coverage_vintage"] = head[3]

    # ------------------------------------------------------------------
    # B1, POSSIBLY RECURRING. THE CA HAS DONE THIS BEFORE.
    #
    # Checklist B1 records that the CA published ONE dataset under TWO names -
    # the "3G" and "4G" layers were 99.9% identical to six decimal places, and
    # the 3G copy was deleted. The first run of this layer shows the same
    # signature between two OPERATORS: Safaricom and Telkom 4G returned
    # percentages identical to full float precision on every parcel where both
    # were present (88.30089662557684, 77.84360305862428, 31.93426093324633,
    # 99.99999964919046 - 6 of 6).
    #
    # Two operators running different networks do not agree to 14 digits.
    # Either the CA published one layer twice, or etl_25 resolved both slots
    # to the same service.
    #
    # THIS ENGINE CANNOT SETTLE IT - that needs a comparison across all 7,134
    # rows, not one parcel. What it can do is refuse to present the pair as
    # two independent measurements while the question is open.
    # ------------------------------------------------------------------
    saf, tel = out.get("coverage_4g_pct_safaricom"), \
        out.get("coverage_4g_pct_telkom")
    if saf is not None and tel is not None and saf == tel:
        src["coverage_operator_identity"] = {
            "observation": f"Safaricom and Telkom 4G both returned {saf!r}% - "
                           f"IDENTICAL TO FULL PRECISION",
            "MEASURED_ACROSS_THE_WHOLE_LAYER": "10,357 Safaricom polygons "
                "ST_Equals a Telkom polygon - a 1:1 geometric match on every "
                "row - and the mean absolute difference in coverage_pct "
                "across all 10,357 pairs is BELOW 5e-7 PERCENTAGE POINTS. "
                "Two operators running different networks do not agree to "
                "seven decimal places on ten thousand polygons. This is one "
                "dataset carrying two operator labels.",
            "rule_B1": "SECOND OCCURRENCE. The CA published one dataset under "
                       "two names before - the '3G' and '4G' layers were "
                       "99.9% identical and the duplicate was deleted. This "
                       "is the same fault between two OPERATORS.",
            "THE_REAL_PROBLEM_IS_NOT_THE_DUPLICATE": "it is that we do not "
                "know WHICH operator the measurements describe. Deleting one "
                "copy leaves a column labelled with an operator name that may "
                "not be whose network was measured - exactly B1's original "
                "danger, where keeping the mislabelled layer would have meant "
                "'what we call 4G is really 3G'.",
            "DO_NOT": "DO NOT SHIP PER-OPERATOR 4G AT ALL until the CA "
                      "confirms the attribution. Not one column, not both. "
                      "The combined layer (operator='all') is unaffected and "
                      "is what a report should use.",
            "SETTLED_SESSION_13": "The comparison this note asked for has now "
                "been run (check_01_coverage_operators.py). The two operators "
                "resolve to DIFFERENT source_layer names - 'safaricom_4G_2022' "
                "and 'Telkom_4G' - with IDENTICAL polygon counts (10,357 each) "
                "and IDENTICAL total area (583,962.3 km2 each). So etl_25 did "
                "not collapse two services into one: the CA supplied the same "
                "measurements twice under two operator filenames. B1's fault "
                "recurred at the SOURCE, not in our loader. The attribution "
                "question is therefore the CA's to answer and belongs in the "
                "A2 letter: WHICH operator do the 4G measurements describe?",
            "DO_NOT_JOIN_ON_admin_name": "admin_name IS NOT A KEY. etl_25 "
                                         "records that slcode holds a NAME, "
                                         "and nearly every Kenyan town has a "
                                         "sublocation called TOWNSHIP - so a "
                                         "join on it fans out across counties "
                                         "and measures name collisions, not "
                                         "operator agreement. A first attempt "
                                         "at this check produced 20,963 pairs "
                                         "from ~7,134 rows and an "
                                         "uninterpretable 8.2%. Match on "
                                         "ST_Equals(geom) instead."}
        print("      ! Safaricom and Telkom 4G are IDENTICAL here - "
              "possible B1 recurrence")

    lic = srcidx.get(next((r[7] for r in rows if r[7] is not None), -1), {})
    if wrote:
        note = {
            **lic,
            "rule_D4": "THIS IS AN AREA PERCENTAGE FOR THE SUBLOCATION, NOT A "
                       "PROPERTY OF THE PARCEL. Say 'the area around this "
                       "parcel is about X% covered'. NEVER 'this parcel has "
                       "4G'. Pair it with dist_tower_m, which is the "
                       "point-specific half.",
            "rule_D5": "AIRTEL IS ABSENT BY OMISSION, NOT BY MEASUREMENT. The "
                       "CA published no Airtel percentage. Any per-operator "
                       "display MUST say so - a blank beside Safaricom and "
                       "Telkom reads as 'no Airtel coverage here', which is "
                       "not what the data says.",
            "rule_D12": "vintages span Jan 2022 - Aug 2023 and the "
                        "technologies cover different polygon sets (2G 9,274, "
                        "4G 7,134). Per-parcel lookup is fine; comparing 2G "
                        "against 4G nationally is not.",
            "rule_A2": "THE CA HAS DECLARED NO LICENCE FOR THIS DATA. Loaded "
                       "redistribution_allowed = FALSE. A verbal 'no licence "
                       "required' is on file and is NOT sufficient to sell "
                       "against - checklist A2 stays open until written "
                       "confirmation arrives.",
            "operators_found": sorted({o for _, o in seen}),
            "technologies_found": sorted({t for t, _ in seen}),
            "vintage_per_layer": vintages,
            "vintage_column_note": "coverage_vintage holds the 4G date "
                                   "because 4G is the headline figure. The "
                                   "other layers have DIFFERENT dates and "
                                   "they are all listed above - one column "
                                   "cannot carry them (rule D12)."}
        for c in ("coverage_2g_pct", "coverage_4g_pct",
                  "coverage_4g_pct_safaricom", "coverage_4g_pct_telkom",
                  "coverage_admin_level", "coverage_admin_name",
                  "coverage_vintage"):
            if c in out:
                src[c] = note
    else:
        src["coverage"] = {
            "result": "no coverage polygon contains this parcel's centroid",
            "MEANING": "ABSENCE OF A POLYGON IS NOT ABSENCE OF COVERAGE. The "
                       "CA's layers do not tile the whole country, so this is "
                       "a gap in the map, not a signal blackspot.",
            "rows_intersecting": len(rows)}

    with engine.connect() as conn:
        tw = conn.execute(text("""
            SELECT round(ST_Distance(p.geom::geography, t.geom::geography)),
                   t.operator, t.radio, t.source_id
              FROM land.parcels p, connectivity.towers t
             WHERE p.parcel_id = :pid AND t.status = 'active'
               AND ST_DWithin(p.geom::geography, t.geom::geography, :d)
             ORDER BY p.geom <-> t.geom LIMIT 1
        """), {"pid": parcel_id, "d": SEARCH_M["tower"]}).one_or_none()
    if tw:
        out["dist_tower_m"] = float(tw[0])
        conf["dist_tower_m"] = 2
        src["dist_tower_m"] = {
            "layer": "connectivity.towers", "operator": tw[1],
            "radio": tw[2], **srcidx.get(tw[3] or -1, {}),
            "search_radius_m": SEARCH_M["tower"],
            "rule_A3": "OpenCellID is CC-BY-SA (share-alike) - but this is "
                       "the ONE you can pay your way out of. Unwired Labs "
                       "sell a commercial licence. Checklist A3.",
            "caveat": "OpenCellID positions are CROWD-ESTIMATED FROM HANDSET "
                      "OBSERVATIONS, not surveyed mast locations. Confidence "
                      "2. Read it as 'there is a mast roughly here', never as "
                      "a coordinate."}
        if out["dist_tower_m"] == 0.0:
            src["dist_tower_m"]["INSIDE_THE_PARCEL"] = (
                "0 m IS CONTAINMENT - the estimated mast position falls ON "
                "this parcel. Given confidence 2 and crowd-sourced "
                "positioning, read it as 'a mast is very close', NOT as 'the "
                "mast is on this land'. Do not render it as 0 m.")
    else:
        src["dist_tower_m"] = {
            "layer": "connectivity.towers",
            "result": f"no tower within {SEARCH_M['tower']:.0f} m",
            "NOT_ZERO": "absence in a CROWD-SOURCED dataset is weak evidence. "
                        "It means nobody's handset reported one, not that "
                        "none exists."}


def layer_landmarks(engine, parcel_id, out, conf, src):
    """The landmarks a Kenyan buyer actually orients by, plus their NAMES.

    Loaded by etl_30_osm_landmarks.py into six tables. Every value here is a
    DISTANCE and a NAME computed in PostGIS on geography - no OSM geometry
    crosses the boundary, so this is the same weakest-exposure position as
    layer_roads (checklist A4).

    ------------------------------------------------------------------
    WHY A VILLAGE IS NOT A TOWN CENTRE, AND WHY THAT DECISION IS HERE
    ------------------------------------------------------------------
    admin.places holds 9,323 rows and 8,679 of them are VILLAGES. If
    dist_town_centre_m measured to the nearest place of any kind, almost
    every parcel in Kenya would come back a few hundred metres from a "town
    centre" and the column would carry no information at all - it would
    measure the density of OSM's village tagging, not the buyer's access to
    a town.

    So the town query is restricted to city / town / national_capital, which
    is 436 rows. Suburbs and villages are excluded on purpose. This is the
    same trap as C8 (health facilities stacked on ward centroids): a distance
    is only meaningful if the thing at the other end is the thing the buyer
    had in mind.

    The name comes back with it. Every other distance in this engine is
    anonymous by design - a buyer does not care WHICH clinic is 1.3 km away.
    Landmarks invert that: "18 km from a city" is nearly useless, "18 km from
    Nairobi" is the entire point, because the name is what lets a buyer apply
    everything they already know about the place.

    ------------------------------------------------------------------
    RADII, AND WHY THEY DIFFER
    ------------------------------------------------------------------
    ST_DWithin bounds each search so the index is usable. The bound is not
    cosmetic - past it we return NULL rather than a number, because a
    landmark far enough away has stopped being a landmark:

        town centre     60 km   beyond this you are not near a town
        airport        120 km   a buyer will still drive 2h to JKIA
        major road      50 km   matches layer_roads' own paved-road bound
        railway station 60 km   same reasoning as a town
        market          30 km   a market you cannot reach weekly is not yours
        police          40 km

    ------------------------------------------------------------------
    CONFIDENCE
    ------------------------------------------------------------------
    OSM coverage is honest but uneven, and the catalogue names a better
    primary for two of these (KCAA for airports, county registers for
    markets). Those sit at 2. The rest sit at 3 - the same value layer_roads
    gives a class-based paved-road reading.
    """
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
              -- town / city centre: NOT villages, NOT suburbs. See docstring.
              (SELECT ARRAY[
                        round(ST_Distance(p.geom::geography,
                                          t.geom::geography))::text,
                        t.name, t.place_type]
                 FROM admin.places t
                WHERE t.status = 'active'
                  AND t.place_type IN ('national_capital','city','town')
                  AND ST_DWithin(p.geom::geography, t.geom::geography, 60000)
                ORDER BY p.geom <-> t.geom LIMIT 1),

              (SELECT ARRAY[
                        round(ST_Distance(p.geom::geography,
                                          a.geom::geography))::text, a.name]
                 FROM transport.airports a
                WHERE a.status = 'active'
                  AND ST_DWithin(p.geom::geography, a.geom::geography, 120000)
                ORDER BY p.geom <-> a.geom LIMIT 1),

              -- THE AIRPORT A BUYER CAN ACTUALLY USE. See v1.9.
              -- The subquery above answers "nearest aviation facility of any
              -- kind" and on every OAK GROVE plot that is the GSU police
              -- airstrip - operational, correctly measured, and not somewhere
              -- anyone flies from. `international` is the only class this
              -- database VERIFIES rather than infers, so it is the one shown.
              (SELECT ARRAY[
                        round(ST_Distance(p.geom::geography,
                                          a.geom::geography))::text, a.name]
                 FROM transport.airports a
                WHERE a.status = 'active'
                  AND a.facility_type = 'international'
                  AND ST_DWithin(p.geom::geography, a.geom::geography, 250000)
                ORDER BY p.geom <-> a.geom LIMIT 1),

              -- A NAMED major road. Distinct from dist_paved_road_m, which is
              -- the nearest road of a good class whether or not anyone has
              -- named it. A buyer cannot orient by an unnamed trunk road, so
              -- rows with no name are excluded here and only here.
              (SELECT ARRAY[
                        round(ST_Distance(p.geom::geography,
                                          r.geom::geography))::text, r.name]
                 FROM transport.roads r
                WHERE r.status = 'active'
                  AND r.road_class IN ('motorway','trunk','primary')
                  AND r.name IS NOT NULL AND btrim(r.name) <> ''
                  AND ST_DWithin(p.geom::geography, r.geom::geography, 50000)
                ORDER BY p.geom <-> r.geom LIMIT 1),

              -- Railway STATIONS, from transport.bus_stops. That table holds
              -- every public-transport stop despite its name (see the tail of
              -- 11_schema_update_v1.8.sql). Stations, not the rail LINES:
              -- etl_30 dropped 1,149 of 1,899 rail segments for having no
              -- name, so a distance to the nearest NAMED line would overstate
              -- how far the railway is. A station is what a buyer uses anyway.
              (SELECT ARRAY[
                        round(ST_Distance(p.geom::geography,
                                          s.geom::geography))::text, s.name]
                 FROM transport.bus_stops s
                WHERE s.status = 'active'
                  AND s.stop_type IN ('railway_station','railway_halt')
                  AND ST_DWithin(p.geom::geography, s.geom::geography, 60000)
                ORDER BY p.geom <-> s.geom LIMIT 1),

              (SELECT round(ST_Distance(p.geom::geography, m.geom::geography))
                 FROM social.markets m
                WHERE m.status = 'active'
                  AND ST_DWithin(p.geom::geography, m.geom::geography, 30000)
                ORDER BY p.geom <-> m.geom LIMIT 1),

              (SELECT round(ST_Distance(p.geom::geography, v.geom::geography))
                 FROM social.public_services v
                WHERE v.status = 'active' AND v.service_type = 'police'
                  AND ST_DWithin(p.geom::geography, v.geom::geography, 40000)
                ORDER BY p.geom <-> v.geom LIMIT 1),

              -- Bus and matatu stages only. Railway stations are answered
              -- above; folding them in here would let a station 400 m away
              -- read as a bus stage and tell a buyer they can catch a matatu
              -- where they cannot.
              (SELECT round(ST_Distance(p.geom::geography, b.geom::geography))
                 FROM transport.bus_stops b
                WHERE b.status = 'active'
                  AND b.stop_type IN ('bus_stop','bus_station','taxi_stage')
                  AND ST_DWithin(p.geom::geography, b.geom::geography, 25000)
                ORDER BY p.geom <-> b.geom LIMIT 1)

            FROM land.parcels p WHERE p.parcel_id = :pid
        """), {"pid": parcel_id}).one_or_none()

    if not row:
        return

    OSM = {"source": "OpenStreetMap/Geofabrik", "licence": "ODbL-1.0",
           "note": "A DISTANCE and a NAME. No OSM geometry is published."}

    def pair(arr, dist_col, name_col, confidence, extra=None):
        """Write a name+distance pair, or write NEITHER.

        A distance with no name is not a partial answer for a landmark, it
        is a broken one: "12 km from an airport" tells a buyer nothing they
        can act on, and printing it would imply we know which airport. So
        the pair is atomic - both or nothing.
        """
        if not arr or arr[0] is None or not arr[1]:
            return
        out[dist_col] = float(arr[0])
        out[name_col] = arr[1]
        conf[dist_col] = confidence
        conf[name_col] = confidence
        meta = dict(OSM)
        if extra:
            meta.update(extra)
        src[dist_col] = meta

    town = row[0]
    if town and town[0] is not None and town[1]:
        out["dist_town_centre_m"] = float(town[0])
        out["nearest_town_name"] = town[1]
        out["nearest_town_type"] = town[2]
        conf["dist_town_centre_m"] = 3
        conf["nearest_town_name"] = 3
        src["dist_town_centre_m"] = dict(
            OSM, EXCLUDES="VILLAGES AND SUBURBS ARE NOT TOWN CENTRES. "
                          "admin.places holds 9,323 rows of which 8,679 are "
                          "villages; measuring to the nearest of any kind "
                          "would put every parcel in Kenya a few hundred "
                          "metres from a 'town centre' and measure OSM's "
                          "tagging density rather than a buyer's access to a "
                          "town. Restricted to city/town/national_capital.")

    # confidence 2: KCAA is the catalogue's primary and this is not it. The
    # international/domestic split is inferred from the NAME, because OSM
    # carries no such attribute - so the class is softer than the distance.
    pair(row[1], "dist_airport_m", "nearest_airport_name", 2,
         {"CLASS_IS_INFERRED": "international vs domestic comes from the "
                               "facility NAME, not from any OSM attribute. "
                               "The DISTANCE is sound; the class is a guess "
                               "that happens to be reliable in Kenya."})

    # 250 km, not 120: Kenya has four international airports and a buyer in
    # Marsabit genuinely does drive to Nairobi or Eldoret. A wider radius on a
    # 4-row table costs nothing, and a NULL here would say "no international
    # airport" when what we mean is "we stopped looking".
    pair(row[2], "dist_intl_airport_m", "nearest_intl_airport_name", 3,
         {"VERIFIED_NOT_INFERRED": "international is the ONE aviation class "
                                   "this database does not guess - each of "
                                   "the four is named so by its operator."})

    pair(row[3], "dist_major_road_m", "nearest_major_road_name", 3,
         {"NOT_THE_SAME_AS": "dist_paved_road_m, which takes the nearest "
                             "road of a good class whether or not it is "
                             "named. This one requires a name, so it is "
                             "always the larger of the two."})

    pair(row[4], "dist_railway_station_m", "nearest_railway_station_name", 3,
         {"STATIONS_NOT_LINES": "etl_30 dropped 1,149 of 1,899 rail segments "
                                "for carrying no name, so a distance to the "
                                "nearest NAMED line would overstate the "
                                "railway. Stations are named and are what a "
                                "passenger uses."})

    if row[5] is not None:
        out["dist_market_m"] = float(row[5])
        conf["dist_market_m"] = 2      # county registers are the primary
        src["dist_market_m"] = dict(
            OSM, COVERAGE="OSM's rural market coverage is thin - 2,205 "
                          "nationally. A large distance here is more likely "
                          "a mapping gap than an absence of markets, the "
                          "same failure mode already noted for power lines.")

    if row[6] is not None:
        out["dist_police_m"] = float(row[6])
        conf["dist_police_m"] = 3
        src["dist_police_m"] = dict(OSM)

    if row[7] is not None:
        out["dist_bus_stop_m"] = float(row[7])
        conf["dist_bus_stop_m"] = 3
        src["dist_bus_stop_m"] = dict(
            OSM, EXCLUDES_RAILWAY="Railway stations are answered by "
                                  "dist_railway_station_m. Folding them in "
                                  "here would let a station read as a matatu "
                                  "stage.")


def layer_amenities(engine, parcel_id, out, conf, src):
    """The distances a land buyer actually asks about, in one round trip.

    EXACT MATCHES, NOT ILIKE PATTERNS. These vocabularies are not conventions,
    they are CHECK CONSTRAINTS in the schema, verified against
    _live_schema_snapshot.sql:

      social.education.level       primary, secondary, tvet, university, other
      social.health.facility_type  hospital, health_centre, dispensary,
                                   clinic, pharmacy

    The database already refuses anything else, so an exact match is correct
    and index-friendly. A pattern match would only paper over a future
    vocabulary change that ought to fail loudly.

    THE HONEST FAILURE MODE IS THE SAME FOR ALL OF THEM: absence of a mapped
    feature is not absence of the feature. Every NULL records its radius.
    """
    q = text("""
        SELECT
          (SELECT round(ST_Distance(p.geom::geography, e.geom::geography))
             FROM social.education e
            WHERE e.status = 'active' AND e.level = 'primary'
              AND ST_DWithin(p.geom::geography, e.geom::geography, :school)
            ORDER BY p.geom <-> e.geom LIMIT 1),
          (SELECT round(ST_Distance(p.geom::geography, e.geom::geography))
             FROM social.education e
            WHERE e.status = 'active' AND e.level = 'secondary'
              AND ST_DWithin(p.geom::geography, e.geom::geography, :school)
            ORDER BY p.geom <-> e.geom LIMIT 1),
          (SELECT round(ST_Distance(p.geom::geography, h.geom::geography))
             FROM social.health h
            WHERE h.status = 'active' AND h.facility_type = 'hospital'
              AND ST_DWithin(p.geom::geography, h.geom::geography, :health)
            ORDER BY p.geom <-> h.geom LIMIT 1),
          (SELECT round(ST_Distance(p.geom::geography, h.geom::geography))
             FROM social.health h
            WHERE h.status = 'active'
              AND h.facility_type IN ('clinic','dispensary','health_centre')
              AND ST_DWithin(p.geom::geography, h.geom::geography, :health)
            ORDER BY p.geom <-> h.geom LIMIT 1),
          (SELECT round(ST_Distance(p.geom::geography, w.geom::geography))
             FROM utilities.water_points w
            WHERE w.status = 'active' AND w.is_functional IS NOT FALSE
              AND ST_DWithin(p.geom::geography, w.geom::geography, :water)
            ORDER BY p.geom <-> w.geom LIMIT 1)
        FROM land.parcels p WHERE p.parcel_id = :pid
    """)
    with engine.connect() as conn:
        row = conn.execute(q, {
            "pid": parcel_id, "school": SEARCH_M["school"],
            "health": SEARCH_M["health"], "water": SEARCH_M["water_point"],
        }).one_or_none()
    if row is None:
        return

    C8 = ("HEALTH FACILITIES SIT AT THE WARD CENTROID, NOT AT TRUE GPS. This "
          "distance is accurate to roughly the size of a ward, and only 82% of "
          "facilities matched a ward at all. DO NOT PRINT IT TO THE METRE. "
          "Checklist C8.")
    WATER = ("is_functional IS NOT FALSE - so this includes points whose "
             "functionality is UNKNOWN, not only working ones. A water point "
             "that exists on paper and not in the ground is a known failure "
             "mode of this dataset.")

    fields = [
        ("dist_primary_school_m", 4, "school", "social.education", None),
        ("dist_secondary_school_m", 4, "school", "social.education", None),
        ("dist_hospital_m", 2, "health", "social.health", C8),
        ("dist_clinic_m", 2, "health", "social.health", C8),
        ("dist_water_point_m", 3, "water_point", "utilities.water_points",
         WATER),
    ]
    # C8 MADE VISIBLE PER PARCEL. If the nearest hospital and the nearest
    # clinic are at the SAME distance, they are almost certainly the same
    # point: several facilities collapsed onto one ward centroid. Observed on
    # 6 of 20 parcels in the first run of this layer - identical metres for
    # two different facility types is the signature, and it is not a
    # coincidence worth ignoring in a report that quotes both.
    if (row[2] is not None and row[3] is not None
            and float(row[2]) == float(row[3])):
        src["health_facility_positions"] = {
            "observation": "nearest hospital and nearest clinic returned the "
                           "IDENTICAL distance",
            "meaning": "they are stacked on one ward centroid. Two facility "
                       "types at the same coordinate is a positioning "
                       "artefact, not two facilities at one address.",
            "rule_C8": "Do not present these as two separate distances to a "
                       "buyer. Report one figure for 'health facilities in "
                       "this ward' until true GPS is loaded from KMHFR or "
                       "healthsites.io."}

    for value, (column, cf, radius_key, layer, caveat) in zip(row, fields):
        note = {"layer": layer, "search_radius_m": SEARCH_M[radius_key]}
        if caveat:
            note["caveat"] = caveat
        if value is None:
            note["result"] = (f"nothing found within "
                              f"{SEARCH_M[radius_key]:.0f} m")
            note["NOT_ZERO"] = ("a blank here means NOT MAPPED WITHIN RANGE. "
                                "It must never render as 0 m, and never as "
                                "'none nearby' without stating the radius.")
            src[column] = note
            continue
        out[column] = float(value)
        conf[column] = cf
        if out[column] == 0.0:
            note["INSIDE_THE_PARCEL"] = (
                "0 m IS NOT A SMALL DISTANCE - IT IS CONTAINMENT. The nearest "
                "feature lies ON this parcel. The report must say 'there is "
                "one on this land', never '0 m', which reads as a rounding "
                "artefact or a missing value. For a large parcel this is "
                "ordinary; it is also a materially different fact from "
                "'nearby' and must not be rendered as the extreme of it.")
        src[column] = note


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    dry = "--dry-run" in sys.argv
    only = None
    if "--parcel" in sys.argv:
        only = sys.argv[sys.argv.index("--parcel") + 1]

    load_dotenv(ENV_DIR / ".env")
    pw = os.getenv("DB_PASSWORD")
    if not pw or pw == "put_your_password_here":
        sys.exit(f"ERROR: set DB_PASSWORD in {ENV_DIR / '.env'}")
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{pw}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
        f"/{os.getenv('DB_NAME','land_intelligence_kenya')}")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print(f"Enrichment engine {ENGINE_VERSION}")
    print(f"Connected: {os.getenv('DB_NAME','land_intelligence_kenya')}")

    cat = load_catalogue(engine)
    collisions = cat.pop("__collisions__", {})
    print(f"\nRaster catalogue, {len(cat)} ACTIVE layers:")
    for v in sorted(cat):
        ok = "  " if Path(cat[v]["path"]).exists() else "MISSING FILE"
        yr = cat[v].get("year")
        print(f"   {v:26} conf {cat[v]['confidence']}  "
              f"{('year ' + str(yr)) if yr else '':10}{ok}")
    for needed in ("flood_hazard", "soil_type", "rainfall", "ndvi",
                   "landcover", "builtup"):
        if needed not in cat:
            print(f"   *** '{needed}' NOT in the active catalogue - the "
                  f"layers depending on it will be NULL ***")

    # The column is built_up_pct_1km. If the radius stops being 1 km, the
    # column name is a lie and the report inherits it. Named here rather than
    # trusted to a comment.
    if BUILTUP_RADIUS_M != 1000.0:
        print(f"   *** BUILTUP_RADIUS_M is {BUILTUP_RADIUS_M:.0f} m but the "
              f"column is named built_up_pct_1km. Rename the column or "
              f"restore 1000 m - do not ship the mismatch. ***")

    # DEFECT 3. A variable naming several active rasters cannot be sampled
    # unambiguously, and until now the engine chose one without saying so.
    if collisions:
        print("\n   *** CATALOGUE VARIABLE COLLISIONS - one name, several "
              "active rasters ***")
        for v, n in sorted(collisions.items()):
            print(f"       {v:26} {n} active rows; kept raster_id "
                  f"{cat[v]['raster_id']}"
              f"{', year ' + str(cat[v]['year']) if cat[v].get('year') else ''}")
        print("       'nightlights' is the KNOWN case - etl_26 writes one row "
              "per year - and")
        print("       must be read from demographics.nightlights_stats, not "
              "sampled from here.")
        print("       ANY OTHER NAME IN THIS LIST IS AN UNKNOWN CASE. Settle "
              "it before")
        print("       trusting the field it feeds. Checklist E11.")

    srcidx = sources_index(engine)
    non_comm = sorted({v["source"] for v in srcidx.values()
                       if v.get("redistribution_allowed") is False})
    if non_comm:
        print(f"\n   SOURCES NOT CLEARED FOR REDISTRIBUTION: "
              f"{', '.join(str(s) for s in non_comm)}")
        print(f"   Any field answered from one of these carries the warning "
              f"in field_sources.")

    # ST_Area on the GEOGRAPHY type gives the buffer's true area in m2. Rule
    # D8 needs a real denominator, not pi*r^2 and not a cell count.
    q = """SELECT parcel_id, parcel_ref, ST_AsGeoJSON(geom) AS gj,
                  ST_X(ST_Centroid(geom)) AS lon, ST_Y(ST_Centroid(geom)) AS lat,
                  ST_AsGeoJSON(ST_Buffer(geom::geography, :r)::geometry) AS gjb,
                  ST_AsGeoJSON(ST_Buffer(geom::geography, :w)::geometry) AS gjw,
                  ST_AsGeoJSON(ST_Buffer(geom::geography, :bu)::geometry) AS gjbu,
                  ST_Area(ST_Buffer(geom::geography, :bu)) AS bu_area_m2,
                  test_expectation
             FROM land.parcels WHERE status = 'active'"""
    if only:
        q += " AND parcel_ref = :ref"
    q += " ORDER BY parcel_ref"
    with engine.connect() as conn:
        parcels = conn.execute(
            text(q), {"r": FLOOD_RADIUS_M, "w": WATER_SEARCH_M,
                      "bu": BUILTUP_RADIUS_M,
                      **({"ref": only} if only else {})}).fetchall()
    if not parcels:
        sys.exit("No parcels found. Run 01_create_test_parcels.sql first.")
    print(f"\n{len(parcels)} parcel(s) to enrich\n" + "=" * 74)

    run_id = None
    if not dry:
        with engine.begin() as conn:
            run_id = conn.execute(text("""
                INSERT INTO analytics.enrichment_runs
                    (engine_version, run_status) VALUES (:v, 'running')
                RETURNING run_id"""), {"v": ENGINE_VERSION}).scalar()
        print(f"Enrichment run opened: {run_id}\n")

    done = 0
    try:
        for (pid, ref, gj, lon, lat, gjb, gjw, gjbu, bu_area,
             expect) in parcels:
            print(f"{ref}")
            geom, geom_buf = json.loads(gj), json.loads(gjb)
            geom_water = json.loads(gjw)
            geom_builtup = json.loads(gjbu)
            out, conf, src = {}, {}, {}

            layer_roads(engine, pid, out, conf, src)
            layer_flood(cat, geom, geom_buf, out, conf, src)
            layer_permanent_water(cat, geom_water, (lon, lat), out, conf, src)
            vpct, cpct = layer_soils(cat, geom, out, conf, src)
            layer_black_cotton(cat, geom, vpct, cpct, out, conf, src)
            layer_rainfall(cat, geom, out, conf, src)
            layer_ndvi(cat, geom, out, conf, src)
            layer_landcover(cat, geom, out, conf, src)
            layer_builtup(cat, geom_builtup, bu_area, out, conf, src)
            layer_environment(engine, pid, out, conf, src, srcidx)
            layer_amenities(engine, pid, out, conf, src)
            layer_landmarks(engine, pid, out, conf, src)
            layer_admin_stats(engine, pid, out, conf, src)
            layer_coverage(engine, pid, out, conf, src, srcidx)

            # Last, so that any layer which DID answer keeps its own entry.
            stamp_not_sourced(out, src)

            for k in sorted(out):
                if k.endswith("_breakdown") or k.endswith("_composition"):
                    print(f"   {k:28} {json.loads(out[k])}")
                else:
                    print(f"   {k:28} {out[k]}")
            if expect:
                print(f"   {'EXPECTED':28} {expect[:120]}...")

            if not dry:
                out["field_confidence"] = json.dumps(conf)
                out["field_sources"] = json.dumps(src)
                out["parcel_id"] = pid
                out["run_id"] = run_id
                out["engine_version"] = ENGINE_VERSION
                cols = ", ".join(out)
                vals = ", ".join(f":{c}" for c in out)
                with engine.begin() as conn:
                    # Supersede, never delete - the project's rule everywhere.
                    conn.execute(text("""
                        UPDATE analytics.parcel_intelligence
                        SET status = 'superseded'
                        WHERE parcel_id = :p AND status = 'active'"""),
                        {"p": pid})
                    nxt = conn.execute(text("""
                        SELECT coalesce(max(version), 0) + 1
                        FROM analytics.parcel_intelligence
                        WHERE parcel_id = :p"""), {"p": pid}).scalar()
                    conn.execute(text(
                        f"INSERT INTO analytics.parcel_intelligence "
                        f"({cols}, version) VALUES ({vals}, :__v)"),
                        {**out, "__v": nxt})
            done += 1
            print()

        if not dry:
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE analytics.enrichment_runs
                    SET finished_at = now(), run_status = 'success',
                        parcels_processed = :n
                    WHERE run_id = :id"""), {"n": done, "id": run_id})
            print("=" * 74)
            print(f"DONE. {done} parcel(s) enriched. Run {run_id} logged.")
        else:
            print("=" * 74)
            print(f"DRY RUN. {done} parcel(s) sampled, nothing written.")

        print("\nNOW CHECK IT AGAINST THE EXPECTATIONS, which were written")
        print("before this engine existed:")
        print("  python verify_01_enrichment.py")

    except BaseException as exc:
        # BaseException, not Exception: SystemExit and KeyboardInterrupt both
        # inherit from it, and an `except Exception` handler leaves the run row
        # at 'running' forever. That bug left 12 orphan rows across a month.
        if run_id is not None:
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE analytics.enrichment_runs
                    SET finished_at = now(), run_status = 'failed'
                    WHERE run_id = :id"""), {"id": run_id})
        raise


if __name__ == "__main__":
    main()
