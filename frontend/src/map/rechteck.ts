import type { Polygon } from "../shared/typen";

export type Punkt = { lng: number; lat: number };

/**
 * Zwei gezogene Eckpunkte zu einem geschlossenen GeoJSON-Rechteck.
 *
 * Bewusst kein Zeichenwerkzeug-Paket: Ein Gebiet ist hier Wetterbezug und
 * Beschriftung, dafür genügt ein Rechteck (AP10b). Der Ring wird
 * geschlossen — `POST /api/areas` lehnt offene Ringe ab — und die Ecken
 * werden sortiert, damit auch ein von rechts unten nach links oben
 * gezogenes Rechteck ein gültiges Polygon ergibt.
 */
export function rechteckPolygon(a: Punkt, b: Punkt): Polygon {
  const westen = Math.min(a.lng, b.lng);
  const osten = Math.max(a.lng, b.lng);
  const sueden = Math.min(a.lat, b.lat);
  const norden = Math.max(a.lat, b.lat);

  return {
    type: "Polygon",
    coordinates: [
      [
        [westen, sueden],
        [osten, sueden],
        [osten, norden],
        [westen, norden],
        [westen, sueden],
      ],
    ],
  };
}

/** Kantenlänge in Grad — winzige Rechtecke sind Fehlklicks, keine Gebiete. */
export function istZuKlein(a: Punkt, b: Punkt): boolean {
  const MINDEST_GRAD = 0.0005; // rund 50 m
  return Math.abs(a.lng - b.lng) < MINDEST_GRAD || Math.abs(a.lat - b.lat) < MINDEST_GRAD;
}
