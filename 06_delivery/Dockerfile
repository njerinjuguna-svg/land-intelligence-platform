# =========================================================================
# GEOCODE LANDIQ EMBED API
#
# This image serves the WIDGET ONLY - the API a client's website calls, plus
# v1.js. It deliberately does NOT contain the ETL pipelines, the raster
# catalogue, the enrichment engine or the scorer.
#
# WHY THE SPLIT MATTERS
#   Those run occasionally, need tens of gigabytes of source rasters, and
#   read and write freely across the database. The widget runs constantly,
#   is reachable from the public internet, and needs SELECT on a handful of
#   tables. Putting them in one image would mean the internet-facing
#   container also carries the credentials and the code to rewrite every
#   parcel in the country.
#
#   Enrichment stays where it is today - a machine you control, running
#   against the same database. Only this image is exposed.
# =========================================================================
FROM python:3.12-slim

# psycopg2-binary needs no build tools, but libpq is still worth having for
# pg_isready in the healthcheck path and for clearer error messages.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements first, so a code change does not reinstall the world.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Only what the widget needs. report_content.py carries the geometry firewall
# and every sentence the product says; api_01_embed.py is the server; v1.js is
# the file the client's two lines point at.
COPY report_content.py api_01_embed.py v1.js ./

# NOT root. If the widget is ever exploited, it should not own the container.
RUN useradd --create-home --shell /usr/sbin/nologin geocode \
 && chown -R geocode:geocode /app
USER geocode

EXPOSE 8000

# The healthcheck hits /v1/health, which touches the DATABASE. A container
# that is running but cannot reach Postgres is not healthy, and the whole
# point of a healthcheck is to say so before a buyer sees an empty panel.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/v1/health || exit 1

# --proxy-headers so client IPs survive the reverse proxy: logs.api_logs
# stores them, and without this every request is logged from the proxy.
# --forwarded-allow-ips is set to the proxy only; trusting * would let any
# caller forge the IP we bill and rate-limit against.
CMD ["uvicorn", "api_01_embed:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "172.16.0.0/12", \
     "--workers", "2"]
