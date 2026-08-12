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
