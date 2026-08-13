"""Ablage der Eignungskarte auf dem Volume (ADR 0008 §7, §8).

Die Kacheln entstehen **lokal** auf dem Rechner des Nutzers
(`geoprocessing/`), nie hier: Auf dem Volume liegt nur die fertige
Kachelpyramide plus Metadatei. Diese Schicht kennt die Pfade, prüft, was
hochgeladen wird, und hängt es atomar um.

Auf demselben Volume liegen die Backups (ADR 0004, seit AP15 die einzige
Sicherung) und die 208-MB-Basiskarte aus AP10a. Deshalb wird vor jedem
Schreiben der freie Platz geprüft — dasselbe Muster wie im Basiskarten-Job.
"""

import json
import os
import shutil
from pathlib import Path
from typing import BinaryIO

TILES_NAME = "suitability.pmtiles"
META_NAME = "suitability.meta.json"

# Der Pfad der Auslieferung ist bewusst nicht der Dateiname: Spec §12 nennt
# `tiles.pmtiles`, auf dem Volume heisst die Datei nach ihrem Inhalt. Wer
# den Dateinamen ändert, ändert damit nicht die öffentliche Schnittstelle.
TILES_ROUTE = "tiles.pmtiles"

TMP_SUFFIX = ".tmp"

DEFAULT_DIR = "/data"

# Erste sieben Bytes jedes PMTiles-Archivs (Spec v3). Billigste mögliche
# Prüfung, ob da überhaupt eine Kachelpyramide ankommt — und sie verhindert
# den teuren Fall, dass eine halbe oder falsche Datei die aktive Karte wird.
PMTILES_MAGIC = b"PMTiles"

# Wie beim Basiskarten-Job: Nach dem Schreiben muss diese Reserve frei
# bleiben, sonst bricht die Backup-Rotation still.
MIN_FREE_BYTES = 1_000_000_000

# Grösserer Upload als das ist mit Sicherheit ein Versehen. Die Kacheln aus
# AP17a sind rund 8 MB; auch mit allen sechs Faktoren bleiben sie zweistellig.
MAX_UPLOAD_BYTES = 500_000_000

BLOCK = 1024 * 1024

# Ohne diese Felder ist die Metadatei für die Anzeige unbrauchbar: Der
# Planer muss sagen können, welche Faktoren enthalten sind (AP17a §6).
PFLICHTFELDER = ("gewichtssatz_version", "faktoren", "generated_at")


class SuitabilityError(RuntimeError):
    """Die Eignungskarte ist nicht verwendbar — fehlt, oder ist unlesbar."""


def suitability_dir() -> Path:
    return Path(os.environ.get("SUITABILITY_DIR", DEFAULT_DIR)).resolve()


def tiles_path() -> Path:
    return suitability_dir() / TILES_NAME


def meta_path() -> Path:
    return suitability_dir() / META_NAME


def read_meta() -> dict:
    """Metadaten der abgelegten Karte.

    Sie tragen Gewichtssatz-Version, beteiligte Faktoren und Quellen mit
    Abrufdatum — ohne sie darf der Layer nicht angezeigt werden, weil
    niemand sagen könnte, worauf der Score beruht (Invariante 10).
    """
    pfad = meta_path()
    try:
        inhalt = pfad.read_text()
    except OSError as exc:
        raise SuitabilityError(
            f"Keine Metadaten unter {pfad}. Es wurde noch keine Eignungskarte "
            "hochgeladen (siehe geoprocessing/README.md)."
        ) from exc

    try:
        metadaten = json.loads(inhalt)
    except json.JSONDecodeError as exc:
        raise SuitabilityError(f"Metadaten unter {pfad} sind kein JSON: {exc}") from exc

    if not isinstance(metadaten, dict):
        raise SuitabilityError(f"Metadaten unter {pfad} sind kein Objekt.")
    return metadaten


def pruefe_freien_platz(erwartete_bytes: int) -> int:
    """Vor dem Schreiben, nicht danach.

    Auf demselben Volume liegen die Backups, und die sind seit AP15 die
    einzige Sicherung (ADR 0004). Ein volles Volume bricht die Rotation
    still — auffallen würde es erst beim Restore.
    """
    verzeichnis = suitability_dir()
    verzeichnis.mkdir(parents=True, exist_ok=True)
    frei = shutil.disk_usage(verzeichnis).free
    danach = frei - erwartete_bytes
    if danach < MIN_FREE_BYTES:
        raise SuitabilityError(
            f"Zu wenig Platz auf {verzeichnis}: frei {frei // 1_000_000} MB, "
            f"Upload {erwartete_bytes // 1_000_000} MB, danach blieben "
            f"{danach // 1_000_000} MB statt der geforderten "
            f"{MIN_FREE_BYTES // 1_000_000} MB. Erst dort aufräumen (ADR 0004)."
        )
    return frei


def _pruefe_meta(rohtext: str) -> dict:
    try:
        metadaten = json.loads(rohtext)
    except json.JSONDecodeError as exc:
        raise SuitabilityError(f"Die Metadatei ist kein JSON: {exc}") from exc
    if not isinstance(metadaten, dict):
        raise SuitabilityError("Die Metadatei ist kein Objekt.")
    fehlend = [feld for feld in PFLICHTFELDER if feld not in metadaten]
    if fehlend:
        raise SuitabilityError(
            f"Der Metadatei fehlen Felder: {', '.join(fehlend)}. Sie stammt "
            "offenbar nicht aus stufe2_tiles.py."
        )
    return metadaten


def speichere_upload(kacheln: BinaryIO, meta_rohtext: str, groesse: int | None = None) -> dict:
    """Hochgeladene Kacheln und Metadatei auf das Volume legen.

    Reihenfolge und Absicherung wie beim Basiskarten-Job (AP10a):
    Freiplatz vorher prüfen, in `.tmp` schreiben, erst nach bestandener
    Prüfung umhängen. **Scheitert irgendetwas, bleibt die bisherige Karte
    unverändert liegen** — ein abgebrochener Upload wird nie zur aktiven
    Karte.
    """
    metadaten = _pruefe_meta(meta_rohtext)

    if groesse is not None:
        if groesse <= 0:
            raise SuitabilityError("Die hochgeladene Datei ist leer.")
        if groesse > MAX_UPLOAD_BYTES:
            raise SuitabilityError(
                f"Upload ist {groesse // 1_000_000} MB gross; mehr als "
                f"{MAX_UPLOAD_BYTES // 1_000_000} MB nimmt der Dienst nicht an."
            )
    pruefe_freien_platz(groesse or 0)

    verzeichnis = suitability_dir()
    ziel = verzeichnis / TILES_NAME
    zwischenziel = verzeichnis / (TILES_NAME + TMP_SUFFIX)
    meta_ziel = verzeichnis / META_NAME
    meta_zwischenziel = verzeichnis / (META_NAME + TMP_SUFFIX)

    geschrieben = 0
    try:
        with zwischenziel.open("wb") as datei:
            kopf = kacheln.read(len(PMTILES_MAGIC))
            if kopf != PMTILES_MAGIC:
                raise SuitabilityError(
                    "Das ist kein PMTiles-Archiv (Signatur fehlt). Stammt die "
                    "Datei aus geoprocessing/out/?"
                )
            datei.write(kopf)
            geschrieben += len(kopf)
            while block := kacheln.read(BLOCK):
                geschrieben += len(block)
                if geschrieben > MAX_UPLOAD_BYTES:
                    raise SuitabilityError(
                        f"Upload überschreitet {MAX_UPLOAD_BYTES // 1_000_000} MB."
                    )
                datei.write(block)

        meta_zwischenziel.write_text(json.dumps(metadaten, indent=2, ensure_ascii=False) + "\n")
    except BaseException:
        # Auch bei Abbruch von aussen: kein halbes Archiv zurücklassen.
        zwischenziel.unlink(missing_ok=True)
        meta_zwischenziel.unlink(missing_ok=True)
        raise

    os.replace(zwischenziel, ziel)
    os.replace(meta_zwischenziel, meta_ziel)

    return {
        "bytes": geschrieben,
        "gewichtssatz_version": metadaten.get("gewichtssatz_version"),
        "faktoren": list(metadaten.get("faktoren", {})),
        "generated_at": metadaten.get("generated_at"),
    }
