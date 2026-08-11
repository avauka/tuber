"""Schemas der Backup-Endpunkte (ADR 0004, AP15)."""

from datetime import datetime

from pydantic import BaseModel


class BackupEntry(BaseModel):
    name: str
    size_bytes: int
    created_at: datetime
    downloaded_at: datetime | None
    stale: bool


class BackupList(BaseModel):
    """`stale_count` ist der Wert, der ins Planer-UI gehört: Er sagt, ob
    überhaupt eine aktuelle Kopie ausserhalb von Railway liegt."""

    entries: list[BackupEntry]
    stale_count: int
    keep: int
