"""Gebiets-Endpunkte (Spec §12)."""

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import Row, Select, func, select

from app.core.db import DbSession
from app.models.core import Area, SeasonNormal, SeasonState
from app.schemas.areas import AreaCreate, AreaRead, SeasonRead
from app.services.geojson import polygon_wkt

router = APIRouter(prefix="/api/areas", tags=["areas"])

SRID = 4326


def _select_areas() -> Select:
    return select(
        Area,
        func.ST_Area(Area.geom).label("area_m2"),
        func.ST_AsGeoJSON(Area.geom).label("geojson"),
    )


def _saisonzustaende(db: DbSession, area_ids: list[UUID]) -> dict[UUID, SeasonRead]:
    """Je Gebiet der jüngste Saisonzustand (AP-Saisonzustand §6).

    Eigene Abfrage statt Join: Die Tabelle führt je Gebiet mehrere
    Stichtage, angezeigt wird der neueste. Ein Join über alle Zeilen
    lieferte Dubletten der Gebiete.
    """
    if not area_ids:
        return {}

    juengster = (
        select(
            SeasonState.area_id,
            func.max(SeasonState.window_end).label("window_end"),
        )
        .where(SeasonState.area_id.in_(area_ids))
        .group_by(SeasonState.area_id)
        .subquery()
    )
    zeilen = db.execute(
        select(SeasonState, SeasonNormal)
        .join(
            juengster,
            (SeasonState.area_id == juengster.c.area_id)
            & (SeasonState.window_end == juengster.c.window_end),
        )
        .join(SeasonNormal, SeasonNormal.area_id == SeasonState.area_id)
    ).all()

    return {
        zustand.area_id: SeasonRead(
            window_end=zustand.window_end,
            precipitation_30d_mm=_als_float(zustand.precipitation_30d_mm),
            precipitation_90d_mm=_als_float(zustand.precipitation_90d_mm),
            precipitation_180d_mm=_als_float(zustand.precipitation_180d_mm),
            precipitation_30d_percent=_als_float(zustand.precipitation_30d_percent),
            precipitation_90d_percent=_als_float(zustand.precipitation_90d_percent),
            precipitation_180d_percent=_als_float(zustand.precipitation_180d_percent),
            soil_moisture_90d=_als_float(zustand.soil_moisture_90d),
            soil_moisture_90d_percent=_als_float(zustand.soil_moisture_90d_percent),
            dry_spell_days=zustand.dry_spell_days,
            complete=zustand.complete,
            missing_days=zustand.missing_days,
            reference_from_year=normale.reference_from_year,
            reference_to_year=normale.reference_to_year,
            source=zustand.source,
        )
        for zustand, normale in zeilen
    }


def _als_float(wert) -> float | None:
    return None if wert is None else float(wert)


def _to_read(row: Row, saison: SeasonRead | None = None) -> AreaRead:
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
        season=saison,
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
    # Ein frisch angelegtes Gebiet hat noch keinen Saisonzustand; den holt
    # der monatliche Backfill.
    return _to_read(row)


@router.get("", response_model=list[AreaRead])
def list_areas(db: DbSession) -> list[AreaRead]:
    rows = db.execute(_select_areas().order_by(Area.name)).all()
    saison = _saisonzustaende(db, [row[0].id for row in rows])
    return [_to_read(row, saison.get(row[0].id)) for row in rows]
