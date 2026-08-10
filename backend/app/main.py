"""FastAPI-App.

Fehlerformat: FastAPI-Standard-Bodies. Die Offline-Queue unterscheidet
retryable / nicht-retryable am Statuscode (4xx endgültig, 5xx und
Netzfehler wiederholen) — kein eigenes Fehlerschema.
"""

from fastapi import Depends, FastAPI

from app.api import areas, auth, conditions, coverage, finds, sessions, signals, tracks
from app.core.auth import require_session

# Globale Dependency statt Router-für-Router: Ein neuer Endpunkt ist damit von
# sich aus geschützt (ADR 0005). Ausnahmen stehen in PUBLIC_API_PATHS.
app = FastAPI(title="TUBER", dependencies=[Depends(require_session)])

app.include_router(auth.router)
app.include_router(finds.router)
app.include_router(signals.router)
app.include_router(tracks.router)
app.include_router(coverage.router)
app.include_router(areas.router)
app.include_router(sessions.router)
app.include_router(conditions.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
