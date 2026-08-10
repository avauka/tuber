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
| DB | PostGIS-Template, PostgreSQL 16 + PostGIS 3.4 |
| API-Service | Docker-Build aus `backend/Dockerfile`, läuft |
| Wetter-Cron | **noch nicht eingerichtet** |
| Media-/Basiskarten-Volume | noch nicht nötig (ab AP10/AP13) |

Von aussen verifiziert: `/api/health` antwortet `200`, HTTP wird per `301` auf
HTTPS umgeleitet, alle `/api/`-Routen antworten ohne Cookie mit `401`, ein
Login-Fehlversuch ergibt `401` (nicht `500`).

Dass das Schema in der Produktionsdatenbank steht, folgt aus dem Start selbst:
`entrypoint.sh` führt `alembic upgrade head` mit `set -e` vor uvicorn aus. Ein
antwortender Healthcheck heisst also, dass die Migration gegen die
Produktions-DB durchgelaufen ist.

**Offen und bewusst nicht per Fernprüfung feststellbar:** die exakten
Servicenamen im Railway-Projekt und ob die Volume-Backups aktiviert sind
(ADR 0004). Beides ist im Dashboard zu bestätigen.
