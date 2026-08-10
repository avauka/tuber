# ADR 0002 — Basiskarte: Protomaps-PMTiles, selbst gehostet

**Datum:** 2026-08-10 · **Status:** angenommen

## Entscheidung
Regionaler Extract (Bbox Aachen/Eifel/Ardennen) aus dem Protomaps-Planet-Build
via `pmtiles extract`, als einzelne statische Datei auf einem Railway-Volume,
ausgeliefert per HTTP-Range-Requests. MapLibre liest sie über das
pmtiles-Protokoll. Styles: protomaps basemaps (helles Thema, Feldmodus-tauglich
anpassen).

## Verworfen
- OpenFreeMap public instance: kostenlos und ohne Limits, aber Offline-Caching
  fremder Tiles + Abhängigkeit von donation-finanziertem Dienst.
- MapTiler Free: Offline-Caching nach unserem Stand ToS-widrig.

## Konsequenzen
- Attribution: OpenStreetMap contributors (ODbL) + Protomaps-Hinweis, sichtbar.
- Tile-Aktualität liegt bei uns (Extract gelegentlich neu ziehen — unkritisch,
  Wald ändert sich langsam).
- Offline-Strategie (ADR 0003) baut direkt darauf auf.
