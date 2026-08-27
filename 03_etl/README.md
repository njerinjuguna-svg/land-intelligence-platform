# ETL Pipeline — Land Intelligence Platform

Scripts that download, clean and load datasets into land_intelligence_kenya.
Run them on this machine, from this folder, with the virtual environment active.

## One-time setup

Open PowerShell and run these commands one at a time:

    cd "E:\Land Intelligence Platform Geocode\Land Intelligence Platform\03_etl"
    py -3.12 -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env
    notepad .env        <- set your real database password, save, close

If PowerShell refuses to activate the venv ("running scripts is disabled"), run:

    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

answer Y, then try the Activate line again.

Every future session starts with just:

    cd "E:\Land Intelligence Platform Geocode\Land Intelligence Platform\03_etl"
    .\venv\Scripts\Activate.ps1

## Script 01 — administrative boundaries

Data to download first (into 03_etl\data\raw\, subfolders fine, unzip them):

1. Counties and subcounties: https://data.humdata.org/dataset/cod-ab-ken
   Download the shapefiles zip (contains adm0/adm1/adm2 layers). Unzip.
2. Wards: https://data.humdata.org/dataset/kenya-wards
   Download the wards shapefile zip. Unzip.

Then:

    python etl_01_admin_boundaries.py

The script finds the .shp files by name, matches county names to the codes
seeded in the database, repairs geometry, and loads everything with source
and run logging. If it stops with unmatched county names, add them to the
ALIASES dictionary at the top of the script and rerun.

## Verify after running

In pgAdmin:

    SELECT name, ST_IsValid(geom),
           round((ST_Area(geom::geography)/1000000)::numeric, 0) AS area_km2
    FROM admin.counties WHERE is_pilot ORDER BY name;

    SELECT county_code, count(*) FROM admin.wards GROUP BY county_code ORDER BY 1;

    SELECT * FROM metadata.etl_runs ORDER BY run_id DESC LIMIT 5;

Area check: Nakuru should be about 7,500 km2, Kiambu about 2,500 km2.
If areas look right, the geometry is genuinely in the right place on Earth.

## Coming next

- etl_02_roads.py — OSM road network for the 20 pilot counties (Geofabrik)
- etl_03_social.py — schools (MoE) and health facilities (KMHFL)
- etl_04_water.py — rivers (WRA/HydroSHEDS) and water points (WPDx)
