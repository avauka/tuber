"""Schemas des Track-Imports (Spec §9, §12)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.coverage import CoverageSummary

# "unique": genau eine Session überlappt am stärksten.
# "none":   keine Session überlappt zeitlich.
# "ambiguous": mehrere Sessions überlappen gleich stark — die Zuordnung
#              trifft später der Nutzer im Planer, nicht der Server per Münzwurf.
SessionAssignment = Literal["unique", "none", "ambiguous"]


class TrackImportResult(BaseModel):
    """Die Track-Felder beschreiben den ROHEN Track (Invariante 5); die
    Coverage-Confidence stammt dagegen aus den bereinigten Punkten."""

    track_id: UUID
    source_filename: str | None
    point_count: int
    length_m: float
    mean_accuracy_m: float | None
    recorded_from: datetime
    recorded_to: datetime

    session_id: UUID | None
    session_assignment: SessionAssignment

    dropped_accuracy: int
    dropped_speed: int
    kept_count: int

    coverage: CoverageSummary | None
    coverage_skipped_reason: str | None
