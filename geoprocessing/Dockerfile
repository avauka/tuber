# Werkzeugkasten der Eignungskarten-Pipeline (ADR 0008, AP17a).
#
# Läuft ausschliesslich lokal auf dem Rechner des Nutzers, nie auf dem
# Server: Auf dem Volume landet nur die fertige Kachelpyramide (ADR 0008 §8).
#
# GDAL im Container, weil eine native GDAL-Installation unter Windows
# Bastelei ist. Der Nutzer braucht Docker und sonst nichts.
#
# Bauen (aus der Repo-Wurzel oder aus geoprocessing/):
#     docker build -t tuber-geo geoprocessing/
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.2

# go-pmtiles: schreibt aus dem MBTiles, das GDAL erzeugt, das PMTiles-Archiv.
# Dieselbe Version wie im Backend-Image (AP10a) — die Archive sollen von
# derselben Implementierung stammen, die sie später ausliefert.
ARG PMTILES_VERSION=1.31.2
# sha256 des Assets go-pmtiles_1.31.2_Linux_x86_64.tar.gz, am 2026-08-12
# selbst aus dem Release berechnet (das Release bringt keine checksums.txt
# mit). Identisch zu backend/Dockerfile.
ARG PMTILES_SHA256=3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3-pytest \
    && curl -fsSL -o /tmp/pmtiles.tar.gz \
        "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_Linux_x86_64.tar.gz" \
    && echo "${PMTILES_SHA256}  /tmp/pmtiles.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/pmtiles.tar.gz -C /usr/local/bin pmtiles \
    && chmod +x /usr/local/bin/pmtiles \
    && rm /tmp/pmtiles.tar.gz \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

# Damit Fehler im Log stehen, bevor der Container endet.
ENV PYTHONUNBUFFERED=1

WORKDIR /geo
COPY . /geo

# Kein ENTRYPOINT: Die Aufrufe stehen in geoprocessing/README.md und nennen
# das Skript ausdrücklich — welche Stufe läuft, soll man am Befehl sehen.
