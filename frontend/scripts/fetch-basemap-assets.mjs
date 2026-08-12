/**
 * Holt Schriften und Sprite der Protomaps-Basiskarte nach public/basemap-assets.
 *
 *   node scripts/fetch-basemap-assets.mjs
 *
 * Warum die Dateien im Repo liegen und nicht zur Laufzeit geladen werden:
 * Der Standard-Stil von @protomaps/basemaps zeigt auf
 * protomaps.github.io. Damit haenge die Beschriftung der Karte an einem
 * fremden Host — im Wald ohne Netz fehlen dann alle Ortsnamen, und die
 * Content-Security-Policy muesste diesen Host oeffnen. ADR 0002 hat die
 * Basiskarte aus genau diesem Grund selbst gehostet; die Schriften gehoeren
 * dazu.
 *
 * Bereiche: 0-255 (Basic Latin, Latin-1) und 256-511 (Latin Extended-A)
 * decken Deutsch, Franzoesisch und Niederlaendisch ab — mehr Sprachen
 * kommen in der Eifel und den Ardennen auf der Karte nicht vor.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BASIS = "https://protomaps.github.io/basemaps-assets";
const ZIEL = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "basemap-assets");

const SCHRIFTEN = ["Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic"];
const BEREICHE = ["0-255", "256-511"];

// v4 passt zum Tileset 4.15.x, das der Extract-Job holt (AP10a).
const SPRITE_DATEIEN = ["light.json", "light.png", "light@2x.json", "light@2x.png"];

async function holen(url, ziel) {
  const antwort = await fetch(url);
  if (!antwort.ok) {
    throw new Error(`${antwort.status} ${antwort.statusText} fuer ${url}`);
  }
  await mkdir(dirname(ziel), { recursive: true });
  await writeFile(ziel, Buffer.from(await antwort.arrayBuffer()));
  console.log(`${ziel.replace(ZIEL, "basemap-assets")}`);
}

for (const schrift of SCHRIFTEN) {
  for (const bereich of BEREICHE) {
    await holen(
      `${BASIS}/fonts/${encodeURIComponent(schrift)}/${bereich}.pbf`,
      join(ZIEL, "fonts", schrift, `${bereich}.pbf`),
    );
  }
}

for (const datei of SPRITE_DATEIEN) {
  await holen(`${BASIS}/sprites/v4/${datei}`, join(ZIEL, "sprites", datei));
}

console.log("Fertig.");
