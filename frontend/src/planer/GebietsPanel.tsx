import { useState, type FormEvent } from "react";

import { ApiFehler, legeGebietAn } from "../shared/api";
import { flaeche } from "../shared/formatierung";
import type { Gebiet, Polygon } from "../shared/typen";
import { SaisonZeile } from "./SaisonZeile";

type Props = {
  gebiete: Gebiet[];
  entwurf: Polygon | null;
  zeichenmodus: boolean;
  onZeichnen: () => void;
  onVerwerfen: () => void;
  onAngelegt: (gebiet: Gebiet) => void;
};

/**
 * Gebietsliste und Anlegen (Spec §12).
 *
 * Gebiete sind der Bezugspunkt des Wetter-Ingests: Ohne Gebiet holt der Job
 * keine Daten, und die Bedingungs-Engine bleibt unerreichbar. Genau deshalb
 * steckt das Anlegen schon in dieser Shell.
 *
 * Die Geometrie entsteht durch Ziehen auf der Karte — ein Rechteck genügt.
 */
export function GebietsPanel({
  gebiete,
  entwurf,
  zeichenmodus,
  onZeichnen,
  onVerwerfen,
  onAngelegt,
}: Props) {
  const [name, setName] = useState("");
  const [notizen, setNotizen] = useState("");
  const [zufahrt, setZufahrt] = useState("");
  const [angeheftet, setAngeheftet] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);

  function zuruecksetzen() {
    setName("");
    setNotizen("");
    setZufahrt("");
    setAngeheftet(false);
    setFehler(null);
  }

  async function absenden(ereignis: FormEvent) {
    ereignis.preventDefault();
    if (!entwurf) return;
    setFehler(null);
    setLaeuft(true);
    try {
      const gebiet = await legeGebietAn({
        name: name.trim(),
        geometry: entwurf,
        notes: notizen.trim() || null,
        access_notes: zufahrt.trim() || null,
        offline_pinned: angeheftet,
      });
      zuruecksetzen();
      onAngelegt(gebiet);
    } catch (problem) {
      // Der Server prüft die Topologie (ST_IsValid) und antwortet bei einem
      // kaputten Polygon mit 422 samt Grund. Das gehört sichtbar gemacht,
      // nicht verschluckt.
      setFehler(problem instanceof ApiFehler ? problem.message : "Anlegen fehlgeschlagen.");
    } finally {
      setLaeuft(false);
    }
  }

  return (
    <div className="gebiete">
      {!entwurf && (
        <button type="button" className="werkzeug" onClick={onZeichnen} disabled={zeichenmodus}>
          {zeichenmodus ? "Rechteck auf der Karte ziehen …" : "Gebiet zeichnen"}
        </button>
      )}

      {entwurf && (
        <form className="formular" onSubmit={absenden} aria-label="Gebiet anlegen">
          <label htmlFor="gebiet-name">Name</label>
          <input
            id="gebiet-name"
            value={name}
            onChange={(ereignis) => setName(ereignis.target.value)}
            required
          />

          <label htmlFor="gebiet-zufahrt">Zufahrt und Parken</label>
          <textarea
            id="gebiet-zufahrt"
            rows={2}
            value={zufahrt}
            onChange={(ereignis) => setZufahrt(ereignis.target.value)}
          />

          <label htmlFor="gebiet-notizen">Notizen</label>
          <textarea
            id="gebiet-notizen"
            rows={2}
            value={notizen}
            onChange={(ereignis) => setNotizen(ereignis.target.value)}
          />

          <label className="ankreuz">
            <input
              type="checkbox"
              checked={angeheftet}
              onChange={(ereignis) => setAngeheftet(ereignis.target.checked)}
            />
            Für Offline vormerken
          </label>

          {fehler && (
            <p className="fehler" role="alert">
              {fehler}
            </p>
          )}

          <div className="knopfreihe">
            <button type="submit" disabled={laeuft || name.trim().length === 0}>
              {laeuft ? "Speichern …" : "Gebiet anlegen"}
            </button>
            <button
              type="button"
              className="sekundaer"
              onClick={() => {
                zuruecksetzen();
                onVerwerfen();
              }}
            >
              Verwerfen
            </button>
          </div>
        </form>
      )}

      {gebiete.length === 0 ? (
        <p className="leer">Noch keine Gebiete angelegt.</p>
      ) : (
        <ul className="liste" aria-label="Gebiete">
          {gebiete.map((gebiet) => (
            <li key={gebiet.id} className="listeneintrag">
              <div className="zeile">
                <span className="art">{gebiet.name}</span>
                {gebiet.offline_pinned && <span className="marke">offline</span>}
              </div>
              <div className="zeile zeile-klein">
                <span>{flaeche(gebiet.area_m2)}</span>
              </div>
              {gebiet.access_notes && <p className="notiz">Zufahrt: {gebiet.access_notes}</p>}
              {gebiet.season && <SaisonZeile saison={gebiet.season} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
