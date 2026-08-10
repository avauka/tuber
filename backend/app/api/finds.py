"""Fund-Endpunkte (Spec §12). Idempotent über client_uuid (Invariante 3)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import Row, Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import bbox_filter, lat_column, lon_column, point
from app.core import params
from app.core.db import DbSession
from app.models.core import Find
from app.schemas.finds import FindCreate, FindRead

router = APIRouter(prefix="/api/finds", tags=["finds"])


def _select_finds() -> Select:
    # lat/lon kommen aus der Geometrie zurück, nicht aus dem Request — die
    # Antwort spiegelt damit immer den gespeicherten Zustand.
    return select(Find, lat_column(Find.geom), lon_column(Find.geom))


def _row_by_client_uuid(db: Session, client_uuid: UUID) -> Row | None:
    return db.execute(_select_finds().where(Find.client_uuid == client_uuid)).first()


def _to_read(row: Row) -> FindRead:
    find, lat, lon = row
    return FindRead(
        id=find.id,
        client_uuid=find.client_uuid,
        lat=lat,
        lon=lon,
        gps_accuracy_m=find.gps_accuracy_m,
        found_at=find.found_at,
        session_id=find.session_id,
        species_guess=find.species_guess,
        species_confidence=find.species_confidence,
        phenotype=find.phenotype,
        id_pending=find.id_pending,
        maturity=find.maturity,
        calcium_reaction=find.calcium_reaction,
        revisit_due=find.revisit_due,
        notes=find.notes,
        created_at=find.created_at,
    )


@router.post("", response_model=FindRead, status_code=status.HTTP_201_CREATED)
def create_find(payload: FindCreate, response: Response, db: DbSession) -> FindRead:
    """Legt einen Fund an. Wiederholte POSTs mit derselben client_uuid
    liefern denselben Datensatz mit 200 statt eines Duplikats."""
    existing = _row_by_client_uuid(db, payload.client_uuid)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _to_read(existing)

    find = Find(
        client_uuid=payload.client_uuid,
        geom=point(payload.lat, payload.lon),
        gps_accuracy_m=payload.gps_accuracy_m,
        found_at=payload.found_at,
        session_id=payload.session_id,
        notes=payload.notes,
        # Spec §10: serverseitig abgeleitet, nie vom Client gesetzt.
        revisit_due=(payload.found_at + params.REVISIT_OFFSET).date(),
    )
    db.add(find)
    try:
        db.commit()
    except IntegrityError:
        # Zwei Replays der Queue gleichzeitig: der Unique-Index auf
        # client_uuid gewinnt, wir liefern den bereits angelegten Fund.
        db.rollback()
        raced = _row_by_client_uuid(db, payload.client_uuid)
        if raced is None:
            raise
        response.status_code = status.HTTP_200_OK
        return _to_read(raced)

    created = _row_by_client_uuid(db, payload.client_uuid)
    if created is None:  # pragma: no cover — nur bei Commit ohne Zeile denkbar
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fund nach dem Commit nicht auffindbar.",
        )
    return _to_read(created)


@router.get("", response_model=list[FindRead])
def list_finds(
    db: DbSession,
    bbox: Annotated[
        str | None, Query(description="minLon,minLat,maxLon,maxLat (EPSG:4326)")
    ] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> list[FindRead]:
    """Alle Funde, neueste zuerst. Ohne Filter vollständig.

    Bewusst ohne Pagination: Single-User mit zweistelligen Fundzahlen pro
    Saison — eine Seitenlogik wäre Aufwand ohne Nutzen und würde den
    Offline-Abgleich im Planer verkomplizieren.
    """
    stmt = _select_finds()
    if bbox is not None:
        try:
            stmt = stmt.where(bbox_filter(Find.geom, bbox))
        except ValueError as exc:
            # 4xx: die Queue soll das nicht wiederholen, der Aufruf ist falsch.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
    if from_ is not None:
        stmt = stmt.where(Find.found_at >= from_)
    if to is not None:
        stmt = stmt.where(Find.found_at <= to)

    rows = db.execute(stmt.order_by(Find.found_at.desc())).all()
    return [_to_read(row) for row in rows]
