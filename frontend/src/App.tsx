import { useCallback, useEffect, useState } from "react";

import { PlanerShell } from "./planer/PlanerShell";
import { Login } from "./shared/Login";
import { NichtAngemeldet, ladeGebiete, setAbmeldungsHandler } from "./shared/api";

type Zustand = "pruefen" | "angemeldet" | "abgemeldet";

/**
 * Hält den Anmeldezustand — mehr Routing braucht die Shell in AP10b nicht.
 *
 * Geprüft wird mit einem echten API-Aufruf statt mit einem Blick ins
 * Cookie: Das Sitzungs-Cookie ist httpOnly und für JavaScript unsichtbar.
 * Ob es noch gilt, weiss allein der Server.
 */
export function App() {
  const [zustand, setZustand] = useState<Zustand>("pruefen");

  const abgemeldet = useCallback(() => setZustand("abgemeldet"), []);

  useEffect(() => {
    // Jede 401 aus irgendeinem Aufruf führt zurück zur Anmeldung — auch
    // mitten in der Sitzung, wenn das 90-Tage-Cookie abgelaufen ist.
    setAbmeldungsHandler(abgemeldet);
    return () => setAbmeldungsHandler(null);
  }, [abgemeldet]);

  useEffect(() => {
    if (zustand !== "pruefen") return;
    let abgebrochen = false;

    ladeGebiete()
      .then(() => {
        if (!abgebrochen) setZustand("angemeldet");
      })
      .catch((problem: unknown) => {
        if (abgebrochen) return;
        // Alles ausser 401 ist ein Serverproblem; die Shell zeigt dann
        // trotzdem die Anmeldung, statt leer dazustehen.
        if (!(problem instanceof NichtAngemeldet)) setZustand("abgemeldet");
      });

    return () => {
      abgebrochen = true;
    };
  }, [zustand]);

  if (zustand === "pruefen") {
    return <main className="laden">Lade …</main>;
  }
  if (zustand === "abgemeldet") {
    return <Login onAngemeldet={() => setZustand("pruefen")} />;
  }
  return <PlanerShell onAbgemeldet={abgemeldet} />;
}
