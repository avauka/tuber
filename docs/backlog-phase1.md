# Phase-1-Backlog — Arbeitspakete

Jedes Paket ist einzeln an Claude Code übergebbar. Regeln für alle Pakete:
Tests dürfen ergänzt, nie gelöscht oder aufgeweicht werden. `uv run pytest`
muss am Ende des Pakets den genannten Zielzustand zeigen. Ein Commit pro
Paket, Präfix `APx:`. Bei Unklarheiten: anhalten und fragen, nicht raten.

**Lint-Gate für jedes Paket:** `uv run ruff check .` **und**
`uv run ruff format --check .` sind beide repo-weit leer. Nicht nur die neu
geschriebene Datei.

Reihenfolge-Logik: Backend-Kern zuerst (AP1–AP7), dann Auth (AP8) und ein
**früher Railway-Deploy (AP9)** — bewusst vor dem Feld-UI, weil
`getCurrentPosition` einen Secure Context verlangt und das iPhone die App
daher über HTTPS erreichen muss, um den Feldmodus real zu testen.

---

## AP1 — GPX-Service grün
`parse_gpx` und `clean_track` implementieren, bis alle 8 Tests in
`tests/unit/test_gpx_parsing.py` grün sind. Nur Standardbibliothek
(`xml.etree`) oder `gpxpy` (dann als Dependency ergänzen und begründen).
**Fertig:** Unit-GPX grün, Rest unverändert rot.

## AP2 — Bedingungs-Scoring grün
Alle Funktionen in `app/services/conditions.py` implementieren
(13 Tests in `test_conditions_scoring.py`). Kurvenformen einfach halten
(stückweise linear reicht) — kalibriert wird später mit echten Daten.
**Fertig:** Unit komplett grün (23/23).

## AP3 — Sync-API grün (Finds/Signals)
DB-Wiring (`app/core/db.py` um Engine/Session-Dependency ergänzen),
Pydantic-Schemas, `POST /api/finds`, `POST /api/signals`, `GET /api/finds`
mit Idempotenz über `client_uuid`. `revisit_due` = `found_at` +
`params.REVISIT_OFFSET` serverseitig ableiten — **dafür Test ergänzen**.
**Fertig:** `test_sync_idempotency.py` grün plus neuer revisit-Test.

## AP4 — Coverage-Service grün
`classify_confidence` und `create_coverage` (ST_Buffer + ST_Union auf
geography, per SQL). **Fertig:** `test_coverage.py` grün.

## AP5 — Track-Import-Endpunkt
`POST /api/tracks/import` (GPX-Upload): parse → Rohtrack speichern
(unverändert!) → clean → Coverage anlegen. Session-Zuordnung über
Zeitüberlappung, sonst `session_id = null`. Duplikaterkennung über
Zeitfenster+Geometrie. Tests ergänzen (Fixtures liegen bereit).
GPX-Upload MUSS gegen XML-Entity-Expansion gehärtet sein (defusedxml oder
äquivalente Größen-/Tiefenbegrenzung) — Pflicht, nicht optional.

## AP6 — Areas- und Sessions-API
`GET/POST /api/areas`, `POST /api/sessions`, `PATCH /api/sessions/{id}/end`.
Beim Beenden: `conditions_score` und Wetterwerte aus dem letzten
`conditions_snapshot` des Gebiets einfrieren (Spec §5 „Wichtig").
Tests ergänzen.

## AP7 — Open-Meteo-Ingest + Conditions-Endpunkt
Job `app/jobs/weather_ingest.py` (als `python -m` lauffähig): Forecast+
Archiv je Area abrufen, `validate_openmeteo_response` PFLICHT, Upsert in
`conditions_snapshot`. `GET /api/conditions/{area_id}`: 7-Tage-Ausblick
mit voller Score-Aufschlüsselung (Invariante 10). HTTP-Aufrufe in Tests
mocken; Attribution-Hinweis (CC BY 4.0) in die Antwort-Metadaten.

## AP8 — Auth
ADR 0005 umsetzen: Login-Endpunkt (Argon2-Verify gegen
`AUTH_PASSWORD_HASH`), httpOnly-Session-Cookie 90 Tage, Rate-Limit,
Dependency schützt alle `/api/*` außer `/api/health` und Login.
Hilfsskript zum Hash-Erzeugen. Tests ergänzen; bestehende Tests
bekommen eine Auth-Fixture.

## AP9 — Railway-Deploy (Backend)
Dockerfile (Python 3.12, uv), Railway-Konfiguration in `infra/railway/`
dokumentieren. **Manuelle Schritte des Nutzers werden hier vom
Projektmanagement einzeln angeleitet** (Account, PostGIS-Template,
Volumes, Volume-Backups AKTIVIEREN, ENV-Secrets, Cron für AP7-Job).
**Fertig:** `/api/health` öffentlich über HTTPS erreichbar.

## AP10 — Frontend-Grundgerüst + Planer-Shell
Vite+React+TS+MapLibre initialisieren (`frontend/`), Basiskarte als
PMTiles-Regional-Extract (ADR 0002; Beschaffung: go-pmtiles gegen den
aktuellen Protomaps-Build, Bbox Aachen/Eifel/Ardennen, Ablage
`data/basemap.pmtiles`, Attribution OSM+Protomaps sichtbar). Planer:
Karte, Fundliste, Login. Vitest-Setup.

## AP11 — Feldmodus-UI
Spec §7, nicht verhandelbar: Vollbildkarte, 3 Buttons (72-px-Targets,
Daumenzone), Ein-Tap-Logging in IndexedDB-Queue, GPS-Genauigkeit
permanent sichtbar, Blockierung > `FIND_ACCURACY_BLOCK_M` mit
unübersehbarer Warnung, Haptik+Ton, Safe-Area-Insets, heller
Hochkontrast. Umschalten zum Planer nur über bewusste Geste.

## AP12 — Offline-Sync-Queue + Service Worker
Queue-Replays mit `client_uuid` (Server ist ab AP3 idempotent),
Sync-Status pro Eintrag + „n nicht synchronisiert"-Zähler (Invariante 4).
Workbox-Grundgerüst. **Vorab Spike S1** (eigene Session): PMTiles aus
lokal gespeicherter Datei (OPFS/Cache Storage) in MapLibre laden,
iOS-Safari — Ergebnis als ADR-0003-Update dokumentieren.

## AP13 — Media + Nachbearbeitung
`POST /api/media` (Foto/Voice, komprimiert, verzögert), Fund-Detail im
Planer, `id_pending`-Liste, geführte Foto-Sequenz (Spec §4a).

## AP14 — Wiederbesuchs-Dashboard
`GET /api/revisits/due`: Funde räumlich clustern
(`FIND_CLUSTER_RADIUS_M`), **MIN(revisit_due) je Fundstelle** (nicht je
Fund), gekoppelt an aktuellen Bedingungsscore. Tests ergänzen.

## AP15 — pg_dump off-platform
ADR 0004 Teil 2: wöchentlicher `pg_dump -Fc` + Media-Archiv, Ziel wird
vorher vom Nutzer entschieden. Restore-Drill dokumentieren und einmal
durchführen.

---

## Parallel, Nutzer-Aufgabe (kein Code)
**GPX-Logger-Feldtest** nach ADR 0006: zwei Kandidaten-Apps, je ~30 min
Track mit iPhone in der Tasche, GPX exportieren und prüfen lassen.
Ergebnis entscheidet, ob AP1-Parsing um App-spezifische Extensions
ergänzt werden muss.
