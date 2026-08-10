"""Gemeinsame Bausteine der Feld-Endpunkte.

Fehlerformat: FastAPI-Standard-Bodies. Die Offline-Queue unterscheidet
retryable / nicht-retryable ausschliesslich am Statuscode — 4xx ist
endgültig und wird nicht wiederholt, 5xx und Netzfehler werden wiederholt.
Deshalb bewusst kein eigenes Fehlerschema.
"""

from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import Cast, cast, func
from sqlalchemy.orm import InstrumentedAttribute

SRID = 4326


def point(lat: float, lon: float) -> WKTElement:
    """Punktgeometrie für eine geography-Spalte (EPSG:4326, Invariante 11)."""
    return WKTElement(f"POINT({lon} {lat})", srid=SRID)


def as_geometry(geom_column: InstrumentedAttribute) -> Cast:
    """geography -> geometry. ST_X/ST_Y und ST_Intersects gegen eine Bbox
    arbeiten auf geometry; für den reinen Koordinatenzugriff und einen
    Rechteckfilter ist das exakt genug."""
    return cast(geom_column, Geometry)


def lat_column(geom_column: InstrumentedAttribute):
    return func.ST_Y(as_geometry(geom_column)).label("lat")


def lon_column(geom_column: InstrumentedAttribute):
    return func.ST_X(as_geometry(geom_column)).label("lon")


def bbox_filter(geom_column: InstrumentedAttribute, raw_bbox: str):
    """Filter aus 'minLon,minLat,maxLon,maxLat' (EPSG:4326)."""
    parts = raw_bbox.split(",")
    if len(parts) != 4:
        raise ValueError("bbox erwartet vier Werte: minLon,minLat,maxLon,maxLat")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("bbox erwartet vier Zahlen: minLon,minLat,maxLon,maxLat") from exc

    envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, SRID)
    return func.ST_Intersects(as_geometry(geom_column), envelope)
