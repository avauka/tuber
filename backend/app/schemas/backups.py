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
    überhaupt eine aktuelle Kopie ausserhalb von Railway liegt.

    Die `disk_*`-Felder beziehen sich auf das ganze Volume, nicht nur auf die
    Dumps: Dort liegt seit AP10a auch die Basiskarte. Läuft das Volume voll,
    scheitert die Rotation still — sichtbar wird das sonst erst beim Restore.
    """

    entries: list[BackupEntry]
    stale_count: int
    keep: int
    disk_total_bytes: int
    disk_used_bytes: int
    disk_free_bytes: int
