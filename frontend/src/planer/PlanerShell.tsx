import { useCallback, useEffect, useState } from "react";

import { Karte } from "../map/Karte";
import {
  abmelden,
  ladeBasiskartenMeta,
  ladeFunde,
  ladeGebiete,
  ladeSignale,
} from "../shared/api";
import type { BasiskartenMeta, Fund, Gebiet, Polygon, Signal } from "../shared/typen";
import { Attribution } from "./Attribution";
import { FundListe } from "./FundListe";
import { GebietsPanel } from "./GebietsPanel";
import { SignalListe } from "./SignalListe";

type Props = {
  onAbgemeldet: () => void;
};

type Reiter = "funde" | "signale" | "gebiete";

/**
 * Planer-Modus (Spec §7): grosse Karte, daneben Listen und die
 * Gebietsverwaltung. Der Feldmodus ist ein eigenes Paket.
 */
export function PlanerShell({ onAbgemeldet }: Props) {
  const [funde, setFunde] = useState<Fund[]>([]);
  const [signale, setSignale] = useState<Signal[]>([]);
  const [gebiete, setGebiete] = useState<Gebiet[]>([]);
  const [meta, setMeta] = useState<BasiskartenMeta | null>(null);
  const [kartenfehler, setKartenfehler] = useState<string | null>(null);
  const [reiter, setReiter] = useState<Reiter>("funde");
  const [zeichenmodus, setZeichenmodus] = useState(false);
  const [entwurf, setEntwurf] = useState<Polygon | null>(null);

  useEffect(() => {
    // Jeder Aufruf für sich: Ein fehlender Datenstand darf nicht die
    // Fundliste verhindern. Eine 401 führt über den zentralen Handler
    // zurück zur Anmeldung.
    void ladeFunde().then(setFunde).catch(ignoriere);
    void ladeSignale().then(setSignale).catch(ignoriere);
    void ladeGebiete().then(setGebiete).catch(ignoriere);
    void ladeBasiskartenMeta()
      .then(setMeta)
      .catch((problem: unknown) => {
        // 503: Der Extract-Job ist noch nicht gelaufen. Die Karte bleibt
        // dann leer — das gehört gesagt, nicht stillschweigend hingenommen.
        setKartenfehler(problem instanceof Error ? problem.message : "Basiskarte nicht verfügbar.");
      });
  }, []);

  const rechteckFertig = useCallback((geometrie: Polygon) => {
    setEntwurf(geometrie);
    setZeichenmodus(false);
    setReiter("gebiete");
  }, []);

  async function abmeldenUndZurueck() {
    try {
      await abmelden();
    } finally {
      onAbgemeldet();
    }
  }

  return (
    <div className="planer">
      <header className="kopf">
        <h1>TUBER</h1>
        <span className="modus">Planer</span>
        <button type="button" className="sekundaer" onClick={abmeldenUndZurueck}>
          Abmelden
        </button>
      </header>

      <aside className="seitenleiste">
        <nav className="reiter">
          <button
            type="button"
            className={reiter === "funde" ? "aktiv" : ""}
            onClick={() => setReiter("funde")}
          >
            Funde ({funde.length})
          </button>
          <button
            type="button"
            className={reiter === "signale" ? "aktiv" : ""}
            onClick={() => setReiter("signale")}
          >
            Signale ({signale.length})
          </button>
          <button
            type="button"
            className={reiter === "gebiete" ? "aktiv" : ""}
            onClick={() => setReiter("gebiete")}
          >
            Gebiete ({gebiete.length})
          </button>
        </nav>

        <div className="inhalt">
          {reiter === "funde" && <FundListe funde={funde} />}
          {reiter === "signale" && <SignalListe signale={signale} />}
          {reiter === "gebiete" && (
            <GebietsPanel
              gebiete={gebiete}
              entwurf={entwurf}
              zeichenmodus={zeichenmodus}
              onZeichnen={() => setZeichenmodus(true)}
              onVerwerfen={() => setEntwurf(null)}
              onAngelegt={(gebiet) => {
                setGebiete((bisher) => [...bisher, gebiet].sort(nachName));
                setEntwurf(null);
              }}
            />
          )}
        </div>
      </aside>

      <section className="kartenbereich">
        {kartenfehler && (
          <p className="hinweis" role="status">
            {kartenfehler}
          </p>
        )}
        <Karte
          funde={funde}
          signale={signale}
          gebiete={gebiete}
          meta={meta}
          zeichenmodus={zeichenmodus}
          entwurf={entwurf}
          onRechteck={rechteckFertig}
        />
        <Attribution meta={meta} />
      </section>
    </div>
  );
}

function nachName(a: Gebiet, b: Gebiet): number {
  return a.name.localeCompare(b.name, "de");
}

/** 401 hat der zentrale Handler schon behandelt; alles andere bleibt leer. */
function ignoriere(): void {}
