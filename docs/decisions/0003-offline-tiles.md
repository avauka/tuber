# ADR 0003 — Offline-Tiles: Area-Extracts, Client speichert lokal

**Datum:** 2026-08-10 · **Status:** angenommen, Umsetzungsdetail als Spike offen

## Entscheidung
`GET /api/offline/package/{area_id}` erzeugt serverseitig per `pmtiles extract`
(go-pmtiles-CLI) ein kleines PMTiles-File für die Area-Bbox. Der Client lädt es
herunter und speichert es lokal (OPFS oder Cache Storage); MapLibre liest offline
daraus.

## Offener Spike (vor Implementierung)
Verifizieren, dass die pmtiles-JS-Library zuverlässig aus einer lokal
gespeicherten Datei liest (FileSource/Blob) — inkl. iOS-Safari-Eigenheiten und
Speicherquota. Fallback: Service Worker cacht einzelne Tiles (Range-Request-
Caching ist fummelig, daher nur Plan B).

## Konsequenzen
- go-pmtiles muss im Backend-Image verfügbar sein.
- Speicherverbrauch pro Area wird dem Nutzer angezeigt (Spec §8).
