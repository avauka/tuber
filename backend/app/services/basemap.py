"""Ablage der Basiskarte auf dem Volume (ADR 0002).

Diese Schicht kennt nur Pfade und die Metadatei. Erzeugt wird die Karte vom
Job (`app/jobs/basemap_extract.py`, AP10a), gelesen von den Endpunkten unter
`/api/basemap` (AP10b) — beide gehen durch dieselben Namen hier, damit die
Ablage nicht an zwei Stellen definiert ist.
"""

import json
import os
from pathlib import Path

ARCHIVE_NAME = "basemap.pmtiles"
META_NAME = "basemap.meta.json"

# Waehrend des Schreibens traegt eine Datei diese Endung; erst das Umhaengen
# macht sie sichtbar (AP10a).
TMP_SUFFIX = ".tmp"

DEFAULT_DIR = "/data"


class BasemapError(RuntimeError):
    """Die Basiskarte ist nicht verwendbar — fehlt, oder ist unlesbar."""


def basemap_dir() -> Path:
    return Path(os.environ.get("BASEMAP_DIR", DEFAULT_DIR)).resolve()


def archive_path() -> Path:
    return basemap_dir() / ARCHIVE_NAME


def meta_path() -> Path:
    return basemap_dir() / META_NAME


def read_meta() -> dict:
    """Metadaten der abgelegten Karte.

    Sie tragen den OSM-Datenstand, der in der Attribution erscheinen muss
    (Spec §15) — deshalb ist eine fehlende Metadatei ein Fehler und kein
    stiller Leerwert.
    """
    pfad = meta_path()
    try:
        inhalt = pfad.read_text()
    except OSError as exc:
        raise BasemapError(
            f"Keine Metadaten unter {pfad}. Der Basiskarten-Job ist noch nicht "
            "gelaufen (python -m app.jobs.basemap_extract)."
        ) from exc

    try:
        metadaten = json.loads(inhalt)
    except json.JSONDecodeError as exc:
        raise BasemapError(f"Metadaten unter {pfad} sind kein JSON: {exc}") from exc

    if not isinstance(metadaten, dict):
        raise BasemapError(f"Metadaten unter {pfad} sind kein Objekt.")
    return metadaten
