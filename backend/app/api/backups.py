"""Backup-Endpunkte (ADR 0004, AP15).

Der Download ist der eigentliche Zweck: Ein Dump auf dem Railway-Volume
schuetzt nicht gegen Projekt- oder Accountverlust. Erst die Kopie auf einem
Geraet, das Railway nicht gehoert, ist ein Backup — deshalb wird jeder
Download festgehalten und ein zu lange nicht geholter Stand als `stale`
gemeldet.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from starlette.background import BackgroundTask

from app.core.db import DbSession, get_sessionmaker
from app.jobs.backup_dump import run_backup
from app.models.core import BackupDownload
from app.schemas.backups import BackupEntry, BackupList
from app.services.backups import (
    KEEP_BACKUPS,
    BackupError,
    created_at,
    is_stale,
    list_backups,
    resolve,
)

router = APIRouter(prefix="/api/backups", tags=["backups"])


def _letzte_downloads(db: DbSession, namen: list[str]) -> dict[str, datetime]:
    if not namen:
        return {}
    zeilen = db.execute(
        select(BackupDownload.filename, func.max(BackupDownload.downloaded_at))
        .where(BackupDownload.filename.in_(namen))
        .group_by(BackupDownload.filename)
    ).all()
    return {name: zeitpunkt for name, zeitpunkt in zeilen}


@router.get("", response_model=BackupList)
def list_backup_files(db: DbSession) -> BackupList:
    pfade = list_backups()
    downloads = _letzte_downloads(db, [p.name for p in pfade])
    jetzt = datetime.now(UTC)

    eintraege = [
        BackupEntry(
            name=pfad.name,
            size_bytes=pfad.stat().st_size,
            created_at=created_at(pfad.name),
            downloaded_at=downloads.get(pfad.name),
            stale=is_stale(pfad.name, downloads.get(pfad.name), jetzt),
        )
        for pfad in pfade
    ]
    return BackupList(
        entries=eintraege,
        stale_count=sum(1 for e in eintraege if e.stale),
        keep=KEEP_BACKUPS,
    )


@router.post("/create", response_model=BackupEntry, status_code=status.HTTP_201_CREATED)
def create_backup() -> BackupEntry:
    """Loest den Dump aus — denselben Codepfad wie `python -m app.jobs.backup_dump`.

    Der Dump laeuft hier im API-Service, weil Railway keine geteilten Volumes
    kennt (ADR 0004, AP15.1): Das Volume haengt am API-Service, also muss der
    Schreiber dort laufen. Ausgeloest wird per Cron ueber HTTP.

    Erreichbar mit Sitzungs-Cookie oder mit dem Bearer-Token aus
    BACKUP_TRIGGER_TOKEN; die Pruefung sitzt in der globalen Auth-Dependency.
    """
    try:
        ergebnis = run_backup()
    except BackupError as exc:
        # Fehlende Passphrase oder fehlendes Programm ist Fehlkonfiguration
        # des Dienstes, nicht ein Fehler des Aufrufers.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    pfad = ergebnis.path
    return BackupEntry(
        name=pfad.name,
        size_bytes=pfad.stat().st_size,
        created_at=created_at(pfad.name),
        downloaded_at=None,
        # Frisch erzeugt und noch nicht heruntergeladen: noch nicht veraltet,
        # aber eben auch noch nicht ausserhalb von Railway.
        stale=is_stale(pfad.name, None),
    )


def _download_festhalten(name: str) -> None:
    """Laeuft erst, nachdem die Antwort vollstaendig raus ist.

    Vorher zu buchen hiesse, einen abgebrochenen Download als Sicherung zu
    zaehlen — genau der Fehler, den `stale` verhindern soll. Eigene Session,
    weil die des Requests zu diesem Zeitpunkt geschlossen ist.
    """
    with get_sessionmaker()() as db:
        db.add(BackupDownload(id=uuid.uuid4(), filename=name, downloaded_at=datetime.now(UTC)))
        db.commit()


@router.get("/{name}")
def download_backup(name: str) -> FileResponse:
    try:
        pfad = resolve(name)
    except BackupError as exc:
        # Unzulaessiger Name und nicht vorhandene Datei fuehren beide zu 404:
        # Ein 400 fuer den einen Fall wuerde verraten, welche Namen die
        # Pruefung passieren.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # FileResponse liest in Bloecken, statt die Datei in den Speicher zu holen —
    # ein Dump kann groesser sein als der Container an RAM hat.
    return FileResponse(
        pfad,
        media_type="application/octet-stream",
        filename=pfad.name,
        background=BackgroundTask(_download_festhalten, pfad.name),
    )
