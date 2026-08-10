"""Coverage-Endpunkt (Spec §12).

Liefert ein Polygon je Track. Spec §9 unioniert "ueber die Session" — das
bleibt bewusst eine Sache der Abfrage bzw. der Darstellung; gespeichert wird
keine Session-Union.
"""

import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.api.common import bbox_filter
from app.core.db import DbSession
from app.models.core import Coverage
from app.models.enums import CoverageConfidenceEnum
from app.schemas.coverage import CoverageFeature, CoverageSummary

router = APIRouter(prefix="/api/coverage", tags=["coverage"])


def _confidence(value: CoverageConfidenceEnum | None) -> CoverageConfidenceEnum:
    """Die Spalte ist nullable, create_coverage setzt sie aber immer. Fehlt
    sie doch, ist 'niedrig' die ehrliche Antwort (ADR 0006) — nicht raten."""
    return value if value is not None else CoverageConfidenceEnum.niedrig


def build_summary(db: OrmSession, coverage: Coverage) -> CoverageSummary:
    """Coverage-Kurzfassung inklusive Flaeche. Auch vom Track-Import genutzt."""
    area = db.execute(
        select(func.ST_Area(Coverage.geom)).where(Coverage.id == coverage.id)
    ).scalar_one()
    return CoverageSummary(
        id=coverage.id,
        track_id=coverage.track_id,
        buffer_m=float(coverage.buffer_m),
        covered_at=coverage.covered_at,
        confidence=_confidence(coverage.confidence),
        area_m2=float(area),
    )


@router.get("", response_model=list[CoverageFeature])
def list_coverage(
    db: DbSession,
    bbox: Annotated[
        str | None, Query(description="minLon,minLat,maxLon,maxLat (EPSG:4326)")
    ] = None,
) -> list[CoverageFeature]:
    stmt = select(
        Coverage,
        func.ST_Area(Coverage.geom).label("area_m2"),
        func.ST_AsGeoJSON(Coverage.geom).label("geojson"),
    )
    if bbox is not None:
        try:
            stmt = stmt.where(bbox_filter(Coverage.geom, bbox))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

    rows = db.execute(stmt.order_by(Coverage.covered_at.desc())).all()
    return [
        CoverageFeature(
            id=coverage.id,
            track_id=coverage.track_id,
            buffer_m=float(coverage.buffer_m),
            covered_at=coverage.covered_at,
            confidence=_confidence(coverage.confidence),
            area_m2=float(area_m2),
            geometry=json.loads(geojson),
        )
        for coverage, area_m2, geojson in rows
    ]
