"""FastAPI-App. Feld-Endpunkte sind Stubs (501), bis die roten Tests in
tests/integration/test_sync_idempotency.py grün implementiert werden."""

from fastapi import FastAPI, Response

app = FastAPI(title="TUBER")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/finds")
def create_find(payload: dict, response: Response) -> dict:  # pragma: no cover
    response.status_code = 501
    return {"detail": "not implemented — siehe tests/integration/test_sync_idempotency.py"}


@app.post("/api/signals")
def create_signal(payload: dict, response: Response) -> dict:  # pragma: no cover
    response.status_code = 501
    return {"detail": "not implemented"}
