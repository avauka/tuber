/**
 * Zugriff auf die API (ADR 0005).
 *
 * Die Sitzung steckt ausschliesslich im httpOnly-Cookie. Es gibt hier
 * bewusst keinen Token, kein LocalStorage und keinen Header — was
 * JavaScript nicht lesen kann, kann ein XSS auch nicht mitnehmen.
 *
 * Jede 401 laeuft ueber `setAbmeldungsHandler` zurueck an die App, die
 * daraufhin die Login-Ansicht zeigt. Das gilt auch mitten in der Sitzung:
 * Das Cookie haelt 90 Tage, aber irgendwann laeuft es ab, und dann darf
 * nicht die halbe Oberflaeche stehenbleiben.
 */
import type { BasiskartenMeta, Fund, Gebiet, GebietEntwurf, Signal } from "./typen";

export class NichtAngemeldet extends Error {
  constructor() {
    super("Nicht angemeldet oder Sitzung abgelaufen.");
    this.name = "NichtAngemeldet";
  }
}

export class ApiFehler extends Error {
  readonly status: number;

  constructor(status: number, meldung: string) {
    super(meldung);
    this.name = "ApiFehler";
    this.status = status;
  }
}

let beiAbmeldung: (() => void) | null = null;

export function setAbmeldungsHandler(handler: (() => void) | null): void {
  beiAbmeldung = handler;
}

async function fehlertext(antwort: Response): Promise<string> {
  try {
    const koerper: unknown = await antwort.json();
    if (koerper && typeof koerper === "object" && "detail" in koerper) {
      const detail = (koerper as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      return JSON.stringify(detail);
    }
  } catch {
    // Kein JSON-Koerper — dann bleibt der Statustext.
  }
  return `${antwort.status} ${antwort.statusText}`;
}

async function anfrage<T>(pfad: string, init?: RequestInit): Promise<T> {
  const antwort = await fetch(pfad, {
    // Gleiche Origin, deshalb geht das Sitzungs-Cookie mit.
    credentials: "same-origin",
    ...(init?.body ? { headers: { "Content-Type": "application/json" } } : {}),
    ...init,
  });

  if (antwort.status === 401) {
    beiAbmeldung?.();
    throw new NichtAngemeldet();
  }
  if (!antwort.ok) {
    throw new ApiFehler(antwort.status, await fehlertext(antwort));
  }
  if (antwort.status === 204) {
    return undefined as T;
  }
  return (await antwort.json()) as T;
}

export async function anmelden(passwort: string): Promise<void> {
  await anfrage("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ password: passwort }),
  });
}

export async function abmelden(): Promise<void> {
  await anfrage("/api/auth/logout", { method: "POST" });
}

export function ladeFunde(): Promise<Fund[]> {
  return anfrage<Fund[]>("/api/finds");
}

export function ladeSignale(): Promise<Signal[]> {
  return anfrage<Signal[]>("/api/signals");
}

export function ladeGebiete(): Promise<Gebiet[]> {
  return anfrage<Gebiet[]>("/api/areas");
}

export function legeGebietAn(entwurf: GebietEntwurf): Promise<Gebiet> {
  return anfrage<Gebiet>("/api/areas", {
    method: "POST",
    body: JSON.stringify(entwurf),
  });
}

export function ladeBasiskartenMeta(): Promise<BasiskartenMeta> {
  return anfrage<BasiskartenMeta>("/api/basemap/meta");
}
