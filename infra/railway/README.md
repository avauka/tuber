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

### Schema-Oberfläche

Standardmässig sind `/docs`, `/redoc` und `/openapi.json` abgeschaltet. Für
die Entwicklung lässt sich `DOCS_ENABLED=true` setzen; die Oberfläche liegt
dann unter `/api/docs` und `/api/openapi.json` und damit hinter der Auth.

In der Produktion bleibt die Variable ungesetzt.

## Drei Services in einem Projekt

| Service | Herkunft | Zweck |
|---|---|---|
| `PostGIS` | Railway-Template PostGIS | PostgreSQL 16 + PostGIS 3.4, persistentes Volume |
| `tuber` | GitHub-Repo, `backend/Dockerfile` | FastAPI hinter Railway-TLS |
| `wetter-cron` | **dasselbe Image** | täglicher Open-Meteo-Ingest |
| `backup-cron` | **dasselbe Image** | verschlüsselter Dump (ADR 0004) |

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
| `BASEMAP_PMTILES_PATH` | Pfad auf dem Volume, z. B. `/data/basemap.pmtiles` | ab AP10 |
| `DOCS_ENABLED` | **nicht setzen** — öffnet die Schema-Oberfläche | nein |
| `BACKUP_DIR` | dieselbe Ablage wie `backup-cron`, z. B. `/data/backups` | ab AP15 |

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

### Service `backup-cron`

| Variable | Wert | Pflicht |
|---|---|---|
| `DATABASE_URL` | Referenz auf `PostGIS` | ja |
| `BACKUP_PASSPHRASE` | symmetrische GPG-Passphrase | **ja** |
| `BACKUP_DIR` | Ablage auf dem Volume, z. B. `/data/backups` | ja |

Details, Zeitplan und Exit-Codes: [`backup-cron.md`](backup-cron.md).
Der API-Service braucht `BACKUP_DIR` ebenfalls und dasselbe Volume — der
Cron schreibt, der Download-Endpunkt liest.

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
- Volume am `api`-Service für Media (ab AP13) und die Basiskarte (ab AP10)
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
