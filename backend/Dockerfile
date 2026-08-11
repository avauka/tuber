# TUBER API — Railway-Deploy (ADR 0001, Backlog AP9).
FROM python:3.12-slim

# uv aus dem offiziellen Image; kein pip-Bootstrap, keine Netzwerkinstallation
# des Installers selbst.
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /uvx /bin/

# Beides fehlt im Basis-Image und beides braucht der Backup-Job (AP15):
#   postgresql-client -> pg_dump -Fc (ADR 0004)
#   gnupg             -> symmetrische Verschluesselung des Dumps
# Bewusst das Standard-gpg statt einer Python-Bibliothek: Ein Backup muss in
# Jahren noch lesbar sein, notfalls ohne diesen Code. Eine .gpg-Datei
# entschluesselt jede beliebige gpg-Installation; ein selbstgebautes Format
# waere auf genau dieses Repository angewiesen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client gnupg \
    && rm -rf /var/lib/apt/lists/*

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

# Non-root. Die Anwendung schreibt nichts ins Dateisystem; /app und das venv
# gehoeren weiterhin root und bleiben damit fuer den Dienst unveraenderlich.
RUN useradd --create-home --uid 10001 tuber
USER tuber

# Railway setzt PORT selbst; 8000 ist nur der lokale Standard.
EXPOSE 8000

CMD ["./entrypoint.sh"]
