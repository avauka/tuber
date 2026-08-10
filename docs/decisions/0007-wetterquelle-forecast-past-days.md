# ADR 0007 — Wetterquelle: Forecast-API mit `past_days`

**Datum:** 2026-08-10 · **Status:** angenommen

## Entscheidung
Der Wetter-Ingest holt Vergangenheit und Ausblick in **einem** Aufruf gegen
`https://api.open-meteo.com/v1/forecast` mit `past_days=14` und
`forecast_days=7`. Der separate Aufruf gegen die Archiv-API (`/v1/archive`)
entfällt ersatzlos, und mit ihm die Logik, in welcher Reihenfolge sich
überlappende Zeiträume überschreiben.

Das weicht bewusst von Spec §5 ab, die beide Endpunkte nennt.

## Kontext
`rain_score` gewichtet Regen, der **3 bis 7 Tage** zurückliegt, am stärksten —
das ist der fachliche Kern der Bedingungs-Engine. Die Archiv-API basiert auf
ERA5 und hängt rund zwei Tage nach. Die jüngsten Tage kämen also gar nicht aus
dem Archiv, sondern blieben Forecast-Werte, bis ein späterer Lauf sie ersetzt.

Damit hätte ausgerechnet das wichtigste Fenster gemischte Herkunft: teils
Modellvorhersage, teils Reanalyse, mit einem Sprung an der Nahtstelle. Ein
Score, der sich ändert, weil zwei Tage später ein anderer Datensatz nachrückt,
ist schwer zu erklären und noch schwerer zu kalibrieren.

## Begründung
- **Nahtstelle vermieden:** Vergangenheit und Zukunft stammen aus demselben
  Modelllauf. An der Tagesgrenze springt nichts.
- **Der Nachlauf trifft das falsche Fenster:** Zwei Tage Verzug liegen genau
  im 3-bis-7-Tage-Bereich, den das Scoring am höchsten gewichtet.
- **Halbierte Calls:** ein Aufruf je Gebiet statt zwei. Bei 10.000 Calls/Tag
  unkritisch, aber der Job wird einfacher und die Fehlerfläche kleiner.
- **Auflösung:** ERA5 ist mit rund 25 km deutlich gröber als das
  Forecast-Modell. Für Bodenfeuchte im Mittelgebirge ist das ein realer
  Unterschied.

## Ehrlicher Trade-off
Wir speichern damit **Modellwerte, keine Messwerte** — auch für die
Vergangenheit. Für die Frage "wann hingehen" ist das angemessen, weil ohnehin
eine Modellgröße (Bodenfeuchte) den Ausschlag gibt und kein Messnetz in
Bestandsdichte existiert. Für eine spätere wissenschaftliche Auswertung von
Fundkorrelationen wäre eine Reanalyse die sauberere Grundlage.

`conditions_snapshot.raw` archiviert die vollständige API-Antwort, die Herkunft
bleibt also nachvollziehbar.

## Rückweg
Falls Phase 3 echte Messwerte für die Auswertung braucht: ein
**Archiv-Backfill** als eigenes Arbeitspaket, das vorhandene Zeilen
rückwirkend mit ERA5-Werten ergänzt — additiv, in eigenen Spalten oder einer
eigenen Tabelle, damit Score-Historie und Auswertung sauber getrennt bleiben.
Der laufende Ingest bliebe davon unberührt.

## Konsequenzen
- `infra/railway/weather-ingest-cron.md` beschreibt einen Aufruf je Gebiet.
- Ein verpasster Cron-Lauf bleibt unkritisch: Der nächste Lauf holt die
  vergangenen 14 Tage ohnehin erneut und überschreibt per Upsert.
