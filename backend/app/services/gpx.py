"""GPX-Parsing und Track-Bereinigung (Spec §9, ADR 0006).

VERTRAG (durch tests/unit/test_gpx_parsing.py fixiert, vor Implementierung):

Genauigkeit pro Punkt, drei Fälle (ADR 0006):
  1. "meters"  — ein Extension-Element, dessen lokaler Name "accuracy"
                 enthält (case-insensitive), Wert in Metern.
  2. "hdop"    — Standard-GPX <hdop>; Umrechnung hdop * HDOP_TO_M_FACTOR,
                 als Schätzung gekennzeichnet.
  3. "none"    — nichts vorhanden; accuracy_m ist None. Kein Punktfilter
                 möglich, all_accuracy_missing = True (=> Confidence niedrig).

Bereinigung (clean_track):
  - Punkte mit accuracy_m > TRACK_ACCURACY_MAX_M verwerfen.
  - Ausreisser über Geschwindigkeit > TRACK_SPEED_MAX_MS verwerfen.
  - Eingabe wird NIE mutiert — der Rohtrack bleibt erhalten (Invariante 5).
"""

import math
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.core import params

AccuracySource = Literal["meters", "hdop", "none"]

# Mittlerer Erdradius für die Haversine-Distanz. Physikalische Konstante,
# nichts Kalibrierbares — gehört daher nicht nach params.py.
EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class TrackPoint:
    lon: float
    lat: float
    time: datetime  # tz-aware, UTC
    accuracy_m: float | None
    accuracy_source: AccuracySource


@dataclass(frozen=True)
class ParsedTrack:
    points: tuple[TrackPoint, ...]
    name: str | None


@dataclass(frozen=True)
class CleanResult:
    kept: tuple[TrackPoint, ...]
    dropped_accuracy: int
    dropped_speed: int
    mean_accuracy_m: float | None  # Mittel der BEHALTENEN Punkte
    all_accuracy_missing: bool


# --- XML-Hilfen -----------------------------------------------------------
# GPX-Dateien tragen je nach Logger-App unterschiedliche Namespaces. Wir
# vergleichen deshalb durchgängig über den lokalen Namen statt über feste
# Namespace-URIs (ADR 0006: der Parser muss App-tolerant sein).


def _local_name(tag: str) -> str:
    """'{http://...}trkpt' -> 'trkpt'."""
    return tag.rsplit("}", 1)[-1]


def _find_child(element: ET.Element, name: str) -> ET.Element | None:
    """Direktes Kindelement mit diesem lokalen Namen, sonst None."""
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def _parse_float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text.strip())
    except ValueError:
        return None


def _parse_time(text: str | None, index: int) -> datetime:
    """GPX-Zeitstempel als tz-aware UTC. Ohne Zeit kein Punkt: die
    Geschwindigkeitsprüfung und die Session-Zuordnung hängen daran."""
    if text is None or not text.strip():
        raise ValueError(f"trkpt #{index}: <time> fehlt — Track nicht verwertbar.")
    raw = text.strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"trkpt #{index}: <time> nicht lesbar ({text!r}).") from exc
    if parsed.tzinfo is None:
        # GPX schreibt UTC vor. Fehlt die Zone, lesen wir sie als UTC —
        # das ist die Spezifikation, keine Annahme über die Lokalzeit.
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _accuracy_from_extensions(trkpt: ET.Element) -> float | None:
    """Fall 1: Meter-Genauigkeit aus einem <extensions>-Element, dessen
    lokaler Name 'accuracy' enthält (z. B. <ogt:accuracy>)."""
    extensions = _find_child(trkpt, "extensions")
    if extensions is None:
        return None
    for element in extensions.iter():
        if "accuracy" in _local_name(element.tag).lower():
            value = _parse_float(element.text)
            if value is not None:
                return value
    return None


def _parse_point(trkpt: ET.Element, index: int) -> TrackPoint:
    lat = _parse_float(trkpt.get("lat"))
    lon = _parse_float(trkpt.get("lon"))
    if lat is None or lon is None:
        raise ValueError(f"trkpt #{index}: lat/lon fehlen oder sind unlesbar.")

    time_element = _find_child(trkpt, "time")
    time = _parse_time(time_element.text if time_element is not None else None, index)

    # Reihenfolge ist Vertrag: die echte Meterangabe schlägt die
    # hdop-Schätzung, und geschätzt wird nur, wenn hdop wirklich dasteht.
    accuracy_m = _accuracy_from_extensions(trkpt)
    if accuracy_m is not None:
        return TrackPoint(lon, lat, time, accuracy_m, "meters")

    hdop_element = _find_child(trkpt, "hdop")
    hdop = _parse_float(hdop_element.text) if hdop_element is not None else None
    if hdop is not None:
        return TrackPoint(lon, lat, time, hdop * params.HDOP_TO_M_FACTOR, "hdop")

    # Fall 3: keine Angabe. Nie einen Wert erfinden — downstream wird daraus
    # Confidence 'niedrig', kein Punktfilter.
    return TrackPoint(lon, lat, time, None, "none")


def parse_gpx(content: bytes) -> ParsedTrack:
    """Alle Trackpunkte in Dokumentreihenfolge, Zeiten normalisiert auf UTC."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Kein gültiges GPX/XML: {exc}") from exc

    name: str | None = None
    points: list[TrackPoint] = []
    index = 0

    for trk in (element for element in root.iter() if _local_name(element.tag) == "trk"):
        if name is None:
            name_element = _find_child(trk, "name")
            if name_element is not None and name_element.text:
                name = name_element.text.strip() or None
        # .iter() statt fester trkseg-Verschachtelung: mehrere Segmente
        # gehören zum selben Track und bleiben eine Punktfolge.
        for trkpt in (el for el in trk.iter() if _local_name(el.tag) == "trkpt"):
            points.append(_parse_point(trkpt, index))
            index += 1

    return ParsedTrack(points=tuple(points), name=name)


# --- Bereinigung ----------------------------------------------------------


def _distance_m(a: TrackPoint, b: TrackPoint) -> float:
    """Haversine-Distanz in Metern — für Punktabstände im Meterbereich
    genau genug und ohne Projektionsabhängigkeit."""
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _is_speed_outlier(previous: TrackPoint, current: TrackPoint) -> bool:
    seconds = (current.time - previous.time).total_seconds()
    distance = _distance_m(previous, current)
    if seconds <= 0:
        # Gleicher oder rückwärts laufender Zeitstempel: ein Ortswechsel ist
        # dann unplausibel, ein reines Duplikat nicht.
        return distance > 0
    return distance / seconds > params.TRACK_SPEED_MAX_MS


def clean_track(points: Sequence[TrackPoint]) -> CleanResult:
    """Genauigkeits- und Ausreisserfilter. Liest die Eingabe nur — der
    Rohtrack bleibt unverändert erhalten (Invariante 5)."""
    all_accuracy_missing = all(point.accuracy_m is None for point in points)

    # Schritt 1: Genauigkeit. Ohne Angabe ist kein Filter möglich (ADR 0006),
    # der Punkt bleibt und die Confidence sinkt stattdessen downstream.
    after_accuracy: list[TrackPoint] = []
    dropped_accuracy = 0
    for point in points:
        if point.accuracy_m is not None and point.accuracy_m > params.TRACK_ACCURACY_MAX_M:
            dropped_accuracy += 1
            continue
        after_accuracy.append(point)

    # Schritt 2: Geschwindigkeit, immer gegen den letzten BEHALTENEN Punkt.
    # Gegen den letzten gelesenen Punkt gemessen würde ein einzelner
    # Kronendach-Sprung den gesamten Rest des Tracks mitreissen.
    kept: list[TrackPoint] = []
    dropped_speed = 0
    for point in after_accuracy:
        if kept and _is_speed_outlier(kept[-1], point):
            dropped_speed += 1
            continue
        kept.append(point)

    accuracies = [point.accuracy_m for point in kept if point.accuracy_m is not None]
    mean_accuracy_m = sum(accuracies) / len(accuracies) if accuracies else None

    return CleanResult(
        kept=tuple(kept),
        dropped_accuracy=dropped_accuracy,
        dropped_speed=dropped_speed,
        mean_accuracy_m=mean_accuracy_m,
        all_accuracy_missing=all_accuracy_missing,
    )
