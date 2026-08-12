import { expect, test } from "vitest";

import { istZuKlein, rechteckPolygon } from "./rechteck";

test("Ring ist geschlossen und in [lon, lat]", () => {
  const polygon = rechteckPolygon({ lng: 6.5, lat: 50.5 }, { lng: 6.6, lat: 50.6 });

  expect(polygon.type).toBe("Polygon");
  const ring = polygon.coordinates[0] ?? [];
  expect(ring).toHaveLength(5);
  expect(ring[0]).toEqual(ring[4]);
  expect(ring[0]).toEqual([6.5, 50.5]);
  expect(ring[2]).toEqual([6.6, 50.6]);
});

test("von rechts unten nach links oben gezogen ergibt dasselbe Rechteck", () => {
  const hin = rechteckPolygon({ lng: 6.5, lat: 50.5 }, { lng: 6.6, lat: 50.6 });
  const zurueck = rechteckPolygon({ lng: 6.6, lat: 50.6 }, { lng: 6.5, lat: 50.5 });

  expect(zurueck).toEqual(hin);
});

test("Fehlklick zählt nicht als Gebiet", () => {
  expect(istZuKlein({ lng: 6.5, lat: 50.5 }, { lng: 6.50001, lat: 50.50001 })).toBe(true);
  expect(istZuKlein({ lng: 6.5, lat: 50.5 }, { lng: 6.51, lat: 50.51 })).toBe(false);
});
