"""Schemas der Gebiets-Endpunkte (Spec §4, §12).

Geometrie-I/O als GeoJSON — dasselbe Format, das GET /api/coverage schon
liefert, damit der Client nicht zwei Darstellungen auseinanderhalten muss.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class AreaCreate(BaseModel):
    name: str = Field(min_length=1)
    geometry: dict
    notes: str | None = None
    access_notes: str | None = None
    offline_pinned: bool = False


class AreaRead(BaseModel):
    id: UUID
    name: str
    geometry: dict
    notes: str | None
    access_notes: str | None
    last_visited: date | None
    offline_pinned: bool
    area_m2: float
