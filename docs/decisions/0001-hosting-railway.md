# ADR 0001 — Hosting: Railway

**Datum:** 2026-08-10 · **Status:** angenommen

## Entscheidung
Deployment auf Railway: FastAPI-Service (Docker), PostGIS via Template
(postgis/postgis, PG16/3.4-kompatibles Image wählen), persistente Volumes für
DB und Media, Railway-Cron für den Wetter-Ingest. TLS/HTTPS durch Railway.

## Kontext
Ein Nutzer, kleines Budget, Priorität: minimaler Betriebsaufwand. Alternativen
waren Hetzner-VPS (+Caddy) und Home-Server (+Tailscale). VPS wäre etwas
günstiger, verlangt aber OS-Pflege; Home-Server kollidiert mit Feld-Sync
(VPN-Zwang auf dem iPhone).

## Konsequenzen
- Kein Server-Patching, aber Anbieterbindung; Fundort-Daten liegen bei einem
  US-Anbieter (bewusst akzeptiert).
- Railway-Volume-Backups (Snapshots/PITR) schützen nur innerhalb des Projekts:
  Volume löschen = Backups weg, Restore nur ins selbe Projekt. Deshalb
  zusätzlich logische Dumps off-platform (ADR 0004).
- Kosten grob 5–15 €/Monat je nach Volume-Größe.

## Ist-Zustand (AP9b, verifiziert am 2026-08-10)

| | |
|---|---|
| Domain | `https://tuber-production-9a4c.up.railway.app` |
| Edge-Region | `ams1` (Amsterdam), aus `x-railway-edge` |
| Service `PostGIS` | PostGIS-Template, PostgreSQL 16 + PostGIS 3.4 |
| Service `tuber` | API, Docker-Build aus `backend/Dockerfile`, läuft |
| Service `wetter-cron` | angelegt, **Schedule noch nicht eingerichtet** |
| Media-/Basiskarten-Volume | noch nicht nötig (ab AP10/AP13) |
| Volume-Backups | **nicht aktiv** — nur im Pro-Plan verfügbar |

Von aussen verifiziert: `/api/health` antwortet `200`, HTTP wird per `301` auf
HTTPS umgeleitet, alle `/api/`-Routen antworten ohne Cookie mit `401`, ein
Login-Fehlversuch ergibt `401` (nicht `500`).

Dass das Schema in der Produktionsdatenbank steht, folgt aus dem Start selbst:
`entrypoint.sh` führt `alembic upgrade head` mit `set -e` vor uvicorn aus. Ein
antwortender Healthcheck heisst also, dass die Migration gegen die
Produktions-DB durchgelaufen ist.

### Folge für das Backup (ADR 0004)

Volume-Backups bietet Railway nur im Pro-Plan an (verifiziert 2026-08-10).
Punkt 1 von ADR 0004 ist damit auf dem aktuellen Plan nicht umsetzbar. Die
dortige Feststellung bleibt trotzdem richtig — sie wird nur nicht durch
Volume-Backups aufgelöst, sondern durch **AP15** (wöchentlicher `pg_dump`
off-platform). Bis AP15 steht, existiert kein Backup. Das ist vertretbar,
solange keine Felddaten erfasst sind, und wird es ab dem ersten echten Fund
nicht mehr.

### Härtung (AP9c)

`/docs`, `/redoc` und `/openapi.json` sind standardmässig abgeschaltet. Mit
`DOCS_ENABLED=true` erscheinen sie unter `/api/docs` und
`/api/openapi.json` — dort greift die Auth-Dependency. Alle Antworten tragen
HSTS, `X-Content-Type-Options` und `X-Frame-Options`.
