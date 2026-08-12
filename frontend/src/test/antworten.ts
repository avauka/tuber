import { vi } from "vitest";

import type { Fund, Gebiet, Signal } from "../shared/typen";

/**
 * `fetch` durch eine Tabelle Pfad -> Antwort ersetzen.
 *
 * Kein Netz im Testlauf, und der Aufrufzähler bleibt prüfbar: Die Tests
 * schauen nach, was tatsächlich geschickt wurde — bei POST /api/areas etwa,
 * ob die Geometrie ein geschlossener Ring ist.
 */
export type Antwort = { status?: number; koerper?: unknown };

export function fetchAttrappe(tabelle: Record<string, Antwort | Antwort[]>) {
  const offen = new Map<string, Antwort[]>(
    Object.entries(tabelle).map(([pfad, wert]) => [pfad, Array.isArray(wert) ? [...wert] : [wert]]),
  );

  const attrappe = vi.fn(async (eingabe: RequestInfo | URL, init?: RequestInit) => {
    const pfad = typeof eingabe === "string" ? eingabe : String(eingabe);
    const schlange = offen.get(pfad);
    const antwort = schlange && (schlange.length > 1 ? schlange.shift() : schlange[0]);
    if (!antwort) {
      throw new Error(`Kein Testfall fuer ${init?.method ?? "GET"} ${pfad}`);
    }
    const status = antwort.status ?? 200;
    return new Response(JSON.stringify(antwort.koerper ?? null), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });

  vi.stubGlobal("fetch", attrappe);
  return attrappe;
}

export function fund(teil: Partial<Fund> = {}): Fund {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    client_uuid: "22222222-2222-4222-8222-222222222222",
    lat: 50.55,
    lon: 6.55,
    gps_accuracy_m: 6.4,
    found_at: "2026-08-10T09:15:00Z",
    session_id: null,
    species_guess: "tuber_spec",
    species_confidence: "unbestimmt",
    phenotype: "unbestimmt",
    id_pending: true,
    maturity: "unbestimmt",
    calcium_reaction: "ungetestet",
    revisit_due: "2027-07-20",
    notes: null,
    created_at: "2026-08-10T09:15:00Z",
    ...teil,
  };
}

export function signal(teil: Partial<Signal> = {}): Signal {
  return {
    id: "33333333-3333-4333-8333-333333333333",
    client_uuid: "44444444-4444-4444-8444-444444444444",
    lat: 50.56,
    lon: 6.56,
    signal_type: "truffelfliege",
    observed_at: "2026-08-09T14:00:00Z",
    dog_confidence: null,
    session_id: null,
    notes: null,
    ...teil,
  };
}

export function gebiet(teil: Partial<Gebiet> = {}): Gebiet {
  return {
    id: "55555555-5555-4555-8555-555555555555",
    name: "Sötenich",
    geometry: {
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
    },
    notes: null,
    access_notes: null,
    last_visited: null,
    offline_pinned: false,
    area_m2: 1_200_000,
    ...teil,
  };
}
