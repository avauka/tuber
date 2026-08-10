"""Schemas der Session-Endpunkte (Spec §4, §5, §12)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.models import enums
from app.schemas.common import as_utc


class SessionCreate(BaseModel):
    started_at: datetime | None = None
    area_id: UUID | None = None
    area_label: str | None = None
    dog_name: str | None = None
    notes: str | None = None

    @field_validator("started_at")
    @classmethod
    def _started_at_utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None


class SessionEnd(BaseModel):
    ended_at: datetime | None = None
    dog_work_minutes: int | None = None
    subjective_rating: enums.SubjectiveRatingEnum | None = None
    notes: str | None = None

    @field_validator("ended_at")
    @classmethod
    def _ended_at_utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None


class SessionRead(BaseModel):
    id: UUID
    started_at: datetime | None
    ended_at: datetime | None
    area_id: UUID | None
    area_label: str | None
    dog_name: str | None
    dog_work_minutes: int | None
    notes: str | None
    subjective_rating: enums.SubjectiveRatingEnum | None

    # Beim Ende eingefroren (Spec §5).
    temperature_c: float | None
    wind_kmh: float | None
    soil_moisture_0_7: float | None
    precip_prev_7d_mm: float | None
    conditions_score: float | None


class SessionEndResult(SessionRead):
    """already_ended trennt den ersten Abschluss vom idempotenten Wiederholer.

    score_reason nennt im Klartext, warum kein Score entstanden ist — oder
    dass gar nicht neu gerechnet wurde, weil die Werte schon eingefroren sind.
    """

    already_ended: bool
    score_reason: str | None
