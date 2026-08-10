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
