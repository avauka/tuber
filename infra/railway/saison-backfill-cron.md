# Railway-Cron: Saisonzustand

Setzt den „Rückweg" aus ADR 0007 um: Archiv-Backfill als eigener Job,
additiv, in eigenen Tabellen. **Der Wetter-Ingest bleibt davon unberührt.**

## Zwei Größen, die man nicht verwechseln darf

| | Bedingungs-Engine | Saisonzustand |
|---|---|---|
| Frage | „Ist jetzt ein guter Zeitpunkt?" | „Ist dieses Jahr eins?" |
| Horizont | 14 Tage zurück, 7 voraus | 180 Tage zurück |
| Quelle | `api.open-meteo.com/v1/forecast` | `archive-api.open-meteo.com/v1/archive` (ERA5) |
| Tabelle | `conditions_snapshot` | `season_state`, `season_normal` |
| Job | `app.jobs.weather_ingest` | `app.jobs.season_backfill` |
| Takt | täglich | **monatlich** |

Die Trennung ist beabsichtigt und in ADR 0007 begründet: Die Engine braucht
ein nahtloses 3-bis-7-Tage-Fenster aus einem Modelllauf, das Archiv hängt
dafür zwei Tage nach. Für eine Sechsmonatsbilanz ist derselbe Nachlauf
belanglos.

## Kommando

```
python -m app.jobs.season_backfill
```

Eigener Cron-Service, **dasselbe Image** wie der API-Service.
Arbeitsverzeichnis `backend/`, keine Argumente.

## Umgebung

### Service `saison-cron`

| Variable | Zweck | Pflicht |
|---|---|---|
| `DATABASE_URL` | Referenz auf `db` | ja |

Kein API-Schlüssel: Open-Meteo ist bei nicht-kommerzieller Nutzung
schlüssellos. Kein Volume, kein `SESSION_SECRET` — der Job spricht kein
HTTP an, er ruft nur ab und schreibt in die Datenbank.

## Zeitplan

**Monatlich**, Tag und Uhrzeit unkritisch (empfohlen: 3. des Monats, nachts
UTC). Nicht täglich: Ein 180-Tage-Fenster verschiebt sich in einem Monat um
ein Sechstel. Täglich abzurufen wäre Last ohne Erkenntnis.

## Was der Job tut

Je Gebiet, am Schwerpunkt der Gebietsgeometrie:

1. **Normale besorgen** — einmalig 1991–2020, rund 260 KB, danach aus der
   Datenbank. Das ist der größte Einzelaufruf des Pakets und passiert
   genau einmal je Gebiet. Ein neues Gebiet holt sie beim nächsten Lauf.
2. **180 Tage abrufen**, Stichtag drei Tage zurück (ERA5-Nachlauf).
3. **Kennzahlen rechnen und upserten** über `(area_id, window_end)` — ein
   zweiter Lauf für denselben Stichtag aktualisiert die Zeile, statt eine
   zweite anzulegen.

Gemessen für ein Gebiet: **4,4 s** inklusive des 30-Jahres-Abrufs.

## Kennzahlen

Vier Anteile am Mittel 1991–2020 (Niederschlag 30/90/180 Tage,
Bodenfeuchte 90 Tage) plus die längste Trockenphase in 180 Tagen, absolut.

**Keine Gesamtnote.** Eine verdichtete Zahl wäre nicht kalibrierbar,
solange keine Funddaten existieren, und Invariante 10 verlangt
Aufschlüsselbarkeit ohnehin.

Die Werte sind **Modellwerte, keine Messwerte** — ERA5 ist eine Reanalyse.
Der Planer sagt das an der Zahl dazu.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| `0` | alle Gebiete verarbeitet |
| `1` | mindestens ein Gebiet gescheitert (Details im Log) |

Ein Gebiet, das scheitert, stoppt die übrigen nicht — dieselbe
Fehlerisolation wie beim Wetter-Ingest.

## Wenn eine Antwort Lücken hat

Der Zustand wird trotzdem geschrieben, aber `complete = false` und
`missing_days` sagen, worauf er beruht. Der Planer kennzeichnet das.
Eine stille Teilsumme wäre eine Zahl, der man ihre Unvollständigkeit nicht
ansieht.

## Anzeige

`GET /api/areas` liefert den jüngsten Saisonzustand je Gebiet als Feld
`season`; der Planer zeigt ihn in der Gebietsliste. Keine eigene Seite,
kein eigener Endpunkt — es ist ein Attribut des Gebiets.
