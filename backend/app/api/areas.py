"""Gebiets-Endpunkte (Spec §12)."""

import json

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import Row, Select, func, select

from app.core.db import DbSession
from app.models.core import Area
from app.schemas.areas import AreaCreate, AreaRead
from app.services.geojson import polygon_wkt

router = APIRouter(prefix="/api/areas", tags=["areas"])

SRID = 4326


def _select_areas() -> Select:
    return select(
        Area,
        func.ST_Area(Area.geom).label("area_m2"),
        func.ST_AsGeoJSON(Area.geom).label("geojson"),
    )


def _to_read(row: Row) -> AreaRead:
    area, area_m2, geojson = row
    return AreaRead(
        id=area.id,
        name=area.name,
        geometry=json.loads(geojson),
        notes=area.notes,
        access_notes=area.access_notes,
        last_visited=area.last_visited,
        offline_pinned=area.offline_pinned,
        area_m2=float(area_m2),
    )


def _validated_wkt(db: DbSession, geometry: dict) -> str:
    """Struktur und Wertebereich in Python, Topologie in PostGIS."""
    try:
        wkt = polygon_wkt(geometry)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    geom = func.ST_GeomFromText(wkt, SRID)
    valid, reason = db.execute(select(func.ST_IsValid(geom), func.ST_IsValidReason(geom))).one()
    if not valid:
        # Typischer Fall: Selbstueberschneidung ("bow-tie").
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Polygon ist topologisch ungueltig: {reason}",
        )
    return wkt


@router.post("", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
def create_area(payload: AreaCreate, db: DbSession) -> AreaRead:
    wkt = _validated_wkt(db, payload.geometry)
    area = Area(
        name=payload.name,
        geom=func.ST_GeogFromText(f"SRID={SRID};{wkt}"),
        notes=payload.notes,
        access_notes=payload.access_notes,
        offline_pinned=payload.offline_pinned,
    )
    db.add(area)
    db.commit()

    row = db.execute(_select_areas().where(Area.id == area.id)).one()
    return _to_read(row)


@router.get("", response_model=list[AreaRead])
def list_areas(db: DbSession) -> list[AreaRead]:
    rows = db.execute(_select_areas().order_by(Area.name)).all()
    return [_to_read(row) for row in rows]
