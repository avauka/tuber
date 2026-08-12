import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";

import { fund } from "../test/antworten";
import { FundListe } from "./FundListe";

test("zeigt Datum, Art, offene Bestimmung und Genauigkeit", () => {
  render(
    <FundListe
      funde={[fund({ species_guess: "t_aestivum", id_pending: false, gps_accuracy_m: 12.7 })]}
    />,
  );

  const eintrag = within(screen.getByRole("listitem"));
  expect(eintrag.getByText("T. aestivum")).toBeInTheDocument();
  expect(eintrag.getByText("± 13 m")).toBeInTheDocument();
  expect(eintrag.getByText(/10\.08\.2026/)).toBeInTheDocument();
  expect(eintrag.queryByText("Bestimmung offen")).not.toBeInTheDocument();
});

test("offene Bestimmung ist gekennzeichnet", () => {
  render(<FundListe funde={[fund({ id_pending: true })]} />);

  expect(screen.getByText("Bestimmung offen")).toBeInTheDocument();
  expect(screen.getByText("Tuber spec. (unbestimmt)")).toBeInTheDocument();
});

test("Indikatorarten stehen in der Liste", () => {
  // Invariante 8: t_rufum und t_excavatum haben keinen Speisewert, sagen
  // aber viel über das Habitat. Kein Filter blendet sie aus — auch kein
  // voreingestellter.
  render(
    <FundListe
      funde={[
        fund({ id: "a", species_guess: "t_rufum" }),
        fund({ id: "b", species_guess: "t_excavatum" }),
        fund({ id: "c", species_guess: "t_aestivum" }),
      ]}
    />,
  );

  expect(screen.getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getByText("T. rufum")).toBeInTheDocument();
  expect(screen.getByText("T. excavatum")).toBeInTheDocument();
});

test("Reihenfolge kommt vom Server und wird nicht umsortiert", () => {
  const eintraege = [
    fund({ id: "neu", found_at: "2026-08-10T09:00:00Z", notes: "neuer" }),
    fund({ id: "alt", found_at: "2026-07-01T09:00:00Z", notes: "älterer" }),
  ];

  render(<FundListe funde={eintraege} />);

  const texte = screen.getAllByRole("listitem").map((eintrag) => eintrag.textContent);
  expect(texte[0]).toContain("neuer");
  expect(texte[1]).toContain("älterer");
});

test("leere Liste sagt es", () => {
  render(<FundListe funde={[]} />);
  expect(screen.getByText("Noch keine Funde erfasst.")).toBeInTheDocument();
});
