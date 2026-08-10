# ADR 0006 — GPX-Logger-App: offen, Feldtest

**Datum:** 2026-08-10 · **Status:** offen

## Kandidaten
Open GPX Tracker (Open Source), myTracks, Guru Maps.

## Prüfkriterien (in dieser Reihenfolge)
1. Schreibt die App pro Trackpunkt Genauigkeit ins GPX — Meter (Extension)
   oder mindestens `<hdop>`? Ohne das ist der 25-m-Filter nicht anwendbar.
2. Loggt sie zuverlässig 2–4 h im Hintergrund bei ausgeschaltetem Display?
3. Export über das iOS Share Sheet in die PWA.

## Konsequenz für den Import-Code
Der Parser behandelt drei Fälle: Meter-Genauigkeit vorhanden, nur hdop
(Umrechnung ~hdop x 5 m, als Schätzung gekennzeichnet), gar nichts
(Track-Confidence = niedrig, kein Punktfilter möglich).
