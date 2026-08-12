# TUBER — Frontend

React 18 + TypeScript + Vite, Karte mit MapLibre GL JS. Zwei UI-Modi liegen
getrennt: `src/planer` (dieses Paket, AP10b) und `src/feld` (eigenes Paket).

    pnpm install
    pnpm dev        # Dev-Server, /api geht an 127.0.0.1:8000
    pnpm test       # vitest
    pnpm lint
    pnpm build      # tsc --noEmit && vite build -> dist/

Im Betrieb wird `dist/` nicht separat ausgeliefert: Die Node-Stage im
`backend/Dockerfile` baut es und legt es ins Image, FastAPI liefert es von
derselben Origin wie die API aus (ADR 0005 — das Sitzungs-Cookie ist httpOnly
und `SameSite=Lax`).

## Karte

Die Kacheln kommen aus **einer** PMTiles-Datei auf unserem Volume
(`GET /api/basemap/basemap.pmtiles`, ADR 0002), gelesen über HTTP-Range.
Der Stil ist `@protomaps/basemaps`, helles Thema (Spec §7: gelesen wird im
Sonnenlicht).

Zwei Dinge, die nicht offensichtlich sind:

- **Schriften und Sprite liegen bei uns** (`public/basemap-assets`, geholt mit
  `pnpm basemap-assets`). Der Standard-Stil zeigt auf protomaps.github.io;
  damit hinge die Beschriftung an einem fremden Host, die CSP müsste ihn
  öffnen, und im Wald ohne Netz fehlten alle Ortsnamen.
- **Der MapLibre-Worker wird ausdrücklich mitgebaut.** MapLibre 6 setzt den
  Pfad zu `maplibre-gl-worker.mjs` zur Laufzeit zusammen; kein Bundler sieht
  das. Ohne den `?worker&url`-Import in `src/map/Karte.tsx` fehlt die Datei im
  Build, der SPA-Fallback antwortet mit `index.html` — und die Karte bleibt
  weiss, ohne Fehler im Netzwerk-Tab.

Die Version von `@protomaps/basemaps` ist auf die Minor gepinnt (`~5.7.0`).
Die Paketversion folgt **nicht** der Tileset-Version: Das Paket steht bei 5.x
und erzeugt Stile für das v4-Schema, das der Extract-Job holt (Tileset
4.15.x). Beim Anheben also nachsehen, ob die Ebenennamen noch passen.
