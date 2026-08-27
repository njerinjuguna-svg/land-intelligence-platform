# Sample parcels — drop client files here

## What goes in this folder

Real parcel geometry, for testing the enrichment engine against data that is
messier than synthetic squares.

**Accepted formats:** shapefile (bring ALL sidecars — `.shp`, `.dbf`, `.shx`,
and especially `.prj`), GeoJSON, KML/KMZ, DXF, GeoPackage, or CSV/Excel with
coordinates.

**The `.prj` matters.** Without it the coordinate system has to be guessed, and
this project has already lost two runs to assumed CRS — etl_17 (iSDA served as
LOCAL_CS, not lon/lat) and etl_22 (SoilGrids assumed Homolosine, actually
EPSG:4326). Both were settled in seconds by asking the file.

## Before copying anything in

**1. Confirm you are permitted to use it.** These are client parcels from a
previous engagement. Internal testing may or may not be covered by the terms
you worked under. Worth being certain — this project has been careful about
every other licence.

**2. Strip personal data.** Parcel attribute tables commonly carry owner names,
national ID numbers, phone numbers and purchase prices. **Kenya's Data
Protection Act 2019 applies to all of that**, and none of it is needed: the
engine wants geometry and a reference code.

Delete those columns before copying if it is easy. If not, say so and the
loader will read geometry and reference only, ignoring the rest.

**3. This folder is test input, not a data store.** Remove the files once the
engine is validated. Do not let client data become a permanent fixture of the
repository.

## What happens next

Once a file is here, it gets inspected before anything is loaded: geometry
validity, CRS, parcel count, attribute names, and whether the polygons look
like real survey boundaries or approximations. Only then is it loaded to
`land.parcels` under the `geocode-test` company, alongside the synthetic
landmark parcels.

The synthetic parcels test whether the engine gets KNOWN answers right. Real
client parcels test whether it survives contact with real geometry — slivers,
self-intersections, multipart plots, holes, and whatever else a surveyor's
export contains. **Both are needed; neither substitutes for the other.**
