"""Signal-Endpunkte (Spec §4). Idempotent über client_uuid (Invariante 3)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import Row, Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import bbox_filter, lat_column, lon_column, point
from app.core.db import DbSession
from app.models.core import Signal
from app.schemas.signals import SignalCreate, SignalRead

router = APIRouter(prefix="/api/signals", tags=["signals"])


def _select_signals() -> Select:
    return select(Signal, lat_column(Signal.geom), lon_column(Signal.geom))


def _row_by_client_uuid(db: Session, client_uuid: UUID) -> Row | None:
    return db.execute(_select_signals().where(Signal.client_uuid == client_uuid)).first()


def _to_read(row: Row) -> SignalRead:
    signal, lat, lon = row
    return SignalRead(
        id=signal.id,
        client_uuid=signal.client_uuid,
        lat=lat,
        lon=lon,
        signal_type=signal.signal_type,
        observed_at=signal.observed_at,
        dog_confidence=signal.dog_confidence,
        session_id=signal.session_id,
        notes=signal.notes,
    )


@router.post("", response_model=SignalRead, status_code=status.HTTP_201_CREATED)
def create_signal(payload: SignalCreate, response: Response, db: DbSession) -> SignalRead:
    """Legt ein Signal an. Wiederholte POSTs mit derselben client_uuid
    liefern denselben Datensatz mit 200 statt eines Duplikats."""
    existing = _row_by_client_uuid(db, payload.client_uuid)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _to_read(existing)

    signal = Signal(
        client_uuid=payload.client_uuid,
        geom=point(payload.lat, payload.lon),
        signal_type=payload.signal_type,
        observed_at=payload.observed_at,
        dog_confidence=payload.dog_confidence,
        session_id=payload.session_id,
        notes=payload.notes,
    )
    db.add(signal)
    try:
        db.commit()
    except IntegrityError:
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
            detail="Signal nach dem Commit nicht auffindbar.",
        )
    return _to_read(created)


@router.get("", response_model=list[SignalRead])
def list_signals(
    db: DbSession,
    bbox: Annotated[
        str | None, Query(description="minLon,minLat,maxLon,maxLat (EPSG:4326)")
    ] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> list[SignalRead]:
    """Alle Signale, neueste zuerst. Aufbau wie GET /api/finds.

    Ebenfalls ohne Pagination: dieselbe Begruendung wie bei den Funden —
    Single-User, zweistellige Zahlen je Saison.

    `observed_at` ist im Gegensatz zu `found_at` optional (Spec §4). Zeilen
    ohne Zeitpunkt stehen deshalb am Ende und nicht, wie es PostgreSQL bei
    DESC von sich aus tut, ganz oben.
    """
    stmt = _select_signals()
    if bbox is not None:
        try:
            stmt = stmt.where(bbox_filter(Signal.geom, bbox))
        except ValueError as exc:
            # 4xx: die Queue soll das nicht wiederholen, der Aufruf ist falsch.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
    if from_ is not None:
        stmt = stmt.where(Signal.observed_at >= from_)
    if to is not None:
        stmt = stmt.where(Signal.observed_at <= to)

    rows = db.execute(stmt.order_by(Signal.observed_at.desc().nullslast())).all()
    return [_to_read(row) for row in rows]
