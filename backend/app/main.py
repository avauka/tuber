"""FastAPI-App.

Fehlerformat: FastAPI-Standard-Bodies. Die Offline-Queue unterscheidet
retryable / nicht-retryable am Statuscode (4xx endgültig, 5xx und
Netzfehler wiederholen) — kein eigenes Fehlerschema.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse

from app.api import (
    areas,
    auth,
    backups,
    basemap,
    conditions,
    coverage,
    finds,
    sessions,
    signals,
    suitability,
    tracks,
)
from app.core.auth import require_session
from app.core.http_security import SecurityHeadersMiddleware

DOCS_PATH = "/api/docs"
OPENAPI_PATH = "/api/openapi.json"

# Das gebaute Frontend (AP10b). Im Image kopiert die Node-Stage hierhin;
# lokal ist das Verzeichnis leer, solange der Vite-Dev-Server laeuft — dann
# bleibt die App reine API.
DEFAULT_FRONTEND_DIST = "/app/static"


def docs_enabled() -> bool:
    """Standard: aus. Die Schema-Oberfläche ist die vollständige Landkarte
    der API und gehört nicht ungefragt ins offene Netz."""
    return os.environ.get("DOCS_ENABLED", "").strip().lower() == "true"


def _docs_router(app: FastAPI) -> APIRouter:
    """Docs als echte API-Routen unter /api/.

    FastAPIs eingebaute Docs-Routen sind einfache Starlette-Routen — die
    globale Dependency greift dort nicht. Selbst registriert sind es
    APIRoutes, und damit gilt der Auth-Schutz wie für jeden anderen
    /api/-Endpunkt.
    """
    router = APIRouter(include_in_schema=False)

    @router.get(OPENAPI_PATH)
    def openapi_schema() -> dict:
        return app.openapi()

    @router.get(DOCS_PATH)
    def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url=OPENAPI_PATH, title="TUBER — API")

    return router


def frontend_dist() -> Path:
    return Path(os.environ.get("FRONTEND_DIST", DEFAULT_FRONTEND_DIST))


def _mount_frontend(app: FastAPI) -> None:
    """Das gebaute Frontend von derselben Origin ausliefern (AP10b).

    Gleiche Origin, weil das Sitzungs-Cookie httpOnly und SameSite=Lax ist
    (ADR 0005): So geht es ohne CORS-Konstruktion mit, und die CSP bleibt eng.

    Registriert wird das **nach** allen API-Routern. Die Reihenfolge ist der
    ganze Schutz davor, dass `/api/*` beschattet wird — deshalb faengt der
    Fallback unbekannte `/api/`-Pfade ausdruecklich ab, statt ihnen die
    index.html zu geben. Ein Client, der auf einen Tippfehler im Pfad eine
    HTML-Seite mit Status 200 bekommt, sucht den Fehler an der falschen
    Stelle.

    Die Shell selbst ist oeffentlich — sonst waere die Login-Ansicht nicht
    erreichbar. `require_session` greift ohnehin nur unter `/api/`; die Daten
    dahinter bleiben geschuetzt.
    """
    verzeichnis = frontend_dist().resolve()
    index = verzeichnis / "index.html"
    if not index.is_file():
        return

    @app.get("/{pfad:path}", include_in_schema=False)
    def spa(pfad: str) -> FileResponse:
        if pfad.startswith("api/"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Unbekannter API-Pfad: /{pfad}"
            )

        datei = (verzeichnis / pfad).resolve()
        # is_relative_to faengt ab, was ueber ../ oder Symlinks aus dem
        # Build-Verzeichnis herausfuehren wuerde.
        if pfad and datei.is_file() and datei.is_relative_to(verzeichnis):
            return FileResponse(datei)

        # Alles Uebrige ist eine Route der SPA (z. B. /planer nach einem
        # Neuladen) und bekommt die Shell.
        return FileResponse(index)


def create_app() -> FastAPI:
    # Globale Dependency statt Router-für-Router: Ein neuer Endpunkt ist damit
    # von sich aus geschützt (ADR 0005). Ausnahmen: PUBLIC_API_PATHS.
    app = FastAPI(
        title="TUBER",
        dependencies=[Depends(require_session)],
        # Die eingebauten Pfade bleiben immer aus; aktiviert werden sie unter
        # /api/ und damit hinter der Auth.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(auth.router)
    app.include_router(finds.router)
    app.include_router(signals.router)
    app.include_router(tracks.router)
    app.include_router(coverage.router)
    app.include_router(areas.router)
    app.include_router(sessions.router)
    app.include_router(conditions.router)
    app.include_router(backups.router)
    app.include_router(basemap.router)
    app.include_router(suitability.router)

    if docs_enabled():
        app.include_router(_docs_router(app))

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    # Zuletzt, damit keine API-Route beschattet wird.
    _mount_frontend(app)

    return app


app = create_app()
