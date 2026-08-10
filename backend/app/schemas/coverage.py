"""Schemas der Coverage-Endpunkte (Spec §9, §12)."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import CoverageConfidenceEnum


class CoverageSummary(BaseModel):
    """Coverage ohne Geometrie — für die Antwort direkt nach dem Import."""

    id: UUID
    track_id: UUID | None
    buffer_m: float
    covered_at: date | None
    confidence: CoverageConfidenceEnum
    area_m2: float


class CoverageFeature(CoverageSummary):
    """Coverage mit Polygon für die Karte. Ein Eintrag je Track — Spec §9
    unioniert erst auf Session-Ebene, und das bleibt Sache der Abfrage."""

    geometry: dict
