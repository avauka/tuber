import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import type { Polygon } from "../shared/typen";
import { fetchAttrappe, gebiet } from "../test/antworten";
import { GebietsPanel } from "./GebietsPanel";

const ENTWURF: Polygon = {
  type: "Polygon",
  coordinates: [
    [
      [6.5, 50.5],
      [6.6, 50.5],
      [6.6, 50.6],
      [6.5, 50.6],
      [6.5, 50.5],
    ],
  ],
};

function panel(ueberschreibungen: Partial<Parameters<typeof GebietsPanel>[0]> = {}) {
  const props = {
    gebiete: [],
    entwurf: ENTWURF,
    zeichenmodus: false,
    onZeichnen: vi.fn(),
    onVerwerfen: vi.fn(),
    onAngelegt: vi.fn(),
    ...ueberschreibungen,
  };
  render(<GebietsPanel {...props} />);
  return props;
}

test("schickt ein geschlossenes GeoJSON-Polygon an POST /api/areas", async () => {
  const attrappe = fetchAttrappe({ "/api/areas": { status: 201, koerper: gebiet() } });
  const props = panel();

  await userEvent.type(screen.getByLabelText("Name"), "Sötenich");
  await userEvent.type(screen.getByLabelText("Zufahrt und Parken"), "Waldweg ab Kirche");
  await userEvent.click(screen.getByRole("button", { name: "Gebiet anlegen" }));

  const [pfad, init] = attrappe.mock.calls[0] as [string, RequestInit];
  expect(pfad).toBe("/api/areas");
  expect(init.method).toBe("POST");

  const koerper = JSON.parse(String(init.body)) as {
    name: string;
    geometry: Polygon;
    access_notes: string | null;
    offline_pinned: boolean;
  };
  expect(koerper.name).toBe("Sötenich");
  expect(koerper.access_notes).toBe("Waldweg ab Kirche");
  expect(koerper.offline_pinned).toBe(false);
  expect(koerper.geometry.type).toBe("Polygon");

  // Der Server lehnt offene Ringe ab (services/geojson.py).
  const ring = koerper.geometry.coordinates[0] ?? [];
  expect(ring.length).toBe(5);
  expect(ring[0]).toEqual(ring[ring.length - 1]);
  // Reihenfolge ist [lon, lat] — vertauscht läge das Gebiet in Somalia.
  expect(ring[0]?.[0]).toBeCloseTo(6.5);
  expect(ring[0]?.[1]).toBeCloseTo(50.5);

  expect(props.onAngelegt).toHaveBeenCalled();
});

test("Cookie geht mit, kein Token im Spiel", async () => {
  const attrappe = fetchAttrappe({ "/api/areas": { status: 201, koerper: gebiet() } });
  panel();

  await userEvent.type(screen.getByLabelText("Name"), "Kall");
  await userEvent.click(screen.getByRole("button", { name: "Gebiet anlegen" }));

  const [, init] = attrappe.mock.calls[0] as [string, RequestInit];
  expect(init.credentials).toBe("same-origin");
  expect(JSON.stringify(init.headers ?? {})).not.toContain("Authorization");
});

test("422 des Servers wird verständlich angezeigt, nicht verschluckt", async () => {
  fetchAttrappe({
    "/api/areas": {
      status: 422,
      koerper: { detail: "Polygon ist topologisch ungueltig: Self-intersection" },
    },
  });
  const props = panel();

  await userEvent.type(screen.getByLabelText("Name"), "Kaputt");
  await userEvent.click(screen.getByRole("button", { name: "Gebiet anlegen" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("topologisch ungueltig");
  expect(props.onAngelegt).not.toHaveBeenCalled();
});

test("ohne Entwurf gibt es nur den Zeichnen-Knopf", async () => {
  const props = panel({ entwurf: null });

  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Gebiet zeichnen" }));

  expect(props.onZeichnen).toHaveBeenCalled();
});

test("angelegte Gebiete stehen in der Liste", () => {
  panel({
    entwurf: null,
    gebiete: [gebiet({ name: "Sötenich", access_notes: "Waldweg", offline_pinned: true })],
  });

  expect(screen.getByText("Sötenich")).toBeInTheDocument();
  expect(screen.getByText("offline")).toBeInTheDocument();
  expect(screen.getByText("120.0 ha")).toBeInTheDocument();
});

// --- Saisonzustand am Gebiet (AP-Saisonzustand §6) ----------------------

const SAISON = {
  window_end: "2026-08-14",
  precipitation_30d_mm: 41.2,
  precipitation_90d_mm: 120.5,
  precipitation_180d_mm: 268.0,
  precipitation_30d_percent: 62.0,
  precipitation_90d_percent: 55.4,
  precipitation_180d_percent: 71.3,
  soil_moisture_90d: 0.18,
  soil_moisture_90d_percent: 78.9,
  dry_spell_days: 17,
  complete: true,
  missing_days: 0,
  reference_from_year: 1991,
  reference_to_year: 2020,
  source: "era5-archive",
};

test("zeigt den Saisonzustand am Gebiet, mit Bezugszeitraum", () => {
  // §6: in der bestehenden Gebietsansicht, keine neue Seite.
  panel({ entwurf: null, gebiete: [gebiet({ name: "Sötenich", season: SAISON })] });

  const saison = screen.getByLabelText("Saisonzustand");
  expect(saison).toHaveTextContent("62 %");
  expect(saison).toHaveTextContent("55 %");
  expect(saison).toHaveTextContent("71 %");
  expect(saison).toHaveTextContent("79 %");
  expect(saison).toHaveTextContent("17 Tage");
  expect(saison).toHaveTextContent("1991–2020");
});

test("nennt die Zahlen als Modellwerte", () => {
  // ADR 0007: gespeichert werden Modellwerte, keine Messwerte.
  panel({ entwurf: null, gebiete: [gebiet({ season: SAISON })] });

  expect(screen.getByLabelText("Saisonzustand")).toHaveTextContent(/Modellwerte/);
});

test("unvollstaendige Reihe wird gekennzeichnet", () => {
  panel({
    entwurf: null,
    gebiete: [gebiet({ season: { ...SAISON, complete: false, missing_days: 4 } })],
  });

  expect(screen.getByLabelText("Saisonzustand")).toHaveTextContent(/unvollständig/i);
});

test("ohne Saisonzustand bleibt die Gebietszeile unveraendert", () => {
  panel({ entwurf: null, gebiete: [gebiet({ name: "Ohne Backfill" })] });

  expect(screen.getByText("Ohne Backfill")).toBeInTheDocument();
  expect(screen.queryByLabelText("Saisonzustand")).not.toBeInTheDocument();
});
