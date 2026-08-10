# Railway-Cron: Wetter-Ingest

Setzt ADR 0001 um ("Railway-Cron ruft `backend/app/jobs/`-Skripte, täglich").

## Kommando

```
python -m app.jobs.weather_ingest
```

Arbeitsverzeichnis: `backend/`. Der Job nimmt keine Argumente — die
Konfiguration kommt vollständig aus der Umgebung.

## Umgebung

| Variable | Zweck |
|---|---|
| `DATABASE_URL` | PostGIS-Instanz, dieselbe wie der API-Service |

Ein API-Key ist nicht nötig: Open-Meteo ist bei nicht-kommerzieller Nutzung
ohne Schlüssel nutzbar (Spec §5). Attribution ist trotzdem Pflicht und wird
von `GET /api/conditions/{area_id}` in den Antwort-Metadaten mitgeliefert.

## Zeitplan

Täglich, einmal. Uhrzeit unkritisch — empfohlen früh morgens UTC, damit der
Ausblick vor der Tagesplanung frisch ist. Ein verpasster Lauf ist unkritisch:
Der nächste Lauf holt die letzten 14 Tage ohnehin erneut und überschreibt per
Upsert.

## Was der Job schreibt

Je Gebiet (Abrufpunkt: `ST_Centroid` der Gebietsgeometrie) **ein** Aufruf
gegen die Forecast-API mit `past_days=14` und `forecast_days=7` — beide
Zeiträume aus einem Modelllauf (ADR 0007):

- **letzte 14 Tage** — so weit blickt `rain_score` zurück;
- **nächste 7 Tage** — so weit reicht der Ausblick.

Als Tageszeilen in `conditions_snapshot`, Upsert über
`UNIQUE(area_id, date)`.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| `0` | alle Gebiete erfolgreich |
| `1` | mindestens ein Gebiet gescheitert (Details in der Ausgabe) |

Ein scheiterndes Gebiet stoppt die übrigen nicht. Der Exit-Code ist trotzdem
ungleich 0 — sonst meldet der Cron-Job Erfolg, obwohl Daten fehlen.

## Überwachung

Sinnvollster Alarm ist nicht der Exit-Code allein, sondern ein Blick auf die
Datenlage: Endet eine Session dauerhaft mit `score_reason`, fehlen Snapshots.
`GET /api/conditions/{area_id}` zeigt dasselbe pro Tag im Klartext.
