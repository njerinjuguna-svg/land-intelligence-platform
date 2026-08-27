# Master Data Catalogue

Geocode Spatial Solutions Ltd — Land Intelligence Platform

Two files, matching the metadata schema in the database:

**sources.csv** — every organisation we take data from. One row per source.
Loads into `metadata.sources`. Tier meaning: 1 Kenya government, 2 international
authoritative, 3 research institutes, 4 community data, 5 Geocode generated.

**datasets.csv** — every dataset the platform uses (74 datasets, 13 categories).
Loads into `metadata.datasets`. Key columns:

- code: dataset identifier, matches target schema naming
- buyer_question: the buyer question this dataset answers. If a dataset answers
  no question, it does not belong in the catalogue.
- storage: postgis (vectors and zonal statistics) or object_storage (rasters as
  Cloud Optimized GeoTIFFs, catalogued in metadata.raster_catalog)
- target_table: where it lands in land_intelligence_kenya
- priority: P1 build first (the ~20 datasets the MVP needs), P2 second wave,
  P3 later
- redistribution: yes / share-alike / caution / no / internal. Anything not
  "yes" or "internal" needs a licensing decision before commercial launch.
- etl_status: planned, sourced, ingested, validated, published, deprecated.
  Update this column as pipelines are built.

Licensing flags to resolve before launch:
1. OpenStreetMap (ODbL) — share-alike terms on derived databases
2. OpenCellID (CC-BY-SA) — share-alike terms
3. Communications Authority coverage maps — get written permission
4. WDPA protected areas — non-commercial only; use KWS as primary
5. Kenya Power network data — formal request required
