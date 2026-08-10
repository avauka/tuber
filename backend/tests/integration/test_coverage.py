"""Coverage-Berechnung — Spec §9, Invariante 5.

Geometrie-Eigenschaften werden gegen echtes PostGIS geprüft (ST_Buffer
auf geography), nicht gegen eine Python-Näherung.
"""

import math
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core import params
from app.models import Track
from app.models.enums import CoverageConfidenceEnum, TrackSourceEnum
from app.services.coverage import classify_confidence, create_coverage
from app.services.gpx import CleanResult, TrackPoint

pytestmark = pytest.mark.db

LAT0, LON0 = 50.53, 6.55
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT0))
T0 = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)


def _line_points(n: int, spacing_m: float, accuracy: float | None) -> tuple[TrackPoint, ...]:
    pts = []
    for i in range(n):
        pts.append(TrackPoint(
            lon=LON0 + (i * spacing_m) / M_PER_DEG_LON,
            lat=LAT0,
            time=T0 + timedelta(seconds=i),
            accuracy_m=accuracy,
            accuracy_source="meters" if accuracy is not None else "none",
        ))
    return tuple(pts)


def _insert_track(db, points) -> uuid.UUID:
    wkt = "LINESTRING(" + ",".join(f"{p.lon} {p.lat}" for p in points) + ")"
    t = Track(
        id=uuid.uuid4(), geom=wkt, source=TrackSourceEnum.gpx_import,
        recorded_from=points[0].time, recorded_to=points[-1].time,
        point_count=len(points),
    )
    db.add(t)
    db.commit()
    return t.id


# ---------------------------------------------------------- Confidence

def test_confidence_klassen_aus_params():
    assert classify_confidence(5.0) == CoverageConfidenceEnum.hoch
    assert classify_confidence(params.COVERAGE_CONFIDENCE_HIGH_MAX_M) == CoverageConfidenceEnum.hoch
    assert classify_confidence(15.0) == CoverageConfidenceEnum.mittel
    assert classify_confidence(35.0) == CoverageConfidenceEnum.niedrig


def test_confidence_ohne_genauigkeitsdaten_ist_niedrig():
    """ADR 0006: keine Genauigkeit im GPX -> ehrlich 'niedrig', nie raten."""
    assert classify_confidence(None) == CoverageConfidenceEnum.niedrig


# ------------------------------------------------------------ Geometrie

def test_coverage_flaeche_entspricht_buffer_um_linie(db_session):
    """100-m-Linie, 8-m-Buffer -> Fläche ~ L*2b + pi*b^2 (±10 %)."""
    points = _line_points(101, 1.0, accuracy=5.0)   # 100 m Länge
    track_id = _insert_track(db_session, points)
    clean = CleanResult(kept=points, dropped_accuracy=0, dropped_speed=0,
                        mean_accuracy_m=5.0, all_accuracy_missing=False)

    cov = create_coverage(db_session, track_id, clean)

    erwartet = 100.0 * 2 * params.COVERAGE_BUFFER_M + math.pi * params.COVERAGE_BUFFER_M ** 2
    area = db_session.execute(
        text("SELECT ST_Area(geom) FROM coverage WHERE id = :i"), {"i": cov.id}
    ).scalar()
    assert area == pytest.approx(erwartet, rel=0.10)
    assert cov.confidence == CoverageConfidenceEnum.hoch
    assert float(cov.buffer_m) == pytest.approx(params.COVERAGE_BUFFER_M)


def test_coverage_nutzt_bereinigte_punkte_nicht_rohtrack(db_session):
    """Invariante 5: Der Rohtrack (mit 200-m-Ausreisser) liegt in der DB —
    die Coverage wird trotzdem NUR aus den bereinigten Punkten gebaut."""
    clean_pts = list(_line_points(101, 1.0, accuracy=5.0))
    outlier = TrackPoint(lon=LON0 + 50 / M_PER_DEG_LON,
                         lat=LAT0 + 200 / M_PER_DEG_LAT,
                         time=T0 + timedelta(seconds=50),
                         accuracy_m=5.0, accuracy_source="meters")
    raw_pts = clean_pts[:50] + [outlier] + clean_pts[50:]
    track_id = _insert_track(db_session, raw_pts)  # Rohtrack MIT Ausreisser

    clean = CleanResult(kept=tuple(clean_pts), dropped_accuracy=0, dropped_speed=1,
                        mean_accuracy_m=5.0, all_accuracy_missing=False)
    cov = create_coverage(db_session, track_id, clean)

    # Läge der Ausreisser drin, wäre die Fläche um Größenordnung 200m*2*8m größer.
    erwartet = 100.0 * 2 * params.COVERAGE_BUFFER_M + math.pi * params.COVERAGE_BUFFER_M ** 2
    area = db_session.execute(
        text("SELECT ST_Area(geom) FROM coverage WHERE id = :i"), {"i": cov.id}
    ).scalar()
    assert area == pytest.approx(erwartet, rel=0.10)

    # Und der Rohtrack in der DB enthält den Ausreisser weiterhin (unverändert).
    raw_n = db_session.execute(
        text("SELECT ST_NumPoints(geom::geometry) FROM track WHERE id = :i"),
        {"i": track_id},
    ).scalar()
    assert raw_n == 102
