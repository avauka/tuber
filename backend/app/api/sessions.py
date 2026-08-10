"""Session-Endpunkte (Spec §5, §12).

Beim Beenden werden die Bedingungen eingefroren. "Eingefroren" ist woertlich
gemeint: ein zweiter Abschluss rechnet nichts neu, sondern liefert die
bestehenden Werte zurueck. Sonst haengt der historische Score davon ab, wann
zuletzt jemand auf den Knopf gedrueckt hat.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.core.db import DbSession
from app.models.core import Area
from app.models.core import Session as SessionModel
from app.schemas.sessions import SessionCreate, SessionEnd, SessionEndResult, SessionRead
from app.services.session_conditions import freeze_conditions

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

ALREADY_ENDED_REASON = (
    "Session war bereits beendet — die Werte sind eingefroren und wurden nicht neu berechnet."
)


def _to_read(session: SessionModel) -> SessionRead:
    return SessionRead(**_read_fields(session))


def _read_fields(session: SessionModel) -> dict:
    return {
        "id": session.id,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "area_id": session.area_id,
        "area_label": session.area_label,
        "dog_name": session.dog_name,
        "dog_work_minutes": session.dog_work_minutes,
        "notes": session.notes,
        "subjective_rating": session.subjective_rating,
        "temperature_c": _as_float(session.temperature_c),
        "wind_kmh": _as_float(session.wind_kmh),
        "soil_moisture_0_7": _as_float(session.soil_moisture_0_7),
        "precip_prev_7d_mm": _as_float(session.precip_prev_7d_mm),
        "conditions_score": _as_float(session.conditions_score),
    }


def _as_float(value: float | None) -> float | None:
    return float(value) if value is not None else None


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate, db: DbSession) -> SessionRead:
    if payload.area_id is not None and db.get(Area, payload.area_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Gebiet {payload.area_id} existiert nicht.",
        )

    session = SessionModel(
        started_at=payload.started_at or datetime.now(UTC),
        area_id=payload.area_id,
        area_label=payload.area_label,
        dog_name=payload.dog_name,
        notes=payload.notes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _to_read(session)


@router.patch("/{session_id}/end", response_model=SessionEndResult)
def end_session(
    session_id: UUID, payload: SessionEnd, response: Response, db: DbSession
) -> SessionEndResult:
    session = db.get(SessionModel, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} nicht gefunden."
        )

    if session.ended_at is not None:
        # Eingefroren heisst eingefroren — nichts neu rechnen, nichts ueberschreiben.
        response.status_code = status.HTTP_200_OK
        return SessionEndResult(
            **_read_fields(session), already_ended=True, score_reason=ALREADY_ENDED_REASON
        )

    ended_at = payload.ended_at or datetime.now(UTC)
    frozen = freeze_conditions(db, session.area_id, ended_at.date())

    session.ended_at = ended_at
    if payload.dog_work_minutes is not None:
        session.dog_work_minutes = payload.dog_work_minutes
    if payload.subjective_rating is not None:
        session.subjective_rating = payload.subjective_rating
    if payload.notes is not None:
        session.notes = payload.notes

    session.temperature_c = frozen.temperature_c
    session.wind_kmh = frozen.wind_kmh
    session.soil_moisture_0_7 = frozen.soil_moisture_0_7
    session.precip_prev_7d_mm = frozen.precip_prev_7d_mm
    session.conditions_score = frozen.conditions_score

    db.commit()
    db.refresh(session)
    return SessionEndResult(
        **_read_fields(session), already_ended=False, score_reason=frozen.score_reason
    )
