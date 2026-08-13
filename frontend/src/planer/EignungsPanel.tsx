import { KLASSEN, faktortext, klassentext, stufentext } from "../map/eignung";
import type { EignungsMeta, EignungsTreffer } from "../shared/typen";

type Props = {
  an: boolean;
  onUmschalten: (an: boolean) => void;
  meta: EignungsMeta | null;
  fehler: string | null;
  treffer: EignungsTreffer | null;
};

/**
 * Eignungskarte zuschalten, Legende, Aufschlüsselung (ADR 0008, Spec §6).
 *
 * Zwei Dinge sind hier nicht verhandelbar:
 *
 * * **Invariante 9.** Es heisst „Eignung", nie „Wahrscheinlichkeit".
 *   Trüffelvorkommen sind auch im perfekten Habitat fleckig (Spec §13.1);
 *   eine Karte, die Fundwahrscheinlichkeit verspricht, lügt.
 * * **Der Hinweis, worauf der Score beruht.** Solange nur der Kalkfaktor
 *   enthalten ist, trägt er 100 % — eine Karte, die nach sechs Faktoren
 *   aussieht, aber einen zeigt, wäre die schlimmste Variante (AP17a §6).
 */
export function EignungsPanel({ an, onUmschalten, meta, fehler, treffer }: Props) {
  const faktoren = meta ? Object.entries(meta.faktoren) : [];
  const nurEiner = faktoren.length === 1;

  return (
    <div className="eignung">
      <label className="ankreuz">
        <input
          type="checkbox"
          checked={an}
          onChange={(ereignis) => onUmschalten(ereignis.target.checked)}
          disabled={meta === null}
        />
        Eignung anzeigen
      </label>

      {fehler && (
        <p className="hinweis-text" role="status">
          {fehler}
        </p>
      )}

      {meta && (
        <>
          <ul className="legende" aria-label="Legende der Eignungsklassen">
            {KLASSEN.map(({ klasse, text, farbe, von, bis }) => (
              <li key={klasse}>
                <span className="farbfeld" style={{ background: farbe }} aria-hidden="true" />
                {text} <span className="zeile-klein">({von}–{bis})</span>
              </li>
            ))}
          </ul>

          <p className="hinweis-text">
            {nurEiner ? (
              <>
                <strong>Der Score beruht derzeit auf einem einzigen Faktor.</strong>{" "}
                {faktoren.map(([name, anteil]) => `${faktortext(name)} trägt ${anteil} %`).join(", ")}
                . Die übrigen Faktoren ({meta.faktoren_fehlend.map(faktortext).join(", ")}) fehlen
                noch; ihr Gewicht ist proportional umgelegt.
              </>
            ) : (
              <>
                Enthalten:{" "}
                {faktoren.map(([name, anteil]) => `${faktortext(name)} ${anteil} %`).join(", ")}.
              </>
            )}{" "}
            Die Karte zeigt Habitat-Eignung, keine Fundwahrscheinlichkeit — und der pH-Wert ist aus
            Geologie und Bodentyp abgeleitet, nicht gemessen.
          </p>

          {treffer && (
            <dl className="aufschluesselung" aria-label="Aufschlüsselung">
              <dt>Eignung</dt>
              <dd>
                {treffer.score} von 100 — {klassentext(treffer.klasse)}
              </dd>
              {Object.entries(treffer.teilscores).map(([name, wert]) => (
                <div key={name} className="teilscore">
                  <dt>{faktortext(name)}</dt>
                  <dd>{wert}</dd>
                </div>
              ))}
              <dt>Datenlage</dt>
              <dd>{stufentext(treffer.stufe)}</dd>
            </dl>
          )}

          {an && !treffer && <p className="zeile-klein">Fläche antippen für die Aufschlüsselung.</p>}

          <p className="zeile-klein">
            Gewichtssatz {meta.gewichtssatz_version}, Raster {meta.rasterweite_m ?? "?"} m ·{" "}
            {meta.quellen.map((quelle) => quelle.name ?? "").filter(Boolean).join(" · ")}
          </p>
        </>
      )}
    </div>
  );
}
