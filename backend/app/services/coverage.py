"""Coverage-Berechnung (Spec §9, Invariante 5).

VERTRAG (durch tests/integration/test_coverage.py fixiert):
- Coverage entsteht AUSSCHLIESSLICH aus einem CleanResult (bereinigte
  Punkte), nie aus dem Rohtrack.
- Buffer per ST_Buffer auf geography (Spec), default params.COVERAGE_BUFFER_M.
- Confidence aus mean_accuracy_m des CleanResult:
    <= COVERAGE_CONFIDENCE_HIGH_MAX_M   -> hoch
    <= COVERAGE_CONFIDENCE_MEDIUM_MAX_M -> mittel
    sonst oder None (keine Genauigkeitsdaten) -> niedrig
"""

import uuid

from sqlalchemy.orm import Session as OrmSession

from app.models.enums import CoverageConfidenceEnum
from app.services.gpx import CleanResult


def classify_confidence(mean_accuracy_m: float | None) -> CoverageConfidenceEnum:
    raise NotImplementedError


def create_coverage(
    db: OrmSession, track_id: uuid.UUID, clean: CleanResult, buffer_m: float | None = None
):
    """Legt eine coverage-Zeile an (ST_Buffer + Union über geography)
    und gibt das ORM-Objekt zurück."""
    raise NotImplementedError
