# TUBER

Private Webapp zur Habitatkartierung und Felddokumentation von Trüffelvorkommen
(Raum Aachen/Eifel/Ardennen). Single-User, wissenschaftlich-dokumentarisch,
keine Entnahme. Verbindliches Spec: `docs/spec.md`. Arbeitskonventionen und
Invarianten: `CLAUDE.md`. Infrastruktur-Entscheidungen: `docs/decisions/`.

## Struktur

- `backend/` — FastAPI + SQLAlchemy/GeoAlchemy2 + Alembic, pytest
- `frontend/` — React + Vite + TS + MapLibre; `src/feld` und `src/planer` sind
  die zwei hart getrennten UI-Modi
- `geoprocessing/` — Offline-Pipelines für die Eignungskarte (Phase 2, eigenes Env)
- `infra/` — Railway-Konfiguration, Backup-Skripte
- `docs/` — Spec, ADRs

## Lokale Entwicklung

    docker compose up -d db        # PostGIS 16/3.4, Host-Port 5433
    cd backend && uv sync && uv run alembic upgrade head && uv run pytest
    cd frontend && pnpm install && pnpm dev

Die Dev-DB hängt auf **Host-Port 5433**, nicht 5432: Port 5432 ist lokal von
einer nativen PostgreSQL-Installation belegt. Im Container bleibt es 5432.

`pnpm dev` schiebt `/api` an `127.0.0.1:8000` weiter; dort muss also das
Backend laufen (aus `backend/`: `uv run uvicorn app.main:app --port 8000`).

Für die Karte braucht es lokal ein Basiskarten-Archiv auf der Platte:

    cd backend && BASEMAP_DIR=./data BASEMAP_BUILD_DATE=<JJJJMMTT> \
        uv run python -m app.jobs.basemap_extract

Das aktuelle Build-Datum steht auf <https://maps.protomaps.com/builds>. Das
Archiv sind rund 208 MB und liegt wie das ganze `backend/data/` ausserhalb der
Versionsverwaltung. Details: `infra/railway/basemap-extract.md`.

## Image bauen

Das Image enthält Backend **und** gebautes Frontend; der Build-Kontext ist
deshalb die Repo-Wurzel und nicht `backend/`:

    docker build -f backend/Dockerfile -t tuber .
