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

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence

AccuracySource = Literal["meters", "hdop", "none"]


@dataclass(frozen=True)
class TrackPoint:
    lon: float
    lat: float
    time: datetime          # tz-aware, UTC
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
    mean_accuracy_m: float | None   # Mittel der BEHALTENEN Punkte
    all_accuracy_missing: bool


def parse_gpx(content: bytes) -> ParsedTrack:
    raise NotImplementedError


def clean_track(points: Sequence[TrackPoint]) -> CleanResult:
    raise NotImplementedError
