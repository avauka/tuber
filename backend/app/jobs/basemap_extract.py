"""Basiskarte beschaffen (ADR 0002, AP10a).

Aufruf:  python -m app.jobs.basemap_extract

Holt per `pmtiles extract` einen regionalen Ausschnitt aus dem
Protomaps-Planet-Build und legt ihn als `basemap.pmtiles` auf dem Volume ab.
Daneben entsteht `basemap.meta.json` mit dem OSM-Datenstand und der
Tileset-Version — die Werte, die spaeter in der Attribution stehen (Spec §15).

Das Build-Datum kommt bewusst ohne Default aus der Umgebung: Protomaps haelt
nur die Builds der letzten Woche vor, und ein geratenes "gestern" liefe gegen
einen Build, der womoeglich noch hochlaedt. Vor jedem Lauf ist ein aktuelles
Datum von maps.protomaps.com/builds zu waehlen.

Der Job ist wiederholbar und laesst eine vorhandene Karte im Fehlerfall
unberuehrt: Geschrieben wird nach `.tmp`, umgehaengt wird erst nach der
Pruefung — und gepruefft wird, indem das Archiv geoeffnet wird.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

BUILD_URL = "https://build.protomaps.com/{date}.pmtiles"

ARCHIVE_NAME = "basemap.pmtiles"
META_NAME = "basemap.meta.json"

# Waehrend des Schreibens traegt die Datei diese Endung. Erst das Umhaengen
# nach bestandener Pruefung macht sie zur aktiven Karte — ein Abbruch
# hinterlaesst damit kein halbes Archiv, das echt aussieht.
TMP_SUFFIX = ".tmp"

DEFAULT_DIR = "/data"

# Aachen/Eifel/Ardennen (ADR 0002). Maxzoom 14 reicht bis in die Waldwege:
# Tracks tragen im Protomaps-Tileset min_zoom 13, und ueber z14 hinaus
# zeichnet MapLibre per Overzoom weiter (lokal verifiziert 2026-08-12).
DEFAULT_BBOX = "5.4,49.7,7.2,51.1"
DEFAULT_MAXZOOM = 14

DOWNLOAD_THREADS = 8

# Protomaps-Builds tragen ein reines Tagesdatum. Die Pruefung faengt den
# Tippfehler hier ab, statt ihn als 404 der Quelle zurueckkommen zu lassen.
BUILD_DATE_PATTERN = re.compile(r"^\d{8}$")

# Feld in basemap.meta.json -> Schluessel in den Archiv-Metadaten. Beides
# kommt aus dem Archiv und nicht aus dem Dateinamen (ADR 0002).
ATTRIBUTION_KEYS = {
    "osm_data_timestamp": "planetiler:osm:osmosisreplicationtime",
    "tileset_version": "version",
}

# Konservativ ueber dem gemessenen Wert (208 MB am 2026-08-12), damit ein
# gewachsener OSM-Datenbestand die Pruefung nicht ueberholt. Dezimale
# Einheiten wie bei go-pmtiles und in der Railway-Anzeige — sonst stehen im
# Log zwei Zahlen fuer dieselbe Datei.
EXPECTED_BYTES = 300_000_000

# Auf demselben Volume liegen die Backups, und die sind seit AP15 die
# einzige Sicherung des Projekts (ADR 0004). Ein volles Volume bricht die
# Rotation still — deshalb bleibt dieses Gigabyte reserviert, und deshalb
# wird vor dem Schreiben geprueft und nicht danach.
MIN_FREE_BYTES = 1_000_000_000


class BasemapError(RuntimeError):
    """Fehler, der den Job abbrechen muss."""


@dataclass(frozen=True)
class BasemapResult:
    path: Path
    meta_path: Path
    bytes: int
    seconds: float
    free_before: int
    free_after: int


def basemap_dir() -> Path:
    return Path(os.environ.get("BASEMAP_DIR", DEFAULT_DIR)).resolve()


def _build_date() -> str:
    wert = os.environ.get("BASEMAP_BUILD_DATE", "").strip()
    if not wert:
        raise BasemapError(
            "BASEMAP_BUILD_DATE ist nicht gesetzt. Es gibt bewusst keinen Default: "
            "Protomaps haelt nur die Builds der letzten Woche vor. Aktuelles Datum "
            "(Form JJJJMMTT) von https://maps.protomaps.com/builds waehlen."
        )
    if not BUILD_DATE_PATTERN.match(wert):
        raise BasemapError(
            f"BASEMAP_BUILD_DATE={wert!r} ist kein Build-Datum. Erwartet wird die "
            "Form JJJJMMTT, etwa 20260811."
        )
    return wert


def _bbox() -> tuple[str, list[float]]:
    """Rohwert fuer die Kommandozeile, Zahlen fuer die Metadaten."""
    rohwert = os.environ.get("BASEMAP_BBOX", DEFAULT_BBOX).strip()
    teile = rohwert.split(",")
    try:
        zahlen = [float(teil) for teil in teile]
    except ValueError as exc:
        raise BasemapError(f"BASEMAP_BBOX={rohwert!r} ist nicht lesbar: {exc}") from exc
    if len(zahlen) != 4:
        raise BasemapError(
            f"BASEMAP_BBOX={rohwert!r} braucht vier Werte "
            f"(min_lon,min_lat,max_lon,max_lat), gefunden: {len(zahlen)}."
        )
    return rohwert, zahlen


def _maxzoom() -> int:
    rohwert = os.environ.get("BASEMAP_MAXZOOM", str(DEFAULT_MAXZOOM)).strip()
    try:
        return int(rohwert)
    except ValueError as exc:
        raise BasemapError(f"BASEMAP_MAXZOOM={rohwert!r} ist keine Zahl.") from exc


def _menschlich(anzahl: float) -> str:
    if abs(anzahl) >= 1_000_000_000:
        return f"{anzahl / 1_000_000_000:.1f} GB"
    return f"{anzahl / 1_000_000:.0f} MB"


def _require_free_space(verzeichnis: Path) -> int:
    """Platz VOR dem Extract pruefen, nicht danach."""
    frei = shutil.disk_usage(verzeichnis).free
    danach = frei - EXPECTED_BYTES
    if danach < MIN_FREE_BYTES:
        raise BasemapError(
            f"Zu wenig Platz auf {verzeichnis}: frei {_menschlich(frei)}, erwarteter "
            f"Bedarf {_menschlich(EXPECTED_BYTES)}, danach blieben {_menschlich(danach)} "
            f"statt der geforderten {_menschlich(MIN_FREE_BYTES)}. Auf demselben Volume "
            "liegen die Backups — erst dort aufraeumen (ADR 0004)."
        )
    return frei


def _extract(url: str, ziel: Path, bbox: str, maxzoom: int) -> None:
    befehl = [
        "pmtiles",
        "extract",
        url,
        str(ziel),
        f"--bbox={bbox}",
        f"--maxzoom={maxzoom}",
        f"--download-threads={DOWNLOAD_THREADS}",
    ]
    print(f"$ {' '.join(befehl)}")

    # Ein liegengebliebenes .tmp aus einem abgebrochenen Lauf waere sonst der
    # Startzustand des naechsten.
    ziel.unlink(missing_ok=True)

    try:
        ergebnis = subprocess.run(befehl, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        ausgabe = f"{exc.stdout or ''}{exc.stderr or ''}"
        print(ausgabe, file=sys.stderr)
        # go-pmtiles meldet den Statuscode im Klartext ("HTTP error: 404").
        # Der Wortlaut ist kein Vertrag, deshalb nur als Hinweis benutzt: die
        # Meldung nennt in beiden Faellen das Datum.
        if "404" in ausgabe:
            raise BasemapError(
                f"Build nicht mehr verfuegbar: {url}. Protomaps haelt nur die Builds "
                "der letzten Woche vor — neueres Datum in BASEMAP_BUILD_DATE eintragen "
                "(https://maps.protomaps.com/builds)."
            ) from exc
        raise BasemapError(f"pmtiles extract endete mit Code {exc.returncode}.") from exc

    print(f"{ergebnis.stdout}{ergebnis.stderr}")


def _metadata(pfad: Path) -> dict:
    """Archiv oeffnen und die Metadaten holen — beides in einem Schritt.

    Laeuft `pmtiles show --metadata` durch, ist das Archiv strukturell heil:
    Header, Verzeichnis und Metadatenblock sind lesbar. Eine Groessenheuristik
    wuerde dagegen eine abgebrochene Uebertragung durchwinken.

    Nur die JSON-Ausgabe von `--metadata` wird gelesen. Die menschenlesbare
    Ausgabe von `pmtiles show` ohne Flag ist kein Vertrag.
    """
    try:
        ergebnis = subprocess.run(
            ["pmtiles", "show", "--metadata", str(pfad)],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"{exc.stdout or ''}{exc.stderr or ''}", file=sys.stderr)
        raise BasemapError(
            f"Das erzeugte Archiv ist nicht lesbar (pmtiles show endete mit Code "
            f"{exc.returncode}). Die Uebertragung war unvollstaendig."
        ) from exc

    try:
        metadaten = json.loads(ergebnis.stdout)
    except json.JSONDecodeError as exc:
        raise BasemapError(f"Metadaten des Archivs sind kein JSON: {exc}") from exc

    if not isinstance(metadaten, dict):
        raise BasemapError("Metadaten des Archivs sind kein Objekt.")
    return metadaten


def _attribution(metadaten: dict) -> dict[str, str]:
    """Datenstand und Tileset-Version aus den Archiv-Metadaten.

    Beides steht spaeter in der Attribution (Spec §15). Fehlt es, ist an der
    Quelle etwas anders als angenommen — dann bricht der Job ab, statt `null`
    in die Metadatei zu schreiben und die Attribution still ohne Datenstand
    dastehen zu lassen.
    """
    werte = {feld: metadaten.get(schluessel) for feld, schluessel in ATTRIBUTION_KEYS.items()}
    fehlend = [ATTRIBUTION_KEYS[feld] for feld, wert in werte.items() if not wert]
    if fehlend:
        raise BasemapError(
            f"Die Archiv-Metadaten enthalten nicht: {', '.join(fehlend)}. Ohne diese "
            "Werte gibt es keinen Datenstand fuer die Attribution (Spec §15)."
        )
    return {feld: str(wert) for feld, wert in werte.items()}


def _sha256(pfad: Path) -> str:
    """Blockweise: Das Archiv ist groesser als der Container an RAM hat."""
    digest = hashlib.sha256()
    with pfad.open("rb") as datei:
        for block in iter(lambda: datei.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(ziel: Path, inhalt: dict) -> None:
    zwischenziel = ziel.with_name(ziel.name + TMP_SUFFIX)
    zwischenziel.write_text(json.dumps(inhalt, indent=2, ensure_ascii=False) + "\n")
    os.replace(zwischenziel, ziel)


def run_extract(now: datetime | None = None) -> BasemapResult:
    build_date = _build_date()
    bbox_roh, bbox = _bbox()
    maxzoom = _maxzoom()

    verzeichnis = basemap_dir()
    verzeichnis.mkdir(parents=True, exist_ok=True)

    ziel = verzeichnis / ARCHIVE_NAME
    zwischenziel = verzeichnis / (ARCHIVE_NAME + TMP_SUFFIX)
    meta_ziel = verzeichnis / META_NAME

    frei_vorher = _require_free_space(verzeichnis)
    print(f"Frei auf {verzeichnis}: {_menschlich(frei_vorher)}")

    url = BUILD_URL.format(date=build_date)
    beginn = time.monotonic()
    try:
        _extract(url, zwischenziel, bbox_roh, maxzoom)
        attribution = _attribution(_metadata(zwischenziel))
        groesse = zwischenziel.stat().st_size
        pruefsumme = _sha256(zwischenziel)
    except BaseException:
        # Auch bei Abbruch von aussen: kein halbes Archiv zuruecklassen. Die
        # bestehende basemap.pmtiles ist zu keinem Zeitpunkt angefasst worden.
        zwischenziel.unlink(missing_ok=True)
        raise

    os.replace(zwischenziel, ziel)
    dauer = time.monotonic() - beginn

    _write_json(
        meta_ziel,
        {
            "build_date": build_date,
            # osm_data_timestamp und tileset_version: aus dem Archiv, nicht
            # aus dem Dateinamen.
            **attribution,
            "bbox": bbox,
            "maxzoom": maxzoom,
            "bytes": groesse,
            "sha256": pruefsumme,
            # Sekundengenau: Die Datei wird gelesen, nicht gerechnet.
            "fetched_at": (now or datetime.now(UTC))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        },
    )

    return BasemapResult(
        path=ziel,
        meta_path=meta_ziel,
        bytes=groesse,
        seconds=dauer,
        free_before=frei_vorher,
        free_after=shutil.disk_usage(verzeichnis).free,
    )


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # Keine Argumente; Konfiguration kommt aus der ENV.
    try:
        ergebnis = run_extract()
    except BasemapError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — der Job braucht einen Exit-Code, keinen Traceback
        print(f"FEHLER (unerwartet): {exc}", file=sys.stderr)
        return 1

    print(
        f"Basiskarte: {ergebnis.path} ({_menschlich(ergebnis.bytes)}, "
        f"{ergebnis.seconds:.0f} s)\n"
        f"Metadaten:  {ergebnis.meta_path}\n"
        f"Frei vorher {_menschlich(ergebnis.free_before)}, "
        f"nachher {_menschlich(ergebnis.free_after)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
