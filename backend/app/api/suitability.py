"""Eignungskarte ausliefern und entgegennehmen (ADR 0008, AP17a §5, §6).

Drei Dinge:

* die Kacheln (`FileResponse`, Range-fähig, wie die Basiskarte),
* die Metadatei mit Gewichtssatz, Faktoren und Quellen,
* und den Upload, über den die lokal erzeugte Datei auf das Volume kommt.

**Kein Endpunkt für den Gewichtssatz** (AP17a-Nachtrag B6). Er hätte den
aktiven Satz aus der Datenbank geliefert, während der Planer die
tatsächlich angewandten Gewichte aus `suitability.meta.json` liest — und
nur die stehen in den Kacheln. Nach einer Umgewichtung ohne Pipelinelauf
lieferte der Endpunkt eine Zahl, die zu keiner ausgelieferten Karte
gehört. Tabelle und Migration bleiben, sie sind der Versionierungsanker;
zurück kommt der Endpunkt mit der Settings-Seite, die ihn braucht.

**Warum es hier einen Schreib-Endpunkt gibt, bei der Basiskarte aber nicht.**
Die Basiskarte holt sich der Container selbst aus dem Netz (AP10a); ein
Upload wäre dort ein Weg gewesen, den niemand braucht. Die Eignungskarte
entsteht dagegen lokal aus Landesdaten, die den Server nie berühren sollen
(ADR 0008 §8) — sie kann nur vom Rechner des Nutzers kommen.

Wie bei der Basiskarte gilt: **keine Kompressions-Middleware auf der
Kachel-Route.** Die Kacheln sind im Archiv bereits gzip-komprimiert, ein
zweites gzip über eine Teilantwort verschöbe die Byte-Offsets.
"""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.schemas.suitability import SuitabilityMeta, UploadErgebnis
from app.services.suitability import (
    TILES_ROUTE,
    SuitabilityError,
    read_meta,
    speichere_upload,
    tiles_path,
)

router = APIRouter(prefix="/api/suitability", tags=["suitability"])

MEDIA_TYPE = "application/octet-stream"


def _nicht_vorhanden(detail: str) -> HTTPException:
    """503, nicht 500 — die Karte fehlt, der Dienst ist in Ordnung."""
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


@router.get(f"/{TILES_ROUTE}")
def eignungs_kacheln() -> FileResponse:
    pfad = tiles_path()
    if not pfad.is_file():
        raise _nicht_vorhanden(
            f"Eignungskarte liegt nicht unter {pfad}. Sie entsteht lokal in "
            "geoprocessing/ und wird über POST /api/suitability/upload abgelegt."
        )
    return FileResponse(pfad, media_type=MEDIA_TYPE)


@router.get("/meta", response_model=SuitabilityMeta)
def eignungs_meta() -> SuitabilityMeta:
    """Womit wurde gerechnet — Gewichtssatz, Faktoren, Quellen.

    Der Planer braucht das, um ehrlich anzuzeigen, worauf der Score beruht.
    Solange nur ein Faktor enthalten ist, muss die Karte das sagen.
    """
    try:
        return SuitabilityMeta(**read_meta())
    except SuitabilityError as exc:
        raise _nicht_vorhanden(str(exc)) from exc
    except ValidationError as exc:
        raise _nicht_vorhanden(
            f"Metadaten der Eignungskarte sind unvollstaendig: {exc.error_count()} "
            "Feld(er) passen nicht. Stufe 2 erneut laufen lassen."
        ) from exc


@router.post("/upload", response_model=UploadErgebnis, status_code=status.HTTP_201_CREATED)
async def kacheln_hochladen(
    tiles: Annotated[UploadFile, File(description="suitability.pmtiles aus geoprocessing/out/")],
    meta: Annotated[UploadFile, File(description="suitability.meta.json aus geoprocessing/out/")],
) -> UploadErgebnis:
    """Kacheln und Metadatei auf das Volume legen.

    Beide zusammen in einem Aufruf, damit auf dem Volume nie Kacheln ohne
    passende Metadatei liegen — die Anzeige würde sonst nicht mehr sagen
    können, worauf sie beruht.

    Hinter der globalen Auth-Dependency (ADR 0005): Es gibt genau einen
    Nutzer, und der ist angemeldet.
    """
    meta_rohtext = (await meta.read()).decode("utf-8", errors="replace")
    try:
        ergebnis = speichere_upload(tiles.file, meta_rohtext, groesse=tiles.size)
    except SuitabilityError as exc:
        # Fehlkonfiguration oder falsche Datei ist ein Fehler des Aufrufers,
        # nicht des Dienstes — 422, damit ein Skript nicht stur wiederholt.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return UploadErgebnis(**ergebnis)
