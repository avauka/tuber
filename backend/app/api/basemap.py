"""Auslieferung der Basiskarte (ADR 0002, AP10b).

Eine einzelne PMTiles-Datei auf dem Volume, gelesen per HTTP-Range-Requests:
MapLibre holt sich über das pmtiles-Protokoll nur die Kacheln, die es gerade
braucht, statt 208 MB am Stück. Die Route liegt bewusst unter `/api/` und
damit hinter der globalen Auth-Dependency (ADR 0005) — es ist eine
selbstgehostete Datei, kein öffentlicher Tile-Server.

Wer hier etwas ändert, achte auf zwei Dinge:

1. **Keine Kompression auf dieser Route.** Die Kacheln im Archiv sind bereits
   gzip-komprimiert; ein zweites gzip über eine Teilantwort verschöbe die
   Byte-Offsets, auf die PMTiles baut. Käme je eine `GZipMiddleware` dazu,
   muss diese Route ausgenommen werden — `test_basemap.py` hält das fest.
2. **`FileResponse` beantwortet Range-Requests selbst** (Starlette ≥ 0.39:
   206, `Content-Range`, 416 bei unsinnigem Bereich). Wird das je durch eine
   eigene Antwort ersetzt, ist die Karte tot, ohne dass ein Fehler auftaucht.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.schemas.basemap import BasemapMeta
from app.services.basemap import ARCHIVE_NAME, BasemapError, archive_path, read_meta

router = APIRouter(prefix="/api/basemap", tags=["basemap"])

# Kein registrierter Medientyp fuer PMTiles; octet-stream ist die ehrliche
# Angabe und verhindert zusammen mit nosniff jedes Raten des Browsers.
MEDIA_TYPE = "application/octet-stream"


def _nicht_vorhanden(detail: str) -> HTTPException:
    """503, nicht 500.

    Die Karte fehlt, weil der Extract-Job noch nicht gelaufen ist oder das
    Volume nicht hängt — beides ein vorübergehender Zustand des Dienstes und
    kein Programmfehler. Der Client darf es später wieder versuchen.
    """
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


@router.get(f"/{ARCHIVE_NAME}")
def basemap_archive() -> FileResponse:
    pfad = archive_path()
    if not pfad.is_file():
        raise _nicht_vorhanden(
            f"Basiskarte liegt nicht unter {pfad}. Der Extract-Job ist noch nicht "
            "gelaufen (siehe infra/railway/basemap-extract.md)."
        )
    return FileResponse(pfad, media_type=MEDIA_TYPE)


@router.get("/meta", response_model=BasemapMeta)
def basemap_meta() -> BasemapMeta:
    """Datenstand der abgelegten Karte — Pflichtangabe der Attribution."""
    try:
        return BasemapMeta(**read_meta())
    except BasemapError as exc:
        raise _nicht_vorhanden(str(exc)) from exc
    except ValidationError as exc:
        raise _nicht_vorhanden(
            f"Metadaten der Basiskarte sind unvollstaendig: {exc.error_count()} Feld(er) "
            "passen nicht. Extract-Job erneut laufen lassen."
        ) from exc
