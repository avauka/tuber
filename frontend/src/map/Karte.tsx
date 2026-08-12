import type { FeatureCollection, Point, Polygon as GeoPolygon } from "geojson";
import {
  GeoJSONSource,
  Map as MapLibreKarte,
  NavigationControl,
  ScaleControl,
  addProtocol,
  setWorkerUrl,
  type LngLat,
  type MapMouseEvent,
} from "maplibre-gl";
// MapLibre 6 laedt seinen Kachel-Worker als eigene Datei und baut den Pfad
// zur Laufzeit zusammen (`new URL("./maplibre-gl-worker.mjs", import.meta.url)`).
// Das sieht kein Bundler, also landet die Datei sonst nicht im Build: Der
// Worker liefe ins Leere, der SPA-Fallback antwortete mit index.html, und
// die Karte bliebe weiss. `?worker&url` laesst Vite den Worker samt seiner
// eigenen Importe buendeln und gibt uns die URL dazu.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { FetchSource, PMTiles, Protocol } from "pmtiles";
import { useEffect, useRef } from "react";

import type { BasiskartenMeta, Fund, Gebiet, Polygon, Signal } from "../shared/typen";
import { istZuKlein, rechteckPolygon } from "./rechteck";
import { ARCHIV_PFAD, basisStil } from "./stil";

import "maplibre-gl/dist/maplibre-gl.css";

type Props = {
  funde: Fund[];
  signale: Signal[];
  gebiete: Gebiet[];
  meta: BasiskartenMeta | null;
  zeichenmodus: boolean;
  /** Fertig gezogenes, noch nicht gespeichertes Rechteck. */
  entwurf: Polygon | null;
  onRechteck: (geometrie: Polygon) => void;
};

// Mitte der Bbox aus ADR 0002, bis die Metadaten der Karte da sind.
const START: [number, number] = [6.3, 50.4];
const START_ZOOM = 9;

// Das Archiv hört bei z14 auf; darüber zeichnet MapLibre per Overzoom
// weiter (AP10a verifiziert).
const MAX_ZOOM = 18;

const QUELLEN = {
  funde: "tuber-funde",
  signale: "tuber-signale",
  gebiete: "tuber-gebiete",
  entwurf: "tuber-entwurf",
} as const;

let eingerichtet = false;

/**
 * MapLibre einrichten — einmal pro Seitenaufruf.
 *
 * Die PMTiles-Quelle wird ausdrücklich mit `credentials: "same-origin"`
 * gebaut: Das Archiv liegt hinter der Auth, und die pmtiles-Bibliothek holt
 * es mit eigenen `fetch`-Aufrufen, an denen MapLibres `transformRequest`
 * vorbeigeht.
 */
function richteMapLibreEin(): void {
  if (eingerichtet) return;
  setWorkerUrl(workerUrl);
  const protokoll = new Protocol();
  protokoll.add(new PMTiles(new FetchSource(ARCHIV_PFAD, undefined, "same-origin")));
  addProtocol("pmtiles", protokoll.tile);
  eingerichtet = true;
}

function punkte(
  eintraege: { id: string; lat: number; lon: number }[],
): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: eintraege.map((eintrag) => ({
      type: "Feature",
      id: eintrag.id,
      geometry: { type: "Point", coordinates: [eintrag.lon, eintrag.lat] },
      properties: { id: eintrag.id },
    })),
  };
}

function flaechen(eintraege: Gebiet[]): FeatureCollection<GeoPolygon> {
  return {
    type: "FeatureCollection",
    features: eintraege.map((gebiet) => ({
      type: "Feature",
      id: gebiet.id,
      geometry: gebiet.geometry,
      properties: { name: gebiet.name },
    })),
  };
}

function leer(): FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}

function setzeDaten(karte: MapLibreKarte, quelle: string, daten: FeatureCollection): void {
  const ziel = karte.getSource(quelle);
  if (ziel && "setData" in ziel) {
    (ziel as GeoJSONSource).setData(daten);
  }
}

function legeEbenenAn(karte: MapLibreKarte): void {
  for (const quelle of Object.values(QUELLEN)) {
    karte.addSource(quelle, { type: "geojson", data: leer() });
  }

  karte.addLayer({
    id: "gebiete-flaeche",
    type: "fill",
    source: QUELLEN.gebiete,
    paint: { "fill-color": "#2f6f4e", "fill-opacity": 0.12 },
  });
  karte.addLayer({
    id: "gebiete-rand",
    type: "line",
    source: QUELLEN.gebiete,
    paint: { "line-color": "#2f6f4e", "line-width": 2 },
  });
  karte.addLayer({
    id: "gebiete-name",
    type: "symbol",
    source: QUELLEN.gebiete,
    layout: {
      "text-field": ["get", "name"],
      "text-font": ["Noto Sans Medium"],
      "text-size": 13,
    },
    paint: { "text-color": "#1d4433", "text-halo-color": "#ffffff", "text-halo-width": 1.5 },
  });

  karte.addLayer({
    id: "entwurf-rand",
    type: "line",
    source: QUELLEN.entwurf,
    paint: { "line-color": "#b5461e", "line-width": 2, "line-dasharray": [2, 1] },
  });

  // Signale zuerst, Funde darüber: Der Fund ist der wichtigere Punkt.
  karte.addLayer({
    id: "signale-punkt",
    type: "circle",
    source: QUELLEN.signale,
    paint: {
      "circle-radius": 5,
      "circle-color": "#2b6cb0",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.5,
    },
  });
  karte.addLayer({
    id: "funde-punkt",
    type: "circle",
    source: QUELLEN.funde,
    paint: {
      "circle-radius": 7,
      "circle-color": "#b5461e",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
    },
  });
}

function umriss(geometrie: Polygon | null): FeatureCollection {
  if (!geometrie) return leer();
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", geometry: geometrie, properties: {} }],
  };
}

export function Karte({ funde, signale, gebiete, meta, zeichenmodus, entwurf, onRechteck }: Props) {
  const behaelter = useRef<HTMLDivElement | null>(null);
  const karte = useRef<MapLibreKarte | null>(null);
  const bereit = useRef(false);
  const eingepasst = useRef(false);

  useEffect(() => {
    const knoten = behaelter.current;
    if (!knoten || karte.current) return;

    richteMapLibreEin();
    const instanz = new MapLibreKarte({
      container: knoten,
      style: basisStil(),
      center: START,
      zoom: START_ZOOM,
      maxZoom: MAX_ZOOM,
      // Eigener, dauerhaft sichtbarer Streifen statt des einklappbaren
      // Controls (Spec §15).
      attributionControl: false,
    });
    // Ohne diesen Zuhörer bleibt ein Fehler der Quelle unsichtbar: MapLibre
    // zeigt dann eine weisse Fläche, und im Netzwerk-Tab steht nichts, weil
    // die Kacheln im Worker verarbeitet werden.
    instanz.on("error", (ereignis) => {
      console.error("MapLibre:", ereignis.error?.message ?? ereignis);
    });
    instanz.addControl(new NavigationControl({ showCompass: false }), "top-right");
    instanz.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    instanz.on("load", () => {
      legeEbenenAn(instanz);
      bereit.current = true;
      setzeDaten(instanz, QUELLEN.funde, punkte(funde));
      setzeDaten(instanz, QUELLEN.signale, punkte(signale));
      setzeDaten(instanz, QUELLEN.gebiete, flaechen(gebiete));
    });

    karte.current = instanz;
    return () => {
      bereit.current = false;
      eingepasst.current = false;
      instanz.remove();
      karte.current = null;
    };
    // Absicht: genau einmal aufbauen. Die Daten kommen über die Effekte unten.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (karte.current && bereit.current) setzeDaten(karte.current, QUELLEN.funde, punkte(funde));
  }, [funde]);

  useEffect(() => {
    if (karte.current && bereit.current)
      setzeDaten(karte.current, QUELLEN.signale, punkte(signale));
  }, [signale]);

  useEffect(() => {
    if (karte.current && bereit.current)
      setzeDaten(karte.current, QUELLEN.gebiete, flaechen(gebiete));
  }, [gebiete]);

  // Das fertig gezogene Rechteck bleibt sichtbar, solange das Formular offen
  // ist — sonst füllt man Namen und Zufahrt für eine Fläche aus, die man
  // gerade nicht mehr sieht.
  useEffect(() => {
    if (karte.current && bereit.current)
      setzeDaten(karte.current, QUELLEN.entwurf, umriss(entwurf));
  }, [entwurf]);

  // Startausschnitt aus den Metadaten der Karte: genau der Bereich, den das
  // Archiv abdeckt. Nur beim ersten Mal — danach gehört der Ausschnitt dem
  // Nutzer.
  useEffect(() => {
    const instanz = karte.current;
    if (!instanz || !meta || eingepasst.current || meta.bbox.length !== 4) return;
    const [minLon, minLat, maxLon, maxLat] = meta.bbox as [number, number, number, number];
    eingepasst.current = true;
    instanz.fitBounds(
      [
        [minLon, minLat],
        [maxLon, maxLat],
      ],
      { padding: 24, animate: false },
    );
  }, [meta]);

  // Rechteck ziehen: Nur solange der Modus an ist, und ohne Zeichenpaket —
  // ein Gebiet ist Wetterbezug und Beschriftung, kein Kataster.
  useEffect(() => {
    const instanz = karte.current;
    if (!instanz) return;

    if (!zeichenmodus) {
      instanz.getCanvas().style.cursor = "";
      return;
    }

    let start: LngLat | null = null;
    instanz.getCanvas().style.cursor = "crosshair";
    instanz.dragPan.disable();

    const beginn = (ereignis: MapMouseEvent) => {
      start = ereignis.lngLat;
    };
    const ziehen = (ereignis: MapMouseEvent) => {
      if (!start) return;
      setzeDaten(instanz, QUELLEN.entwurf, {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: rechteckPolygon(start, ereignis.lngLat),
            properties: {},
          },
        ],
      });
    };
    const ende = (ereignis: MapMouseEvent) => {
      if (!start) return;
      const ecke = start;
      start = null;
      if (istZuKlein(ecke, ereignis.lngLat)) {
        setzeDaten(instanz, QUELLEN.entwurf, leer());
        return;
      }
      onRechteck(rechteckPolygon(ecke, ereignis.lngLat));
    };

    instanz.on("mousedown", beginn);
    instanz.on("mousemove", ziehen);
    instanz.on("mouseup", ende);

    return () => {
      instanz.off("mousedown", beginn);
      instanz.off("mousemove", ziehen);
      instanz.off("mouseup", ende);
      instanz.dragPan.enable();
      instanz.getCanvas().style.cursor = "";
      // Der Entwurf selbst bleibt stehen; er gehört jetzt dem Formular.
    };
  }, [zeichenmodus, onRechteck]);

  return <div className="karte" ref={behaelter} data-testid="karte" />;
}
