"""Schemas der Fund-Endpunkte (Spec §12)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core import params
from app.models import enums
from app.schemas.common import as_utc


class FindCreate(BaseModel):
    """Was die Feld-Queue schickt. Nachbearbeitung läuft später über PATCH.

    Unbekannte Felder werden bewusst ignoriert statt abgelehnt: Die
    Offline-Queue kann Payloads einer älteren oder neueren Client-Version
    nachspielen, und ein 4xx darauf wäre nach der Sync-Regel endgültig —
    der Eintrag ginge verloren. Serverseitig abgeleitete Felder wie
    revisit_due sind dadurch auch nicht von aussen setzbar.
    """

    client_uuid: UUID
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    # Invariante 1: Pflichtfeld ohne Default — ein Fund ohne Genauigkeits-
    # angabe wird nie gespeichert.
    # Invariante 2: oberhalb der Schwelle blockiert der Server das Loggen.
    # iOS ohne "Genauer Standort" meldet 3-9 km und wird so aussortiert.
    gps_accuracy_m: float = Field(gt=0.0, le=params.FIND_ACCURACY_BLOCK_M)
    found_at: datetime
    session_id: UUID | None = None
    notes: str | None = None

    @field_validator("found_at")
    @classmethod
    def _found_at_utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class FindRead(BaseModel):
    id: UUID
    client_uuid: UUID
    lat: float
    lon: float
    gps_accuracy_m: float
    found_at: datetime
    session_id: UUID | None
    species_guess: enums.ArtEnum
    species_confidence: enums.SpeciesConfidenceEnum
    phenotype: enums.PhenotypeEnum
    id_pending: bool
    maturity: enums.MaturityEnum
    calcium_reaction: enums.CalciumReactionEnum
    revisit_due: date | None
    notes: str | None
    created_at: datetime
