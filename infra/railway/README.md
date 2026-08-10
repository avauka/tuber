# Railway-Deployment — Ziel-Topologie und Ist-Zustand

Setzt ADR 0001 um. Die manuellen Schritte im Railway-Dashboard werden separat
angeleitet; hier steht, **was** am Ende stehen soll.

## Stand 2026-08-10 (AP9b von aussen verifiziert)

| Punkt | Stand |
|---|---|
| Domain | `https://tuber-production-9a4c.up.railway.app` |
| `db` (PostGIS) | läuft — belegt durch die im Entrypoint gelaufene Migration |
| `api` | läuft, `/api/health` → `200` |
| HTTPS | HTTP wird per `301` umgeleitet |
| Auth | alle `/api/`-Routen ohne Cookie → `401` |
| `AUTH_PASSWORD_HASH` | gesetzt und nicht leer (Fehlversuch → `401`, nicht `500`) |
| `wetter-cron` | **noch nicht eingerichtet** |
| Volume-Backups | im Dashboard zu bestätigen (ADR 0004) |
| `/docs`, `/redoc`, `/openapi.json` | **öffentlich erreichbar** — siehe unten |

### Offener Punkt: öffentliches API-Schema

Die FastAPI-Oberflächen liegen unter `/docs`, `/redoc` und `/openapi.json`,
also **ausserhalb** von `/api/` — und damit ausserhalb des Auth-Schutzes, der
bewusst nur `/api/*` abdeckt. Abrufbar ist die vollständige Endpunktliste samt
Feldnamen und Enum-Werten (rund 24 KB).

Keine Zugangsdaten, keine Fundorte. Aber es ist die komplette Landkarte der
API für jeden, der die Domain kennt. Drei Wege, die Entscheidung liegt beim
Projektmanagement:

1. In der Produktion abschalten: `FastAPI(docs_url=None, redoc_url=None,
   openapi_url=None)`, gesteuert über eine ENV-Variable.
2. Unter `/api/` verschieben, dann greift der bestehende Schutz.
3. So lassen — bei einer privaten Single-User-App ohne Registrierung ein
   überschaubares Risiko.

## Drei Services in einem Projekt

| Service | Herkunft | Zweck |
|---|---|---|
| `db` | Railway-Template PostGIS | PostgreSQL 16 + PostGIS 3.4, persistentes Volume |
| `api` | GitHub-Repo, `backend/Dockerfile` | FastAPI hinter Railway-TLS |
| `wetter-cron` | **dasselbe Image** wie `api` | täglicher Open-Meteo-Ingest |

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
