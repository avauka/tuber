"""FastAPI-App.

Fehlerformat: FastAPI-Standard-Bodies. Die Offline-Queue unterscheidet
retryable / nicht-retryable am Statuscode (4xx endgültig, 5xx und
Netzfehler wiederholen) — kein eigenes Fehlerschema.
"""

import os

from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from app.api import (
    areas,
    auth,
    backups,
    conditions,
    coverage,
    finds,
    sessions,
    signals,
    tracks,
)
from app.core.auth import require_session
from app.core.http_security import SecurityHeadersMiddleware

DOCS_PATH = "/api/docs"
OPENAPI_PATH = "/api/openapi.json"


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

    if docs_enabled():
        app.include_router(_docs_router(app))

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
