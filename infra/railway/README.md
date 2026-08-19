# Railway-Deployment — Ziel-Topologie und Ist-Zustand

Setzt ADR 0001 um. Die manuellen Schritte im Railway-Dashboard werden separat
angeleitet; hier steht, **was** am Ende stehen soll.

## Stand 2026-08-10 (AP9b von aussen verifiziert)

| Punkt | Stand |
|---|---|
| Domain | `https://tuber-production-9a4c.up.railway.app` |
| Service `PostGIS` | läuft — belegt durch die im Entrypoint gelaufene Migration |
| Service `tuber` (API) | läuft, `/api/health` → `200` |
| Service `wetter-cron` | angelegt, **Schedule noch offen** |
| HTTPS | HTTP wird per `301` umgeleitet |
| Auth | alle `/api/`-Routen ohne Cookie → `401` |
| `AUTH_PASSWORD_HASH` | gesetzt und nicht leer (Fehlversuch → `401`, nicht `500`) |
| Volume-Backups | **nicht aktiv** — nur im Pro-Plan (ADR 0004) |
| Schema-Oberfläche | seit AP9c standardmässig aus |

### Backup

Volume-Backups gibt es auf dem aktuellen Plan nicht (kein Pro-Plan,
entschieden 2026-08-10). Der verschlüsselte Dump aus AP15 ist damit die
einzige Sicherung. Er ist umgesetzt; einzurichten bleibt der
`backup-cron`-Service samt Volume — und der **regelmässige Download**, ohne
den der Dump Railway nie verlässt.

### Frontend im selben Service (ab AP10b)

Das gebaute Frontend liegt im Image unter `/app/static` und wird von FastAPI
ausgeliefert — gleiche Origin wie die API. Grund: Das Sitzungs-Cookie ist
httpOnly und `SameSite=Lax` (ADR 0005); bei gleicher Origin geht es ohne
CORS-Konstruktion mit, und die CSP bleibt eng.

**Einmalige Umstellung im Railway-Dashboard, Service `tuber`:**

| Einstellung | Wert |
|---|---|
| Root Directory | **leer** (Repo-Wurzel) — vorher `backend` |
| Dockerfile Path | `backend/Dockerfile` |

Ohne diese Umstellung schlägt der Build fehl: Die Node-Stage im
`backend/Dockerfile` braucht `frontend/`, und das liegt ausserhalb von
`backend/`. Ein `.dockerignore` in der Repo-Wurzel hält den Kontext klein.

Statische Dateien und die Login-Ansicht sind **öffentlich** — sonst käme
niemand zur Anmeldung. Geschützt bleibt alles unter `/api/`; die globale
Auth-Dependency ist unverändert. Unbekannte Pfade liefern `index.html`
(SPA-Fallback), unbekannte `/api/`-Pfade dagegen weiterhin `404`.

Seit AP10b setzt `SecurityHeadersMiddleware` auch eine
Content-Security-Policy (`default-src 'none'` plus das Nötige, kein fremder
Host). Der Wortlaut und die Begründung je Direktive stehen in
`backend/app/core/http_security.py`. Wer dort etwas ändert, prüft es **im
Browser** nach: Eine zu enge Policy ergibt eine weisse Karte, ohne dass im
Netzwerk-Tab etwas auffällt.

### Basiskarte

Der Extract der Basiskarte (ADR 0002, AP10a) läuft **manuell und ohne
Zeitplan** im Container des Service `tuber` — dort hängt das Volume. Ein Lauf
legt `/data/basemap.pmtiles` und `/data/basemap.meta.json` ab; ausgeliefert
wird noch nichts (das ist AP10b). Auslösung, Variablen und Aktualisierung:
[`basemap-extract.md`](basemap-extract.md).

Das Image bringt dafür `go-pmtiles` mit (eigene Build-Stage im
`backend/Dockerfile`), das ADR 0003 später auch zur Laufzeit braucht.

### Eignungskarte

Die Kacheln entstehen **lokal** auf dem Rechner des Nutzers
(`geoprocessing/`, ADR 0008 §8) und kommen über
`POST /api/suitability/upload` auf das Volume — anders als bei der
Basiskarte, die sich der Container selbst aus dem Netz holt. Rohdaten
berühren den Server nie; auf `/data` liegen nur `suitability.pmtiles`
(derzeit 7,7 MB) und `suitability.meta.json`.

Der Upload prüft vor dem Schreiben den freien Platz und die
PMTiles-Signatur und hängt erst danach um. Ablauf und Befehle:
[`geoprocessing/README.md`](../../geoprocessing/README.md).

### Schema-Oberfläche

Standardmässig sind `/docs`, `/redoc` und `/openapi.json` abgeschaltet. Für
die Entwicklung lässt sich `DOCS_ENABLED=true` setzen; die Oberfläche liegt
dann unter `/api/docs` und `/api/openapi.json` und damit hinter der Auth.

In der Produktion bleibt die Variable ungesetzt.

## Drei Services in einem Projekt

| Service | Herkunft | Zweck |
|---|---|---|
| `PostGIS` | Railway-Template PostGIS | PostgreSQL 16 + PostGIS 3.4, persistentes Volume |
| `tuber` | GitHub-Repo, `backend/Dockerfile` | FastAPI hinter Railway-TLS, liefert auch das Frontend aus |
| `wetter-cron` | **dasselbe Image** | täglicher Open-Meteo-Ingest |
| `backup-cron` | **dasselbe Image** | löst den Dump per HTTP aus (ADR 0004) |
| `saison-cron` | **dasselbe Image** | monatlicher Archiv-Backfill (ADR 0007 „Rückweg") |

Railway kennt **keine geteilten Volumes** — ein Volume gehört genau einem
Service (verifiziert 2026-08-11). Das Volume hängt deshalb am Service `tuber`
(Mount `/data`), und der Dump wird dort geschrieben. `backup-cron` klopft nur
per HTTP an und braucht selbst kein Volume.

`wetter-cron` ist bewusst kein eigenes Image: Der Job importiert dieselben
Modelle und dieselbe Scoring-Engine wie die API. Zwei Images hiessen zwei
Stände, die auseinanderlaufen können.

- **Startbefehl `wetter-cron`:** `python -m app.jobs.weather_ingest`
- **Schedule:** täglich, Uhrzeit unkritisch (empfohlen früh morgens UTC)

Der Job endet mit Exit-Code `1`, sobald ein Gebiet gescheitert ist — Railway
markiert den Lauf dann als fehlgeschlagen. Details siehe
[`weather-ingest-cron.md`](weather-ingest-cron.md).

## Umgebungsvariablen

### Service `db`
Kommt vom Template. Railway stellt `DATABASE_URL` als Referenz bereit.

### Service `api`

| Variable | Wert | Pflicht |
|---|---|---|
| `DATABASE_URL` | Referenz auf `db` | ja |
| `SESSION_SECRET` | langer Zufallswert, signiert das Session-Cookie | ja |
| `AUTH_PASSWORD_HASH` | Argon2id-Hash (siehe unten) | ja |
| `PORT` | setzt Railway selbst | — |
| `MEDIA_ROOT` | Pfad auf dem Media-Volume, z. B. `/data/media` | ab AP13 |
| `BASEMAP_DIR` | Ablage der Basiskarte, Standard `/data` | nein |
| `SUITABILITY_DIR` | Ablage der Eignungskarte, Standard `/data` | nein |
| `FRONTEND_DIST` | gebautes Frontend, Standard `/app/static` | nein |
| `DOCS_ENABLED` | **nicht setzen** — öffnet die Schema-Oberfläche | nein |
| `BACKUP_DIR` | Ablage auf dem Volume, Standard `/data/backups` | ab AP15 |
| `BACKUP_PASSPHRASE` | symmetrische GPG-Passphrase für den Dump | ab AP15 |
| `BACKUP_TRIGGER_TOKEN` | Bearer-Token, mit dem der Cron auslöst | ab AP15 |

Die Variablen des Basiskarten-Laufs (`BASEMAP_BUILD_DATE` und Co.) stehen
bewusst **nicht** in dieser Tabelle: Sie gehören zum einzelnen manuellen Lauf,
nicht dauerhaft an den Service — siehe [`basemap-extract.md`](basemap-extract.md).

Fehlen `SESSION_SECRET` oder `AUTH_PASSWORD_HASH`, antwortet der Login mit
`500` statt jemanden durchzulassen — eine Fehlkonfiguration soll laut
scheitern.

Hash erzeugen, lokal aus `backend/`:

```
uv run python scripts/hash_password.py
```

Das Klartextpasswort gehört nirgendwohin ausser in deinen Passwortmanager.

### Service `wetter-cron`

| Variable | Wert | Pflicht |
|---|---|---|
| `DATABASE_URL` | Referenz auf `db` | ja |

Kein API-Key: Open-Meteo ist bei nicht-kommerzieller Nutzung schlüssellos
(Spec §5). Kein `SESSION_SECRET` — der Job spricht kein HTTP an.

### Service `saison-cron`

| Variable | Wert | Pflicht |
|---|---|---|
| `DATABASE_URL` | Referenz auf `db` | ja |

Monatlich, nicht täglich — der Saisonzustand ändert sich langsam. Er ist
eine **zweite, getrennte** Grösse neben der Bedingungs-Engine und rührt
`conditions_snapshot` nicht an. Details:
[`saison-backfill-cron.md`](saison-backfill-cron.md).

### Service `backup-cron`

| Variable | Wert | Pflicht |
|---|---|---|
| `BASE_URL` | öffentliche Domain des API-Service | ja |
| `BACKUP_TRIGGER_TOKEN` | derselbe Token wie am Service `tuber` | ja |

Kein `DATABASE_URL`, kein `BACKUP_PASSPHRASE`, kein Volume — der Job löst nur
`POST /api/backups/create` aus. Details, Zeitplan, Exit-Codes und der
Notausgang bei Schreibrechten: [`backup-cron.md`](backup-cron.md).

## Healthcheck

| | |
|---|---|
| Pfad | `/api/health` |
| Erwartet | `200` mit `{"status":"ok"}` |

Der Pfad ist bewusst öffentlich (ADR 0005): Ein Healthcheck, der ein Cookie
bräuchte, wäre keiner.

## DATABASE_URL

Railway liefert das Schema `postgres://`. SQLAlchemy 2 kennt es nicht mehr;
`app.core.db.normalize_database_url` ergänzt den Treiber `+psycopg`. Das gilt
für die Anwendung **und** für Alembic, weil `alembic/env.py` die URL über
dieselbe Funktion holt. Es ist also nichts von Hand umzuschreiben.

## Volumes und Backup

- Volume am `db`-Service für die Datenbank
- Volume am `api`-Service für Media (ab AP13), die Backups (ab AP15) und die
  Basiskarte (ab AP10a, ~208 MB von 5 GB). `GET /api/backups` meldet die
  Auslastung mit — ein volles Volume bräche sonst still die Backup-Rotation.
- **Volume-Backups ab Tag 1 aktivieren** (ADR 0004). Sie schützen nicht gegen
  Projekt- oder Accountverlust — der wöchentliche `pg_dump` off-platform aus
  AP15 bleibt trotzdem nötig.

## Start des API-Containers

`backend/entrypoint.sh` führt `alembic upgrade head` aus und startet danach
uvicorn. Die Migration läuft bewusst im Entrypoint und nicht als separater
Release-Schritt: Bei einer einzelnen Instanz gibt es kein
Nebenläufigkeitsproblem, und ein vergessener Release-Schritt wäre die
wahrscheinlichere Fehlerquelle.

Ein Deploy mit fehlgeschlagener Migration startet gar nicht erst — der
Entrypoint bricht bei Fehlern ab (`set -e`).

## Dockerfile-Pfad kommt aus railway.json

Die Datei `railway.json` in der Repo-Wurzel legt fuer **alle** Dienste des
Projekts fest, dass mit `backend/Dockerfile` gebaut wird. Damit muss der
Pfad nicht je Dienst im Dashboard gesucht werden — das Feld ist dort je
nach Ansicht nicht ohne Weiteres zu finden.

Bewusst steht dort **nur** der Build-Abschnitt. Ein `startCommand` in
dieser Datei gaelte fuer jeden Dienst gleichermassen und wuerde die
Unterscheidung zwischen API und den Cron-Diensten aufheben; der
Startbefehl bleibt deshalb je Dienst im Dashboard.

Root Directory bleibt bei allen Diensten leer.
