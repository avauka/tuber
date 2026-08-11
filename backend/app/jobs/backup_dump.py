"""Verschluesselter Datenbank-Dump (ADR 0004, AP15).

Aufruf:  python -m app.jobs.backup_dump

pg_dump -Fc schreibt in eine Pipe, gpg verschluesselt daraus symmetrisch mit
AES256. Der Klartext beruehrt nie das Dateisystem: Ein abgebrochener Lauf
wuerde sonst einen unverschluesselten Dump mit allen Fundkoordinaten auf dem
Volume zuruecklassen.

Ohne BACKUP_PASSPHRASE bricht der Job ab. Es gibt bewusst keinen Fallback auf
unverschluesselt — ein Backup, das man versehentlich im Klartext ablegt, ist
schlimmer als ein fehlendes, weil man sich auf es verlaesst.
"""

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.core.db import database_url, get_sessionmaker
from app.services.backups import BackupError, backup_dir, build_name, list_backups, rotate

REQUIRED_TOOLS = ("pg_dump", "gpg")

# Waehrend des Schreibens traegt die Datei diese Endung. Erst das Umbenennen
# nach erfolgreichem Lauf macht sie fuer die Rotation und die API sichtbar —
# ein Abbruch hinterlaesst damit kein halbes Backup, das echt aussieht.
PARTIAL_SUFFIX = ".part"

CIPHER = "AES256"


@dataclass(frozen=True)
class BackupResult:
    path: Path
    removed: list[str]


def _passphrase() -> str:
    wert = os.environ.get("BACKUP_PASSPHRASE", "")
    if not wert.strip():
        raise BackupError(
            "BACKUP_PASSPHRASE ist nicht gesetzt. Es wird kein unverschluesselter Dump geschrieben."
        )
    return wert


def _require_tools() -> None:
    fehlend = [name for name in REQUIRED_TOOLS if shutil.which(name) is None]
    if fehlend:
        raise BackupError(
            f"Benoetigte Programme fehlen im Image: {', '.join(fehlend)}. Siehe backend/Dockerfile."
        )


def parse_pg_dump_major(ausgabe: str) -> int:
    """Hauptversion aus `pg_dump --version`.

    Format: "pg_dump (PostgreSQL) 16.14 (Debian 16.14-1.pgdg13+1)".
    """
    treffer = re.search(r"\(PostgreSQL\)\s+(\d+)", ausgabe)
    if treffer is None:
        raise BackupError(f"Version von pg_dump nicht lesbar: {ausgabe.strip()!r}")
    return int(treffer.group(1))


def _pg_dump_major() -> int:
    ergebnis = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True, check=True)
    return parse_pg_dump_major(ergebnis.stdout)


def _server_major() -> int:
    with get_sessionmaker()() as db:
        # server_version_num ist 160014 fuer 16.14 — robuster als der
        # Anzeigetext, der je nach Distribution Zusaetze traegt.
        nummer = db.execute(text("SELECT current_setting('server_version_num')")).scalar_one()
    return int(nummer) // 10000


def _require_matching_major() -> None:
    """Ein Dump, den der Zielserver nicht einlesen kann, ist kein Backup.

    pg_dump schreibt das Archivformat seiner eigenen Version. Ist der Client
    neuer als der Server, laesst sich das Ergebnis mit dem passenden
    pg_restore nicht mehr einspielen ("unsupported version in file header").
    Das faellt beim Erstellen nicht auf — nur beim Wiederherstellen, also im
    denkbar schlechtesten Moment. Deshalb hier, laut und vorher.
    """
    dump_major = _pg_dump_major()
    server_major = _server_major()
    if dump_major != server_major:
        raise BackupError(
            f"Versionskonflikt: pg_dump ist {dump_major}, der Server ist PostgreSQL "
            f"{server_major}. Der Dump waere mit pg_restore {server_major} nicht "
            "einspielbar. Client-Hauptversion im backend/Dockerfile angleichen."
        )


def _pg_dump_command(url: str) -> list[str]:
    # psycopg-Praefix entfernen: pg_dump versteht nur die libpq-Form.
    libpq_url = url.replace("postgresql+psycopg://", "postgresql://", 1)
    return [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        # PostGIS-Referenzdaten: Eine frische Datenbank bekommt sie von
        # CREATE EXTENSION postgis. Im Dump wuerden sie beim Restore mit den
        # bereits vorhandenen Zeilen kollidieren. (Eigene SRIDs gibt es
        # nicht — das Projekt nutzt EPSG:4326 und 25832.)
        "--exclude-table=public.spatial_ref_sys",
        libpq_url,
    ]


def _gpg_command(passphrase_fd: int, ziel: Path) -> list[str]:
    return [
        "gpg",
        "--batch",
        "--yes",
        "--symmetric",
        "--cipher-algo",
        CIPHER,
        # Passphrase ueber einen eigenen Dateideskriptor: nicht als Argument
        # (stuende in der Prozessliste) und nicht ueber eine Datei.
        "--passphrase-fd",
        str(passphrase_fd),
        "--output",
        str(ziel),
    ]


def _run_pipeline(url: str, passphrase: str, ziel: Path) -> None:
    read_fd, write_fd = os.pipe()
    os.set_inheritable(read_fd, True)
    try:
        # Passphrasen sind kurz genug, um ohne Leser in den Pipe-Puffer zu passen.
        with os.fdopen(write_fd, "w") as kanal:
            kanal.write(passphrase)

        dump = subprocess.Popen(_pg_dump_command(url), stdout=subprocess.PIPE)
        assert dump.stdout is not None
        try:
            verschluesselung = subprocess.Popen(
                _gpg_command(read_fd, ziel), stdin=dump.stdout, pass_fds=(read_fd,)
            )
        finally:
            # Im Elternprozess schliessen, sonst bekommt gpg kein EOF.
            dump.stdout.close()

        gpg_code = verschluesselung.wait()
        dump_code = dump.wait()
    finally:
        os.close(read_fd)

    if dump_code != 0:
        raise BackupError(f"pg_dump endete mit Code {dump_code}.")
    if gpg_code != 0:
        raise BackupError(f"gpg endete mit Code {gpg_code}.")


def run_backup(now: datetime | None = None) -> BackupResult:
    """Legt einen verschluesselten Dump an und raeumt alte weg.

    Einziger Codepfad fuer den Dump: Sowohl `python -m app.jobs.backup_dump`
    als auch POST /api/backups/create landen hier (AP15.1). Zwei Wege, die
    sich auseinanderentwickeln koennen, waere bei einem Backup die
    schlechteste denkbare Stelle dafuer.
    """
    passphrase = _passphrase()
    _require_tools()
    _require_matching_major()

    verzeichnis = backup_dir()
    verzeichnis.mkdir(parents=True, exist_ok=True)

    ziel = verzeichnis / build_name(now or datetime.now(UTC))
    zwischenziel = ziel.with_name(ziel.name + PARTIAL_SUFFIX)

    try:
        _run_pipeline(database_url(), passphrase, zwischenziel)
    except BaseException:
        zwischenziel.unlink(missing_ok=True)
        raise

    if not zwischenziel.exists() or zwischenziel.stat().st_size == 0:
        zwischenziel.unlink(missing_ok=True)
        raise BackupError("Der erzeugte Dump ist leer.")

    zwischenziel.rename(ziel)
    return BackupResult(path=ziel, removed=rotate())


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # Keine Argumente; Konfiguration kommt aus der ENV.
    try:
        ergebnis = run_backup()
    except BackupError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — der Cron braucht einen Exit-Code, keinen Traceback
        print(f"FEHLER (unerwartet): {exc}", file=sys.stderr)
        return 1

    print(f"Backup: {ergebnis.path.name} ({ergebnis.path.stat().st_size} Bytes)")
    if ergebnis.removed:
        print(
            f"Rotation: {len(ergebnis.removed)} alte Dumps entfernt ({', '.join(ergebnis.removed)})"
        )
    print(f"Vorhanden: {len(list_backups())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
