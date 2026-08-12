/** Anzeige-Hilfen. Lokalzeit ist reine Darstellung, gespeichert wird UTC. */

const DATUM = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const DATUM_ZEIT = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function datum(iso: string | null): string {
  if (!iso) return "ohne Datum";
  return DATUM.format(new Date(iso));
}

export function datumZeit(iso: string | null): string {
  if (!iso) return "ohne Zeitpunkt";
  return DATUM_ZEIT.format(new Date(iso));
}

/**
 * Artname für die Anzeige. `tuber_spec` ist der Feld-Default (Invariante 6)
 * und heisst deshalb ausdrücklich "unbestimmt" und nicht etwa nichts.
 */
const ARTNAMEN: Record<string, string> = {
  t_aestivum: "T. aestivum",
  t_macrosporum: "T. macrosporum",
  t_mesentericum: "T. mesentericum",
  t_borchii: "T. borchii",
  t_brumale: "T. brumale",
  t_rufum: "T. rufum",
  t_excavatum: "T. excavatum",
  t_melanosporum: "T. melanosporum",
  tuber_spec: "Tuber spec. (unbestimmt)",
  andere_hypogaee: "andere Hypogäe",
};

export function artname(wert: string): string {
  return ARTNAMEN[wert] ?? wert;
}

const SIGNALNAMEN: Record<string, string> = {
  hund_anzeige_ohne_fund: "Hund zeigt an, kein Fund",
  truffelfliege: "Trüffelfliege",
  brule_erkannt: "Brûlé erkannt",
  habitat_auffaellig: "Habitat auffällig",
  wirtsbaum_bestand: "Wirtsbaum-Bestand",
};

export function signalname(wert: string): string {
  return SIGNALNAMEN[wert] ?? wert;
}

/** Genauigkeit bleibt sichtbar (Invariante 1/2) — auch im Planer. */
export function genauigkeit(meter: number): string {
  return `± ${meter < 10 ? meter.toFixed(1) : Math.round(meter)} m`;
}

export function flaeche(quadratmeter: number): string {
  const hektar = quadratmeter / 10_000;
  if (hektar >= 1) return `${hektar.toFixed(1)} ha`;
  return `${Math.round(quadratmeter)} m²`;
}
