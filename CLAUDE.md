# TUBER — Trüffel-Habitatkartierung & Felddokumentation

Private Single-User-Webapp zur wissenschaftlichen Kartierung und Dokumentation
von Trüffelhabitaten und -funden (Raum Aachen/Eifel/Ardennen). Kein Entnahme-Tool.
Verbindliche Referenz: `docs/spec.md` (Spec v1.0). Bei Widerspruch gilt das Spec.

**Strikt getrennt von Pilzobs/OMYKO.** Kein geteilter Code, keine geteilte DB,
kein Auth-Sharing, kein Datenaustausch. Taucht Pilzobs-Kontext auf: Nutzer darauf
hinweisen, nicht übernehmen.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x + GeoAlchemy2, Alembic — `backend/`
- **DB:** PostgreSQL 16 + PostGIS 3.4
- **Frontend:** React 18 + Vite, TypeScript, MapLibre GL JS — `frontend/`
- **Offline:** Service Worker (Workbox), IndexedDB (Sync-Queue), PMTiles (Karten)
- **Geo-Preprocessing (offline, nie zur Laufzeit):** GDAL/rasterio, geopandas — `geoprocessing/`
- **Deploy:** Railway (API-Service + PostGIS-Template + Volumes + Cron). Caddy entfällt, TLS macht Railway.
- **Zielgerät:** iPhone/Safari als PWA. Desktop nur Planer-Modus.

## Tooling & Kommandos

- Backend: `uv` für Dependencies, `ruff` (Lint + Format), `mypy`, `pytest`.
  - Tests: `cd backend && uv run pytest`
  - Lint: `uv run ruff check . && uv run ruff format --check .`
- Frontend: `pnpm`, `vitest`, `eslint`.
- Lokale DB: `docker compose up db` (Root-Compose), Image `postgis/postgis:16-3.4`.
- Migrationen: `cd backend && uv run alembic upgrade head` / `alembic revision --autogenerate`.

## Domänen-Invarianten (verletzt = Bug, keine Diskussion)

1. Ein Fund ohne GPS-Genauigkeitsangabe wird nie gespeichert.
2. Ist iOS "Genauer Standort" aus (Genauigkeit im Kilometerbereich), wird das
   Loggen blockiert, nicht gespeichert.
3. Alle Schreiboperationen aus dem Feld sind idempotent über eine client-seitig
   erzeugte `client_uuid`.
4. Das Gerät ist kein sicherer Speicher. Ein Datensatz gilt erst als sicher, wenn
   er servergesynct ist. Ungesyncte Einträge bleiben im UI sichtbar markiert.
5. Coverage-Polygone entstehen ausschließlich aus bereinigten Tracks
   (Genauigkeitsfilter + Plausibilitätsprüfung). Rohtracks bleiben unverändert erhalten.
6. Artbestimmung ist nie Pflichtfeld. Feld-Default: `tuber_spec` + `id_pending = true`.
7. Saisonlogik hängt am Ökotyp/Zielfenster, nie an der Taxonomie.
   *T. aestivum* und *T. uncinatum* sind eine Art (`phenotype` trennt die Ökotypen).
8. Indikatorarten ohne Speisewert (`t_rufum`, `t_excavatum`) werden nie
   standardmäßig ausgefiltert.
9. Die App zeigt Habitat-Eignung, nie "Fundwahrscheinlichkeit" — in Code,
   UI-Texten und Variablennamen (`suitability`, nicht `probability`).
10. Jeder Eignungsscore bleibt in Einzelfaktoren aufschlüsselbar. Keine Blackbox-Zahl.
11. Geometrien in EPSG:4326 gespeichert; Berechnungen über `geography` oder EPSG:25832.
12. Wallonische CNSW-Daten nur client-seitig laden — nie proxyen, nie cachen (Lizenz).

## Konventionen

- Alle Timestamps in der DB `TIMESTAMPTZ`, UTC. Lokalzeit ist reine Darstellung.
- Enums: DB-Enums mit deutschen Werten exakt wie im Spec (Abschnitt 4/4a).
- Kalibrierbare Konstanten (Buffer 8 m, Genauigkeitsschwelle 25 m,
  Geschwindigkeitsfilter 3 m/s, Cluster-Radius 15 m, Revisit-Offset) leben als
  benannte Werte in `backend/app/core/params.py` mit Kommentar, nie inline.
- API-Fehler strukturiert (RFC 7807-artig); der Offline-Sync unterscheidet
  retryable / nicht-retryable.
- Kein LLM-Aufruf zur Laufzeit (Ausnahme: optionale Sprachnotiz-Strukturierung,
  Phase 1, hinter Feature-Flag).
- Keine Community-/Sharing-/Cloud-Aggregations-Features. Keine Entnahme-Felder.
  Keine automatische Artbestimmung per Foto.
- `alembic check` ist KEIN Gate: Das PostGIS-Image bringt Tiger-Geocoder-Tabellen
  mit, und die GIST-Indizes sind bewusst migrationsverwaltet — Autogenerate-Diffs
  sind daher erwartbar. Gate ist der Upgrade/Downgrade-Roundtrip.

## Test-First bei kritischen Pfaden

Für diese Bereiche existieren Tests, **bevor** Implementierungscode entsteht:

- GPX-Parsing und -Bereinigung (inkl. fehlendes Genauigkeitsfeld, hdop-Fallback)
- Offline-Sync und Idempotenz (`client_uuid`-Wiederholungen erzeugen keine Duplikate)
- Coverage-Berechnung (Buffer, Union, Confidence-Ableitung)
- Bedingungs-Scoring (vier Teilkomponenten einzeln + Gesamtscore)

Fixtures liegen in `backend/tests/fixtures/`. Tests dürfen bei fehlender
Implementierung fehlschlagen (rot ist der Startzustand). Tests dürfen nie
gelöscht oder inhaltlich aufgeweicht werden (Assertions, Erwartungswerte,
Fixture-Semantik), um grün zu werden. Rein kosmetische Lint-/Format-Korrekturen
an Testdateien sind in eigenen Pflege-Commits erlaubt. Neue Tests zu ergänzen
ist ausdrücklich erwünscht.

## Phasendisziplin

Phase 1 (Logger, Bedingungs-Engine, Offline, GPX-Import) wird abgeschlossen,
bevor Phase-2-Arbeit (Eignungskarte, Ingest-Pipeline) beginnt. Bei Anfragen, die
Phase 2/3 vorziehen: daran erinnern, nicht stillschweigend bauen.

## Getroffene Infrastruktur-Entscheidungen

Details und Begründungen: `docs/decisions/`. Kurzfassung:

| Thema | Entscheidung |
|---|---|
| Hosting | Railway (API + PostGIS-Template + Volumes + Cron) |
| Basiskarte | Protomaps-PMTiles-Regional-Extract, selbst gehostet als statische Datei |
| Offline-Tiles | Pro Area serverseitiges `pmtiles extract`; Client speichert lokal (Spike offen) |
| Media | Railway-Volume am API-Service, Pfade in `media.storage_path` |
| Auth | Single-User-Session: Argon2-Passwort, langlebiges httpOnly-Cookie, Login-Rate-Limit |
| Backup | Railway Volume-Backups ab Tag 1; wöchentlicher pg_dump off-platform (Arbeitspaket, Ziel offen) |
| Push | Vorbereitet (VAPID-Keys, Endpunkt-Stubs), aktiviert später |
| Wetter-Ingest | Railway-Cron ruft `backend/app/jobs/`-Skripte, täglich |
| GPX-Logger | Offen — Feldtest-Arbeitspaket; Kriterium 1: schreibt die App Genauigkeit/hdop ins GPX? |

## Attribution (sichtbar in der App, Pflicht)

OSM contributors (ODbL), Protomaps, Open-Meteo (CC BY 4.0), Geologischer Dienst
NRW (dl-de/by-2-0, mit Abrufdatum), Thünen-Institut, DWD CDC, Geobasis NRW,
SPW/CNSW (nur client-seitig). Vollständige Liste: Spec Abschnitt 15.
