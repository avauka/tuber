"""Schemas der Signal-Endpunkte (Spec §4, Lernkreislauf)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models import enums
from app.schemas.common import as_utc


class SignalCreate(BaseModel):
    """Signal ohne Fund. Keine Genauigkeitsschwelle: Invariante 1/2 gelten
    dem Fund, und das Datenmodell führt für Signale keine GPS-Genauigkeit."""

    client_uuid: UUID
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    signal_type: enums.SignalTypeEnum
    observed_at: datetime | None = None
    dog_confidence: enums.DogConfidenceEnum | None = None
    session_id: UUID | None = None
    notes: str | None = None

    @field_validator("observed_at")
    @classmethod
    def _observed_at_utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None


class SignalRead(BaseModel):
    id: UUID
    client_uuid: UUID
    lat: float
    lon: float
    signal_type: enums.SignalTypeEnum
    observed_at: datetime | None
    dog_confidence: enums.DogConfidenceEnum | None
    session_id: UUID | None
    notes: str | None
