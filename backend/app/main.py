"""FastAPI-App.

Fehlerformat: FastAPI-Standard-Bodies. Die Offline-Queue unterscheidet
retryable / nicht-retryable am Statuscode (4xx endgültig, 5xx und
Netzfehler wiederholen) — kein eigenes Fehlerschema.
"""

from fastapi import FastAPI

from app.api import coverage, finds, signals, tracks

app = FastAPI(title="TUBER")

app.include_router(finds.router)
app.include_router(signals.router)
app.include_router(tracks.router)
app.include_router(coverage.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
