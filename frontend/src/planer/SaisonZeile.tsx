import type { Saisonzustand } from "../shared/typen";

type Props = {
  saison: Saisonzustand;
};

/**
 * Saisonzustand eines Gebiets (AP-Saisonzustand §6).
 *
 * Steht bewusst **in** der Gebietszeile und nicht auf einer eigenen Seite:
 * Die Frage „ist dieses Jahr eins" gehört neben das Gebiet, für das sie
 * gilt.
 *
 * Zwei Dinge, die an den Zahlen hängen müssen, sonst sind sie nicht
 * lesbar:
 *
 * * **Der Bezugszeitraum.** „62 %" ohne „vom Mittel 1991–2020" ist keine
 *   Aussage.
 * * **Die Herkunft.** ERA5 liefert Modellwerte, keine Messwerte (ADR 0007).
 *
 * Keine Gesamtnote — die Kennzahlen stehen einzeln (Invariante 10). Auch
 * keine Ampelfarbe: Ohne Funddaten wäre jede Schwelle erfunden.
 */
export function SaisonZeile({ saison }: Props) {
  const prozent = (wert: number | null) => (wert === null ? "—" : `${Math.round(wert)} %`);

  return (
    <dl className="saison" aria-label="Saisonzustand">
      <div className="saison-wert">
        <dt>Regen 30 Tage</dt>
        <dd>{prozent(saison.precipitation_30d_percent)}</dd>
      </div>
      <div className="saison-wert">
        <dt>90 Tage</dt>
        <dd>{prozent(saison.precipitation_90d_percent)}</dd>
      </div>
      <div className="saison-wert">
        <dt>180 Tage</dt>
        <dd>{prozent(saison.precipitation_180d_percent)}</dd>
      </div>
      <div className="saison-wert">
        <dt>Bodenfeuchte 90 Tage</dt>
        <dd>{prozent(saison.soil_moisture_90d_percent)}</dd>
      </div>
      <div className="saison-wert">
        <dt>längste Trockenphase</dt>
        <dd>{saison.dry_spell_days === null ? "—" : `${saison.dry_spell_days} Tage`}</dd>
      </div>
      <p className="zeile-klein saison-fuss">
        Anteil am Mittel 1991–2020, Stand{" "}
        {new Date(saison.window_end).toLocaleDateString("de-DE")}. Modellwerte aus dem
        ERA5-Archiv, keine Messwerte.
        {!saison.complete && (
          <> Die Reihe ist unvollständig: {saison.missing_days} Tage fehlen.</>
        )}
      </p>
    </dl>
  );
}
