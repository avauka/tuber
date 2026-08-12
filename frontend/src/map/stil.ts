import { layers, namedFlavor } from "@protomaps/basemaps";
import type { StyleSpecification } from "maplibre-gl";

/**
 * Stil der Basiskarte (ADR 0002).
 *
 * Die Kacheln kommen aus der einen PMTiles-Datei auf unserem Volume, die
 * Schriften und das Sprite aus `public/basemap-assets` — beides bewusst
 * selbst gehostet. Der Standard-Stil von @protomaps/basemaps zeigt für die
 * Schriften auf protomaps.github.io; damit hinge die Beschriftung an einem
 * fremden Host, und die CSP müsste ihn öffnen.
 *
 * Helles Thema: Die App wird im Sonnenlicht gelesen (Spec §7), Dark Mode
 * ist ausdrücklich nicht der Standard.
 */

export const QUELLE = "protomaps";

/** Gleiche Origin — dadurch geht das Sitzungs-Cookie mit (ADR 0005). */
export const ARCHIV_PFAD = "/api/basemap/basemap.pmtiles";
export const ARCHIV_URL = `pmtiles://${ARCHIV_PFAD}`;

export function basisStil(): StyleSpecification {
  return {
    version: 8,
    glyphs: "/basemap-assets/fonts/{fontstack}/{range}.pbf",
    sprite: `${window.location.origin}/basemap-assets/sprites/light`,
    sources: {
      [QUELLE]: {
        type: "vector",
        url: ARCHIV_URL,
        // Die Attribution steht dauerhaft im eigenen Streifen (Spec §15),
        // nicht in MapLibres einklappbarem Control.
        attribution: "",
      },
    },
    layers: layers(QUELLE, namedFlavor("light"), { lang: "de" }),
  };
}
