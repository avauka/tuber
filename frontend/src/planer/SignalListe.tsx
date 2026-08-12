import { datumZeit, signalname } from "../shared/formatierung";
import type { Signal } from "../shared/typen";

type Props = {
  signale: Signal[];
};

/** Signale ohne Fund (Spec §4) — eigene Ebene, eigene Liste. */
export function SignalListe({ signale }: Props) {
  if (signale.length === 0) {
    return <p className="leer">Noch keine Signale erfasst.</p>;
  }

  return (
    <ul className="liste" aria-label="Signale">
      {signale.map((signal) => (
        <li key={signal.id} className="listeneintrag">
          <div className="zeile">
            <span className="art">{signalname(signal.signal_type)}</span>
          </div>
          <div className="zeile zeile-klein">
            <span>{datumZeit(signal.observed_at)}</span>
            {signal.dog_confidence && <span>Hund: {signal.dog_confidence}</span>}
          </div>
          {signal.notes && <p className="notiz">{signal.notes}</p>}
        </li>
      ))}
    </ul>
  );
}
