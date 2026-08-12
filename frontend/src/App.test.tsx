import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { App } from "./App";
import { fetchAttrappe, fund } from "./test/antworten";

// MapLibre braucht WebGL — in jsdom gibt es keins. Die Karte ist hier
// nicht der Prüfgegenstand; sie wird im Browser verifiziert.
vi.mock("./map/Karte", () => ({
  Karte: () => <div data-testid="karte" />,
}));

const META = {
  build_date: "20260812",
  osm_data_timestamp: "2026-08-12T04:00:00Z",
  tileset_version: "4.15.2",
  bbox: [5.4, 49.7, 7.2, 51.1],
  maxzoom: 14,
  bytes: 208196018,
  sha256: "a".repeat(64),
  fetched_at: "2026-08-12T12:17:59Z",
};

describe("Anmeldung", () => {
  test("401 beim Start führt zur Login-Ansicht", async () => {
    fetchAttrappe({
      "/api/areas": { status: 401, koerper: { detail: "Nicht angemeldet." } },
    });

    render(<App />);

    expect(await screen.findByLabelText("Passwort")).toBeInTheDocument();
  });

  test("falsches Passwort bleibt in der Login-Ansicht und sagt es", async () => {
    fetchAttrappe({
      "/api/areas": { status: 401 },
      "/api/auth/login": { status: 401, koerper: { detail: "Passwort falsch." } },
    });

    render(<App />);
    await userEvent.type(await screen.findByLabelText("Passwort"), "daneben");
    await userEvent.click(screen.getByRole("button", { name: "Anmelden" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Passwort falsch");
    expect(screen.getByLabelText("Passwort")).toBeInTheDocument();
  });

  test("nach erfolgreicher Anmeldung erscheint der Planer", async () => {
    fetchAttrappe({
      "/api/areas": [{ status: 401 }, { koerper: [] }],
      "/api/auth/login": { koerper: { status: "angemeldet" } },
      "/api/finds": { koerper: [fund()] },
      "/api/signals": { koerper: [] },
      "/api/basemap/meta": { koerper: META },
    });

    render(<App />);
    await userEvent.type(await screen.findByLabelText("Passwort"), "feldgang-2026");
    await userEvent.click(screen.getByRole("button", { name: "Anmelden" }));

    expect(await screen.findByText("Planer")).toBeInTheDocument();
    expect(screen.getByTestId("karte")).toBeInTheDocument();
  });

  test("401 mitten in der Sitzung wirft zurück zur Anmeldung", async () => {
    // Das 90-Tage-Cookie läuft irgendwann ab — dann darf nicht die halbe
    // Oberfläche stehenbleiben (ADR 0005).
    fetchAttrappe({
      "/api/areas": { koerper: [] },
      "/api/finds": { status: 401, koerper: { detail: "Sitzung abgelaufen." } },
      "/api/signals": { koerper: [] },
      "/api/basemap/meta": { koerper: META },
    });

    render(<App />);

    await waitFor(() => expect(screen.getByLabelText("Passwort")).toBeInTheDocument());
  });

  test("Abmelden führt zurück zur Login-Ansicht", async () => {
    fetchAttrappe({
      "/api/areas": { koerper: [] },
      "/api/finds": { koerper: [] },
      "/api/signals": { koerper: [] },
      "/api/basemap/meta": { koerper: META },
      "/api/auth/logout": { koerper: { status: "abgemeldet" } },
    });

    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Abmelden" }));

    expect(await screen.findByLabelText("Passwort")).toBeInTheDocument();
  });
});

describe("Attribution", () => {
  test("steht dauerhaft mit Datenstand in der Oberfläche", async () => {
    // Spec §15: Pflicht, sichtbar, nicht in einem Menü.
    fetchAttrappe({
      "/api/areas": { koerper: [] },
      "/api/finds": { koerper: [] },
      "/api/signals": { koerper: [] },
      "/api/basemap/meta": { koerper: META },
    });

    render(<App />);

    const zeile = await screen.findByText(/OpenStreetMap/);
    expect(zeile.closest(".attribution")).toHaveTextContent("Protomaps");
    expect(await screen.findByText(/Datenstand 12\.8\.2026/)).toBeInTheDocument();
  });

  test("fehlende Basiskarte wird benannt statt verschwiegen", async () => {
    fetchAttrappe({
      "/api/areas": { koerper: [] },
      "/api/finds": { koerper: [] },
      "/api/signals": { koerper: [] },
      "/api/basemap/meta": {
        status: 503,
        koerper: { detail: "Keine Metadaten unter /data/basemap.meta.json." },
      },
    });

    render(<App />);

    expect(await screen.findByRole("status")).toHaveTextContent("Keine Metadaten");
  });
});
