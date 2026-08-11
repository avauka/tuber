# TUBER API — Railway-Deploy (ADR 0001, Backlog AP9).
FROM python:3.12-slim

# uv aus dem offiziellen Image; kein pip-Bootstrap, keine Netzwerkinstallation
# des Installers selbst.
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /uvx /bin/

# Beides fehlt im Basis-Image und beides braucht der Backup-Job (AP15):
#   postgresql-client-16 -> pg_dump -Fc (ADR 0004)
#   gnupg                -> symmetrische Verschluesselung des Dumps
# Bewusst das Standard-gpg statt einer Python-Bibliothek: Ein Backup muss in
# Jahren noch lesbar sein, notfalls ohne diesen Code. Eine .gpg-Datei
# entschluesselt jede beliebige gpg-Installation; ein selbstgebautes Format
# waere auf genau dieses Repository angewiesen.
#
# HAUPTVERSION 16, festgenagelt (AP15.2): Sie muss zur Produktions-DB passen.
# pg_dump 17 schreibt Archivformat 1.16, das pg_restore 16 mit "unsupported
# version in file header" ablehnt — das Backup waere unbrauchbar, ohne dass
# es beim Erstellen auffaellt. Debian trixie liefert nur Client 17, deshalb
# das PGDG-Repo. Das generische "postgresql-client" waere beim naechsten
# Basis-Image stillschweigend weitergewandert; genau so ist der Fehler
# entstanden.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg]" \
        "http://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

# pg_dump aus dem versionierten Paket liegt nicht im PATH.
ENV PATH="/usr/lib/postgresql/16/bin:$PATH"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Erst nur die Abhaengigkeiten aufloesen: Diese Schicht bleibt im Cache,
# solange sich pyproject.toml und uv.lock nicht aendern.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Dann der Code. --no-editable: das Paket wird echt installiert, nicht als
# Verweis auf /app - der Container soll nicht davon abhaengen, dass das
# Quellverzeichnis zur Laufzeit unveraendert daliegt.
COPY . .
RUN uv sync --locked --no-dev --no-editable \
    && chmod +x entrypoint.sh

# Non-root. /app und das venv gehoeren weiterhin root und bleiben damit fuer
# den Dienst unveraenderlich.
RUN useradd --create-home --uid 10001 tuber

# Einziger beschreibbarer Ort: die Backup-Ablage auf dem Volume (AP15.1).
# Achtung: Haengt Railway das Volume nach /data, verdeckt es dieses
# Verzeichnis samt Eigentuemer. Reicht das nicht, ist RAILWAY_RUN_UID=0 der
# dokumentierte Notausgang — siehe infra/railway/README.md.
ENV BACKUP_DIR=/data/backups
RUN mkdir -p /data/backups && chown -R tuber:tuber /data

USER tuber

# Railway setzt PORT selbst; 8000 ist nur der lokale Standard.
EXPOSE 8000

CMD ["./entrypoint.sh"]
