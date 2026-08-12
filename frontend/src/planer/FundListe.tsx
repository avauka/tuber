import { artname, datumZeit, genauigkeit } from "../shared/formatierung";
import type { Fund } from "../shared/typen";

type Props = {
  funde: Fund[];
};

/**
 * Fundhistorie, neueste zuerst (Reihenfolge kommt vom Server).
 *
 * Ohne Filter: Indikatorarten wie *T. rufum* und *T. excavatum* haben keinen
 * Speisewert, sagen aber viel über das Habitat — sie werden hier nie
 * ausgeblendet, auch nicht durch einen voreingestellten Filter
 * (Invariante 8).
 *
 * Bearbeiten geht hier nicht: `PATCH /api/finds/{id}` gibt es noch nicht.
 */
export function FundListe({ funde }: Props) {
  if (funde.length === 0) {
    return <p className="leer">Noch keine Funde erfasst.</p>;
  }

  return (
    <ul className="liste" aria-label="Funde">
      {funde.map((fund) => (
        <li key={fund.id} className="listeneintrag">
          <div className="zeile">
            <span className="art">{artname(fund.species_guess)}</span>
            {fund.id_pending && (
              <span className="marke marke-offen" title="Bestimmung offen">
                Bestimmung offen
              </span>
            )}
          </div>
          <div className="zeile zeile-klein">
            <span>{datumZeit(fund.found_at)}</span>
            {/* Genauigkeit bleibt sichtbar (Invariante 1/2). */}
            <span className="genauigkeit">{genauigkeit(fund.gps_accuracy_m)}</span>
          </div>
          {fund.notes && <p className="notiz">{fund.notes}</p>}
        </li>
      ))}
    </ul>
  );
}
