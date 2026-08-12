# AP10b — Frontend-Grundgerüst + Planer-Shell

Kontext: Spec §7 (Modus „Planer"), ADR 0002 (Basiskarte), ADR 0005 (Auth),
CLAUDE.md. Phase 1. Lies ADR 0002 und ADR 0005, bevor du anfängst.

Vorbedingung erfüllt: AP10a ist durch. `/data/basemap.pmtiles` (208 MB, Bbox
5.4,49.7,7.2,51.1, maxzoom 14) und `/data/basemap.meta.json` liegen auf dem
Volume des Service `tuber`.

**Nicht in diesem Paket:** Feldmodus, Service Worker, Offline-Queue, IndexedDB,
GPX-Import-UI, Fund-Detail/Nachbearbeitung, Eignungskarte. Baue davon nichts,
auch nicht vorbereitend.

---

## 1. Auslieferung: gleiche Origin

Das gebaute Frontend wird von FastAPI ausgeliefert. Begründung: Das
Session-Cookie ist httpOnly und SameSite=Lax (ADR 0005) — bei gleicher Origin
geht es ohne CORS-Konstruktion mit, und die CSP bleibt eng.

- `frontend/` mit Vite, React 18, TypeScript, pnpm, vitest.
- Build nach `frontend/dist`, im Dockerfile in einer eigenen Node-Stage gebaut
  und in die finale Stage kopiert. Node-Version pinnen.
- FastAPI mountet die statischen Dateien. **`/api/*` darf dabei nie beschattet
  werden** — das Mount kommt nach den API-Routern.
- SPA-Fallback: unbekannte Pfade liefern `index.html`.
- Die Shell (HTML, JS, CSS) ist **öffentlich**, sonst ist die Login-Seite nicht
  erreichbar. Analog zu `PUBLIC_API_PATHS` in ADR 0005. Die Daten dahinter
  bleiben geschützt — das ist die bestehende globale Dependency, an der sich
  nichts ändert.

## 2. Basiskarte ausliefern

**Zuerst verifizieren:** Starlette-Version in `uv.lock` prüfen. Ab 0.39.0
beantwortet `FileResponse` Range-Requests (206/416, `Accept-Ranges: bytes`).
Ist die gelockte Version älter, anhalten und melden — ohne Range funktioniert
PMTiles nicht, und das ist eine Entscheidung, keine Reparatur.

- `GET /api/basemap/basemap.pmtiles` — `FileResponse` auf `/data/basemap.pmtiles`,
  hinter der bestehenden Auth (globale Dependency, nichts extra).
- **Keine Kompressions-Middleware auf dieser Route.** Die Kacheln sind im Archiv
  bereits gzip-komprimiert; doppeltes gzip auf einer Range-Antwort zerstört die
  Byte-Offsets. Falls irgendwo GZipMiddleware aktiv ist oder wird: diese Route
  ausnehmen und den Grund kommentieren.
- `GET /api/basemap/meta` — liefert `basemap.meta.json`. Wird für die
  Attribution mit Datenstand gebraucht.
- Fehlt die Datei: 503 mit klarer Meldung, nicht 500.
- Ein Test, der den Range-Request wirklich stellt und 206 plus korrekte
  `Content-Range` prüft. Nicht nur 200 auf den vollen Abruf.

## 3. Karte im Frontend

- MapLibre GL JS, `pmtiles`-Protokoll registriert, Quelle
  `pmtiles:///api/basemap/basemap.pmtiles`.
- Fetch mit `credentials: 'same-origin'`, damit das Cookie mitgeht.
- Style: `@protomaps/basemaps`, **auf 4er-Minor gepinnt, nicht auf Patch**. Das
  Tileset wandert im Patch-Bereich zwischen Builds (4.15.1 → 4.15.2 an einem
  Tag), der Style darf davon nicht abhängen. Helles Thema als Ausgangspunkt
  (Spec §7: kein Dark-Mode-Standard, Sonnenlicht).
- Startansicht auf die Bbox-Mitte, sinnvoller Zoom.
- **Attribution sichtbar und dauerhaft** (Spec §15, Pflicht): OpenStreetMap
  contributors (ODbL), Protomaps, dazu der Datenstand aus `/api/basemap/meta`
  (`osm_data_timestamp`). Nicht in einem Menü versteckt.

**CSP:** Die `SecurityHeadersMiddleware` bekommt eine Content-Security-Policy.
MapLibre erzeugt Web Worker aus Blob-URLs und PMTiles liest über `fetch` —
`worker-src blob:` und passende `connect-src`/`img-src` sind nötig. Baue die
Policy so eng wie möglich und **verifiziere im Browser, dass die Karte
tatsächlich rendert**, statt die Direktiven aus dem Kopf zu schreiben. Welche
Direktiven MapLibre in der eingesetzten Version genau braucht, ist zu prüfen,
nicht zu raten.

## 4. Login

- Login-Ansicht, `POST /api/auth/login`, Cookie wird vom Browser gehalten.
- Jede 401-Antwort führt zurück zur Login-Ansicht — auch mitten in der Sitzung
  (90-Tage-Cookie läuft irgendwann ab).
- Logout-Möglichkeit.
- Kein Token im LocalStorage, nirgends. Das Cookie ist httpOnly und bleibt es.

## 5. Fundliste

- `GET /api/finds`, neueste zuerst, als Liste **und** als Punkte auf der Karte.
- Anzeige: Datum, Art, `id_pending`-Kennzeichnung, GPS-Genauigkeit.
- Indikatorarten (`t_rufum`, `t_excavatum`) werden **nicht** ausgefiltert
  (Invariante 8) — auch kein Default-Filter, der sie versteckt.
- Keine Bearbeitung. `PATCH /api/finds/{id}` existiert nicht (Spec §12 nennt
  ihn, AP3 hat ihn nicht gebaut) — das ist ein eigenes Paket.

## 6. `GET /api/signals` (Backend, fehlt bislang)

Analog zu `GET /api/finds`: Liste mit optionalem `bbox`-Filter, neueste zuerst,
ohne Pagination (dieselbe Begründung wie bei den Funden). Tests ergänzen.
Im Frontend als eigene, visuell unterscheidbare Punktebene.

## 7. Gebietsverwaltung

Der Grund, warum das hier drin ist: Die Bedingungs-Engine ist seit AP2/AP7
fertig, aber unerreichbar — der Wetter-Job holt Daten **je Gebiet**, und
Gebiete lassen sich ohne Karte nicht anlegen.

- `GET /api/areas` als Liste und als Polygone auf der Karte.
- Anlegen über `POST /api/areas`: Name, Notizen, Zufahrt/Parken
  (`access_notes`), `offline_pinned`.
- **Geometrie als Rechteck, per Ziehen auf der Karte.** Bewusst kein
  Zeichenwerkzeug-Paket: die Bibliothekslage für MapLibre ist uneinheitlich, und
  ein Gebiet dient hier als Wetterbezug und Beschriftung — dafür genügt ein
  Rechteck. Freihand-Polygone später, wenn sich ein Bedarf zeigt.
- Der Server validiert die Topologie bereits (`ST_IsValid`); ein 422 wird im UI
  verständlich angezeigt, nicht verschluckt.

## 8. Tests

- Vitest-Setup lauffähig.
- Frontend: Login-Flow (401 → Login-Ansicht), Fundliste rendert, Areas-Formular
  schickt gültiges GeoJSON.
- Backend: `GET /api/signals` inkl. bbox; Basemap-Route mit echtem
  Range-Request; Basemap-Route ohne vorhandene Datei → 503.
- Keine Netzaufrufe in Tests.

---

## Fertig, wenn

- `uv run pytest` grün, `pnpm test` grün.
- `uv run ruff check .` / `ruff format --check .` repo-weit leer, `mypy` sauber,
  Frontend-Lint leer.
- Auf Railway deployed: Login funktioniert, die Karte rendert mit der PMTiles-
  Basiskarte, Attribution samt Datenstand sichtbar, ein Gebiet lässt sich
  anlegen und erscheint auf der Karte.
- Bericht nennt: gelockte Starlette-Version, die gesetzte CSP im Wortlaut, und
  ob der Range-Test wirklich 206 sieht.

Ein Commit, Präfix `AP10b:`. Tests dürfen ergänzt, nie gelöscht oder
aufgeweicht werden. Bei Unklarheiten anhalten und fragen, nicht raten.
