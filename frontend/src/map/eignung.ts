import type { FillLayerSpecification } from "maplibre-gl";

/**
 * Darstellung der Eignungskarte (ADR 0008, Spec §6).
 *
 * **Vier diskrete Klassen, kein Farbverlauf.** Ein glatter Verlauf
 * suggeriert eine Trennschärfe, die abgeleitete Daten nicht hergeben — der
 * pH stammt aus Geologie und Bodentyp, nicht aus einer Messung (Spec §13).
 *
 * Sprachregelung (Invariante 9): „Eignung", nie „Wahrscheinlichkeit".
 */

export const EIGNUNG_QUELLE = "tuber-eignung";
export const EIGNUNG_EBENE = "eignung-flaeche";

/** Gleiche Origin, damit das Sitzungs-Cookie mitgeht (ADR 0005). */
export const EIGNUNG_PFAD = "/api/suitability/suitability.pmtiles";
export const EIGNUNG_URL = `pmtiles://${EIGNUNG_PFAD}`;

// Der Layername in den Vektorkacheln, vergeben von stufe2_tiles.py.
export const EIGNUNG_QUELLLAYER = "suitability";

export type Klasse = 1 | 2 | 3 | 4;

export const KLASSEN: { klasse: Klasse; text: string; farbe: string; von: number; bis: number }[] = [
  { klasse: 1, text: "gering", farbe: "#cfc8b8", von: 0, bis: 25 },
  { klasse: 2, text: "mäßig", farbe: "#d7d79a", von: 25, bis: 50 },
  { klasse: 3, text: "gut", farbe: "#8fbf6a", von: 50, bis: 75 },
  { klasse: 4, text: "sehr gut", farbe: "#2f6f4e", von: 75, bis: 100 },
];

export function klassentext(klasse: number): string {
  return KLASSEN.find((eintrag) => eintrag.klasse === klasse)?.text ?? "unbekannt";
}

/** Klartext der Kaskadenstufe (ADR 0008 §5) — die Datenqualitäts-Ampel. */
export function stufentext(stufe: number): string {
  switch (stufe) {
    case 1:
      return "Stufe 1 — Bodenkarte 1:5.000 (feinste Datenlage)";
    case 2:
      return "Stufe 2 — Geologische Karte 1:100.000 und Bodenkarte 1:50.000";
    case 3:
      return "Stufe 3 — BFD50 Rheinland-Pfalz";
    case 4:
      return "Stufe 4 — SoilGrids 250 m (gröbster Rückfall)";
    default:
      return "ohne Angabe";
  }
}

export const FAKTOR_TEXT: Record<string, string> = {
  kalk: "Kalk / pH",
  wasser: "Wasserhaushalt",
  exposition: "Exposition",
  wirtsbaum: "Wirtsbaum",
  struktur: "Bestandsstruktur",
  klima: "Klima",
};

export function faktortext(name: string): string {
  return FAKTOR_TEXT[name] ?? name;
}

export function eignungsEbene(): FillLayerSpecification {
  return {
    id: EIGNUNG_EBENE,
    type: "fill",
    source: EIGNUNG_QUELLE,
    "source-layer": EIGNUNG_QUELLLAYER,
    paint: {
      // Ausgeschrieben statt aus KLASSEN erzeugt: Der Ausdruck ist Teil des
      // MapLibre-Stils und muss dessen feste Form haben.
      "fill-color": [
        "match",
        ["get", "klasse"],
        1,
        "#cfc8b8",
        2,
        "#d7d79a",
        3,
        "#8fbf6a",
        4,
        "#2f6f4e",
        "#cfc8b8",
      ],
      // Halbtransparent: Der Wald darunter bleibt lesbar, sonst plant man
      // auf einer Farbfläche statt auf einer Karte.
      "fill-opacity": 0.45,
    },
  };
}
