import { useState, type FormEvent } from "react";

import { ApiFehler, NichtAngemeldet, anmelden } from "./api";

type Props = {
  onAngemeldet: () => void;
};

/**
 * Ein Passwortfeld, mehr nicht (ADR 0005: ein Nutzer, ein Passwort).
 *
 * Das Ergebnis landet im httpOnly-Cookie, das der Browser hält — hier wird
 * nichts gespeichert, weder im State noch im LocalStorage.
 */
export function Login({ onAngemeldet }: Props) {
  const [passwort, setPasswort] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);

  async function absenden(ereignis: FormEvent) {
    ereignis.preventDefault();
    setFehler(null);
    setLaeuft(true);
    try {
      await anmelden(passwort);
      setPasswort("");
      onAngemeldet();
    } catch (problem) {
      if (problem instanceof NichtAngemeldet) {
        setFehler("Passwort falsch.");
      } else if (problem instanceof ApiFehler && problem.status === 429) {
        // Der Server zaehlt Fehlversuche und nennt die Wartezeit selbst.
        setFehler(problem.message);
      } else {
        setFehler("Anmeldung nicht möglich. Ist der Dienst erreichbar?");
      }
    } finally {
      setLaeuft(false);
    }
  }

  return (
    <main className="login">
      <form className="login-karte" onSubmit={absenden}>
        <h1>TUBER</h1>
        <p className="unterzeile">Trüffel-Habitatkartierung</p>

        <label htmlFor="passwort">Passwort</label>
        <input
          id="passwort"
          type="password"
          autoComplete="current-password"
          value={passwort}
          onChange={(ereignis) => setPasswort(ereignis.target.value)}
          autoFocus
        />

        {fehler && (
          <p className="fehler" role="alert">
            {fehler}
          </p>
        )}

        <button type="submit" disabled={laeuft || passwort.length === 0}>
          {laeuft ? "Anmelden …" : "Anmelden"}
        </button>
      </form>
    </main>
  );
}
