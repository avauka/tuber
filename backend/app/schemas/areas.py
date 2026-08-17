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


class SeasonRead(BaseModel):
    """Saisonzustand des Gebiets (AP-Saisonzustand, ADR 0007 „Rückweg").

    Eine **zweite, getrennte** Größe neben der Bedingungs-Engine: sechs
    Monate Rückschau aus dem ERA5-Archiv statt 14 Tage aus der
    Forecast-API. Sie beantwortet „ist dieses Jahr eins", nicht „ist jetzt
    ein guter Zeitpunkt".

    Bewusst ohne Gesamtnote — die Kennzahlen stehen einzeln (Invariante 10).
    Der Bezugszeitraum reist mit, sonst ist „41 %" nicht lesbar, und die
    Quelle ebenfalls: Es sind Modellwerte, keine Messwerte.
    """

    window_end: date
    precipitation_30d_mm: float | None
    precipitation_90d_mm: float | None
    precipitation_180d_mm: float | None
    precipitation_30d_percent: float | None
    precipitation_90d_percent: float | None
    precipitation_180d_percent: float | None
    soil_moisture_90d: float | None
    soil_moisture_90d_percent: float | None
    dry_spell_days: int | None
    complete: bool
    missing_days: int
    reference_from_year: int
    reference_to_year: int
    source: str


class AreaRead(BaseModel):
    id: UUID
    name: str
    geometry: dict
    notes: str | None
    access_notes: str | None
    last_visited: date | None
    offline_pinned: bool
    area_m2: float
    # Fehlt, solange der Backfill fuer das Gebiet noch nicht lief.
    season: SeasonRead | None = None
