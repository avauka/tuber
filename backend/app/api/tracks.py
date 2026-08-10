"""Track-Import (Spec §9, §12).

Ablauf: parsen -> Rohtrack IMMER speichern (Invariante 5) -> bereinigen ->
Coverage. Der Rohtrack bleibt auch dann erhalten, wenn nach der Bereinigung
keine Fläche mehr entsteht.

Anders als die Feld-Endpunkte ist der Upload eine bewusste Nutzeraktion und
kein Queue-Replay. Ein erkanntes Duplikat wird deshalb ehrlich mit 409
abgelehnt statt still als idempotenter Treffer durchgewinkt.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.api.coverage import build_summary
from app.core.db import DbSession
from app.models.core import Session as SessionModel
from app.models.core import Track
from app.models.enums import TrackSourceEnum
from app.schemas.coverage import CoverageSummary
from app.schemas.tracks import SessionAssignment, TrackImportResult
from app.services.coverage import create_coverage
from app.services.gpx import ParsedTrack, TrackPoint, clean_track, parse_gpx

router = APIRouter(prefix="/api/tracks", tags=["tracks"])

SRID = 4326

# Ein realer Tagestrack liegt bei deutlich unter 1 MB. 10 MB ist grosszuegig
# und begrenzt trotzdem, was ein Upload an Speicher binden kann.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 64 * 1024

# Zwei Uploads gelten als dasselbe Material, wenn Start und Ende innerhalb
# dieser Toleranz liegen und die Punktzahl uebereinstimmt.
DUPLICATE_TOLERANCE_S = 60.0

# Zeitueberlappungen, die sich um weniger als das unterscheiden, gelten als
# gleich stark — sonst entscheidet Rechenrauschen ueber die Zuordnung.
SESSION_TIE_TOLERANCE_S = 1.0

# Ein LINESTRING braucht zwei Stuetzpunkte.
MIN_LINE_POINTS = 2


def _read_limited(upload: UploadFile) -> bytes:
    """Upload stueckweise lesen und bei Ueberschreitung abbrechen, statt
    erst alles einzulesen und dann die Groesse zu pruefen."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = upload.file.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"GPX-Datei groesser als {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _linestring_wkt(points: tuple[TrackPoint, ...]) -> str:
    return "LINESTRING(" + ", ".join(f"{p.lon} {p.lat}" for p in points) + ")"


def _mean_accuracy(points: tuple[TrackPoint, ...]) -> float | None:
    """Mittel ueber ALLE geparsten Punkte — der Track beschreibt den Rohzustand."""
    accuracies = [p.accuracy_m for p in points if p.accuracy_m is not None]
    return sum(accuracies) / len(accuracies) if accuracies else None


def _find_duplicate(
    db: OrmSession, recorded_from: datetime, recorded_to: datetime, point_count: int
) -> uuid.UUID | None:
    seconds_from = func.abs(func.extract("epoch", Track.recorded_from - recorded_from))
    seconds_to = func.abs(func.extract("epoch", Track.recorded_to - recorded_to))
    return db.execute(
        select(Track.id).where(
            Track.point_count == point_count,
            seconds_from <= DUPLICATE_TOLERANCE_S,
            seconds_to <= DUPLICATE_TOLERANCE_S,
        )
    ).scalar()


def _assign_session(
    db: OrmSession, recorded_from: datetime, recorded_to: datetime
) -> tuple[uuid.UUID | None, SessionAssignment]:
    """Session mit der groessten Zeitueberlappung gewinnt. Bei Gleichstand
    wird nichts zugeordnet — raten waere hier schlechter als offen lassen."""
    overlap_seconds = func.extract(
        "epoch",
        func.least(SessionModel.ended_at, recorded_to)
        - func.greatest(SessionModel.started_at, recorded_from),
    )
    rows = db.execute(
        select(SessionModel.id, overlap_seconds.label("overlap_s")).where(
            SessionModel.started_at.is_not(None), SessionModel.ended_at.is_not(None)
        )
    ).all()

    candidates = [
        (row.id, float(row.overlap_s))
        for row in rows
        if row.overlap_s is not None and float(row.overlap_s) > 0
    ]
    if not candidates:
        return None, "none"

    best = max(overlap for _, overlap in candidates)
    winners = [sid for sid, overlap in candidates if best - overlap <= SESSION_TIE_TOLERANCE_S]
    if len(winners) > 1:
        return None, "ambiguous"
    return winners[0], "unique"


def _parse_or_422(content: bytes) -> ParsedTrack:
    try:
        return parse_gpx(content)
    except ValueError as exc:
        # Deckt kaputtes XML, fehlende Zeitstempel und die
        # defusedxml-Abwehr ab (DefusedXmlException erbt von ValueError).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/import", response_model=TrackImportResult, status_code=status.HTTP_201_CREATED)
def import_track(
    db: DbSession,
    file: Annotated[UploadFile, File(description="GPX-Datei")],
) -> TrackImportResult:
    parsed = _parse_or_422(_read_limited(file))

    if len(parsed.points) < MIN_LINE_POINTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"GPX enthaelt {len(parsed.points)} Trackpunkte, mindestens "
            f"{MIN_LINE_POINTS} sind noetig.",
        )

    recorded_from = parsed.points[0].time
    recorded_to = parsed.points[-1].time
    point_count = len(parsed.points)

    duplicate_id = _find_duplicate(db, recorded_from, recorded_to, point_count)
    if duplicate_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Track mit gleichem Zeitfenster und gleicher Punktzahl "
                "ist bereits importiert.",
                "existing_track_id": str(duplicate_id),
            },
        )

    session_id, assignment = _assign_session(db, recorded_from, recorded_to)

    # Rohtrack unveraendert speichern, inklusive aller spaeter verworfenen
    # Ausreisser (Invariante 5).
    line = func.ST_GeogFromText(f"SRID={SRID};{_linestring_wkt(parsed.points)}")
    mean_accuracy_m = _mean_accuracy(parsed.points)
    track = Track(
        geom=line,
        source=TrackSourceEnum.gpx_import,
        source_filename=file.filename,
        recorded_from=recorded_from,
        recorded_to=recorded_to,
        point_count=point_count,
        mean_accuracy_m=mean_accuracy_m,
        length_m=func.ST_Length(line),
        session_id=session_id,
    )
    db.add(track)
    db.commit()

    # Laenge kommt aus PostGIS und ist der einzige Wert, den wir nicht schon
    # als lokale Groesse haben.
    length_m = float(
        db.execute(select(func.ST_Length(Track.geom)).where(Track.id == track.id)).scalar_one()
    )

    clean = clean_track(parsed.points)
    coverage: CoverageSummary | None = None
    skipped_reason: str | None = None
    if len(clean.kept) < MIN_LINE_POINTS:
        # Der Rohtrack bleibt gespeichert — nur die Flaeche entfaellt.
        skipped_reason = (
            f"Nach der Bereinigung blieben {len(clean.kept)} Punkte uebrig, "
            f"mindestens {MIN_LINE_POINTS} sind fuer eine Flaeche noetig."
        )
    else:
        coverage = build_summary(db, create_coverage(db, track.id, clean))

    # Bewusst aus den lokalen Werten gebaut, nicht vom ORM-Objekt zurueckgelesen:
    # die Spalten sind nullable, die hier verwendeten Groessen sind es nicht.
    return TrackImportResult(
        track_id=track.id,
        source_filename=file.filename,
        point_count=point_count,
        length_m=length_m,
        mean_accuracy_m=mean_accuracy_m,
        recorded_from=recorded_from,
        recorded_to=recorded_to,
        session_id=session_id,
        session_assignment=assignment,
        dropped_accuracy=clean.dropped_accuracy,
        dropped_speed=clean.dropped_speed,
        kept_count=len(clean.kept),
        coverage=coverage,
        coverage_skipped_reason=skipped_reason,
    )
