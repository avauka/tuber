import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import type { EignungsMeta, EignungsTreffer } from "../shared/typen";
import { EignungsPanel } from "./EignungsPanel";

const META: EignungsMeta = {
  gewichtssatz_version: 1,
  faktoren: { kalk: 100 },
  faktoren_fehlend: ["wasser", "exposition", "wirtsbaum", "struktur", "klima"],
  rasterweite_m: 20,
  klassengrenzen: [25, 50, 75],
  quellen: [{ name: "IS GK 100 — Lithologische Zusammensetzung", lizenz: "dl-de/by-2-0" }],
  generated_at: "2026-08-13T06:41:49Z",
};

const TREFFER: EignungsTreffer = {
  score: 80,
  klasse: 4,
  stufe: 2,
  teilscores: { kalk: 80 },
};

function panel(ueberschreibungen: Partial<Parameters<typeof EignungsPanel>[0]> = {}) {
  const props = {
    an: true,
    onUmschalten: vi.fn(),
    meta: META,
    fehler: null,
    treffer: null,
    ...ueberschreibungen,
  };
  render(<EignungsPanel {...props} />);
  return props;
}

test("Legende zeigt vier Klassen ohne Verlauf", () => {
  // Spec §6: diskrete Klassen. Ein glatter Verlauf suggeriert eine
  // Trennschärfe, die abgeleitete Daten nicht hergeben.
  panel();

  const legende = screen.getByLabelText("Legende der Eignungsklassen");
  expect(legende.querySelectorAll("li")).toHaveLength(4);
  expect(screen.getByText("sehr gut")).toBeInTheDocument();
  expect(screen.getByText("gering")).toBeInTheDocument();
});

test("sagt deutlich, dass der Score auf einem einzigen Faktor beruht", () => {
  // AP17a §6: Eine Karte, die nach sechs Faktoren aussieht, aber einen
  // zeigt, wäre die schlimmste Variante.
  panel();

  expect(screen.getByText(/einem einzigen Faktor/)).toBeInTheDocument();
  expect(screen.getByText(/Kalk \/ pH trägt 100 %/)).toBeInTheDocument();
  expect(screen.getByText(/Wasserhaushalt/)).toBeInTheDocument();
});

test("nennt Eignung und nie Wahrscheinlichkeit", () => {
  // Invariante 9, nicht verhandelbar.
  const { container } = render(
    <EignungsPanel an onUmschalten={vi.fn()} meta={META} fehler={null} treffer={TREFFER} />,
  );

  const text = container.textContent ?? "";
  expect(text).toMatch(/Eignung/);
  // Das Wort darf genau einmal vorkommen: in der Absage. Spec §13 verlangt
  // diesen Satz ausdrücklich — was verboten ist, ist die Behauptung.
  expect(text).toMatch(/keine Fundwahrscheinlichkeit/);
  expect(text.replace("keine Fundwahrscheinlichkeit", "")).not.toMatch(/wahrscheinlich/i);
});

test("Antippen schlüsselt Score, Teilfaktor und Datenstufe auf", () => {
  // Invariante 10: Jeder Score bleibt aufschlüsselbar.
  panel({ treffer: TREFFER });

  const liste = screen.getByLabelText("Aufschlüsselung");
  expect(liste).toHaveTextContent("80 von 100 — sehr gut");
  expect(liste).toHaveTextContent("Kalk / pH");
  expect(liste).toHaveTextContent("Geologische Karte 1:100.000 und Bodenkarte 1:50.000");
});

test("Umschalten meldet sich nach oben", async () => {
  const props = panel({ an: false });

  await userEvent.click(screen.getByLabelText("Eignung anzeigen"));

  expect(props.onUmschalten).toHaveBeenCalledWith(true);
});

test("ohne Karte bleibt der Schalter aus und der Grund steht da", () => {
  panel({
    meta: null,
    an: false,
    fehler: "Keine Metadaten unter /data/suitability.meta.json.",
  });

  expect(screen.getByLabelText("Eignung anzeigen")).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("Keine Metadaten");
  expect(screen.queryByLabelText("Legende der Eignungsklassen")).not.toBeInTheDocument();
});

test("nennt Gewichtssatz, Rasterweite und Quelle", () => {
  panel();

  expect(screen.getByText(/Gewichtssatz 1/)).toBeInTheDocument();
  expect(screen.getByText(/20 m/)).toBeInTheDocument();
  expect(screen.getByText(/IS GK 100/)).toBeInTheDocument();
});
