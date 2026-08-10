"""GeoJSON <-> WKT für Gebietsgeometrien.

Geprüft wird hier nur, was sich ohne Datenbank feststellen lässt: Struktur,
geschlossene Ringe und WGS84-Wertebereich. Die topologische Gültigkeit
(Selbstüberschneidung) beantwortet PostGIS per ST_IsValid — die Regeln dafür
selbst nachzubauen wäre fehleranfälliger als sie zu fragen.
"""

from collections.abc import Mapping, Sequence
from typing import Any

LON_MIN, LON_MAX = -180.0, 180.0
LAT_MIN, LAT_MAX = -90.0, 90.0

# Ein geschlossener Ring braucht drei Ecken plus den wiederholten Startpunkt.
MIN_RING_POSITIONS = 4


def _position(raw: Any, ring_index: int, position_index: int) -> tuple[float, float]:
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes) or len(raw) < 2:
        raise ValueError(f"Ring {ring_index}, Position {position_index}: erwartet wird [lon, lat].")
    try:
        lon = float(raw[0])
        lat = float(raw[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Ring {ring_index}, Position {position_index}: lon/lat sind keine Zahlen."
        ) from exc

    if not LON_MIN <= lon <= LON_MAX:
        raise ValueError(
            f"Ring {ring_index}, Position {position_index}: lon {lon} liegt "
            f"ausserhalb von {LON_MIN}..{LON_MAX} (EPSG:4326)."
        )
    if not LAT_MIN <= lat <= LAT_MAX:
        raise ValueError(
            f"Ring {ring_index}, Position {position_index}: lat {lat} liegt "
            f"ausserhalb von {LAT_MIN}..{LAT_MAX} (EPSG:4326)."
        )
    return lon, lat


def polygon_wkt(geometry: Mapping[str, Any]) -> str:
    """GeoJSON-Polygon in WKT übersetzen. Wirft ValueError im Klartext."""
    if geometry.get("type") != "Polygon":
        raise ValueError("geometry.type muss 'Polygon' sein.")

    rings = geometry.get("coordinates")
    if not isinstance(rings, list) or not rings:
        raise ValueError("geometry.coordinates fehlt oder ist leer.")

    wkt_rings: list[str] = []
    for ring_index, ring in enumerate(rings):
        if not isinstance(ring, list) or len(ring) < MIN_RING_POSITIONS:
            raise ValueError(
                f"Ring {ring_index} braucht mindestens {MIN_RING_POSITIONS} Positionen."
            )
        positions = [
            _position(raw, ring_index, position_index) for position_index, raw in enumerate(ring)
        ]
        if positions[0] != positions[-1]:
            raise ValueError(
                f"Ring {ring_index} ist nicht geschlossen: erste und letzte "
                "Position müssen identisch sein."
            )
        wkt_rings.append("(" + ", ".join(f"{lon} {lat}" for lon, lat in positions) + ")")

    return "POLYGON(" + ", ".join(wkt_rings) + ")"
