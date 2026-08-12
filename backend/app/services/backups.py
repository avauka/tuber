"""Ablage der verschlüsselten Dumps (ADR 0004, AP15).

Die Dateien liegen auf einem Volume, nicht in der Datenbank. Diese Schicht
kennt nur das Verzeichnis und die Namenskonvention — sie erzeugt nichts und
entschlüsselt nichts.
"""

import os
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

SUFFIX = ".dump.gpg"
NAME_FORMAT = "tuber-%Y%m%d-%H%M%S"

# Streng: nur Dateien, die dieser Job selbst erzeugt hat. Der Ausdruck laesst
# weder Schraegstriche noch Punkte an anderer Stelle zu und ist damit die
# erste von zwei Sperren gegen Pfad-Traversal.
NAME_PATTERN = re.compile(r"^tuber-\d{8}-\d{6}\.dump\.gpg$")

KEEP_BACKUPS = 7

# Ein Dump auf dem Railway-Volume schuetzt nicht gegen Projekt- oder
# Accountverlust (ADR 0004). Erst der Download macht ihn zum Backup — bleibt
# er aus, gilt der Stand als veraltet.
STALE_AFTER = timedelta(days=7)

DEFAULT_BACKUP_DIR = "./data/backups"


class BackupError(RuntimeError):
    """Fehler, der den Job abbrechen muss."""


def backup_dir() -> Path:
    return Path(os.environ.get("BACKUP_DIR", DEFAULT_BACKUP_DIR)).resolve()


def build_name(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(NAME_FORMAT) + SUFFIX


def created_at(name: str) -> datetime:
    """Zeitpunkt aus dem Dateinamen — nicht aus der mtime, die sich beim
    Kopieren oder Wiederherstellen aendert."""
    stamp = name[: -len(SUFFIX)]
    return datetime.strptime(stamp, NAME_FORMAT).replace(tzinfo=UTC)


def list_backups() -> list[Path]:
    """Vorhandene Dumps, neueste zuerst."""
    verzeichnis = backup_dir()
    if not verzeichnis.is_dir():
        return []
    treffer = [p for p in verzeichnis.iterdir() if p.is_file() and NAME_PATTERN.match(p.name)]
    return sorted(treffer, key=lambda p: p.name, reverse=True)


def resolve(name: str) -> Path:
    """Dateiname in einen Pfad aufloesen — oder ablehnen.

    Zwei Sperren: der Name muss dem Muster entsprechen, und der aufgeloeste
    Pfad muss im Backup-Verzeichnis liegen. Die zweite faengt ab, was ueber
    Symlinks oder Kodierungstricks am Muster vorbeikaeme.
    """
    if not NAME_PATTERN.match(name):
        raise BackupError(f"Unzulaessiger Backup-Name: {name!r}")

    verzeichnis = backup_dir()
    pfad = (verzeichnis / name).resolve()
    if pfad.parent != verzeichnis:
        raise BackupError(f"Pfad liegt ausserhalb des Backup-Verzeichnisses: {name!r}")
    if not pfad.is_file():
        raise BackupError(f"Backup nicht gefunden: {name}")
    return pfad


def rotate(keep: int = KEEP_BACKUPS) -> list[str]:
    """Alles ausser den `keep` neuesten Dumps loeschen."""
    vorhanden = list_backups()
    entfernt: list[str] = []
    for pfad in vorhanden[keep:]:
        pfad.unlink(missing_ok=True)
        entfernt.append(pfad.name)
    return entfernt


def volume_usage() -> tuple[int, int, int]:
    """Gesamt, belegt und frei auf dem Dateisystem der Ablage — in Bytes.

    Auf demselben Volume liegt seit AP10a auch die Basiskarte. Ohne diese
    Zahlen scheitert die Rotation an einer vollen Platte, ohne dass es jemand
    sieht: Der Dump bricht ab, und auffallen wuerde es erst beim Restore.

    Gemessen wird am naechsten vorhandenen Verzeichnis oberhalb der Ablage —
    vor dem ersten Dump gibt es sie noch nicht, das Dateisystem ist aber
    dasselbe.
    """
    verzeichnis = backup_dir()
    while not verzeichnis.exists() and verzeichnis != verzeichnis.parent:
        verzeichnis = verzeichnis.parent
    total, used, free = shutil.disk_usage(verzeichnis)
    return total, used, free


def is_stale(name: str, downloaded_at: datetime | None, now: datetime | None = None) -> bool:
    """Nie heruntergeladen und älter als STALE_AFTER."""
    if downloaded_at is not None:
        return False
    jetzt = now or datetime.now(UTC)
    return jetzt - created_at(name) > STALE_AFTER
