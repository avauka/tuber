"""Cron-Ziel: loest den Dump im API-Service aus (ADR 0004, AP15.1).

Aufruf:  python -m app.jobs.trigger_backup

Railway kennt keine geteilten Volumes. Das Volume haengt am API-Service, also
muss der Dump dort geschrieben werden — dieser Job ruft ihn nur per HTTP an
und braucht deshalb weder DATABASE_URL noch ein eigenes Volume.
"""

import os
import sys
from collections.abc import Sequence

import httpx

from app.core.auth import BACKUP_TRIGGER_PATH

# pg_dump laeuft synchron im Request. Bei einer Single-User-Datenbank sind das
# Sekunden, aber die Grenze soll nicht der begrenzende Faktor sein.
REQUEST_TIMEOUT_S = 900.0


def _env(name: str) -> str:
    wert = os.environ.get(name, "").strip()
    if not wert:
        raise RuntimeError(f"{name} ist nicht gesetzt.")
    return wert


def trigger() -> dict:
    basis = _env("BASE_URL").rstrip("/")
    token = _env("BACKUP_TRIGGER_TOKEN")

    antwort = httpx.post(
        f"{basis}{BACKUP_TRIGGER_PATH}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=REQUEST_TIMEOUT_S,
    )
    antwort.raise_for_status()
    result: dict = antwort.json()
    return result


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # Keine Argumente; Konfiguration kommt aus der ENV.
    try:
        eintrag = trigger()
    except Exception as exc:  # noqa: BLE001 — der Cron braucht einen Exit-Code, keinen Traceback
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1

    print(f"Backup ausgeloest: {eintrag['name']} ({eintrag['size_bytes']} Bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
