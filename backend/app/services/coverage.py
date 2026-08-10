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

from sqlalchemy import func
from sqlalchemy.orm import Session as OrmSession

from app.core import params
from app.models.core import Coverage
from app.models.enums import CoverageConfidenceEnum
from app.services.gpx import CleanResult

SRID = 4326


def classify_confidence(mean_accuracy_m: float | None) -> CoverageConfidenceEnum:
    if mean_accuracy_m is None:
        # ADR 0006: ohne Genauigkeitsangabe wird nicht geraten, sondern
        # ehrlich die schlechteste Klasse vergeben.
        return CoverageConfidenceEnum.niedrig
    if mean_accuracy_m <= params.COVERAGE_CONFIDENCE_HIGH_MAX_M:
        return CoverageConfidenceEnum.hoch
    if mean_accuracy_m <= params.COVERAGE_CONFIDENCE_MEDIUM_MAX_M:
        return CoverageConfidenceEnum.mittel
    return CoverageConfidenceEnum.niedrig


def create_coverage(
    db: OrmSession, track_id: uuid.UUID, clean: CleanResult, buffer_m: float | None = None
) -> Coverage:
    """Legt eine coverage-Zeile an (ST_Buffer + Union über geography)
    und gibt das ORM-Objekt zurück."""
    if len(clean.kept) < 2:
        raise ValueError(
            f"Coverage braucht mindestens zwei bereinigte Punkte — vorhanden: {len(clean.kept)}."
        )

    width = params.COVERAGE_BUFFER_M if buffer_m is None else buffer_m

    # Die Linie entsteht aus clean.kept, NICHT aus track.geom (Invariante 5):
    # der Rohtrack enthält die verworfenen Ausreisser und behält sie auch.
    line_wkt = "LINESTRING(" + ", ".join(f"{p.lon} {p.lat}" for p in clean.kept) + ")"
    # Das WKT geht als gebundener Parameter in die Query, nicht als SQL-Literal.
    # Kein ST_Union hier: Spec §9 unioniert "über die Session", also über
    # mehrere Tracks hinweg — das ist Sache der Abfrageschicht. Pro Track
    # entsteht eine Fläche, passend zur POLYGON-Typisierung von coverage.geom.
    geom = func.ST_Buffer(func.ST_GeogFromText(f"SRID={SRID};{line_wkt}"), width)

    coverage = Coverage(
        track_id=track_id,
        geom=geom,
        buffer_m=width,
        covered_at=clean.kept[0].time.date(),
        confidence=classify_confidence(clean.mean_accuracy_m),
    )
    db.add(coverage)
    db.commit()
    # Zuruecklesen, damit geom und die Server-Defaults den gespeicherten Zustand
    # zeigen statt des noch unausgewerteten SQL-Ausdrucks.
    db.refresh(coverage)
    return coverage
