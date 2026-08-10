"""Schemas des Bedingungs-Ausblicks (Spec §5, §12, §15)."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel

# Pflichtangabe, Spec §15. Gehört zusätzlich sichtbar in die App-Oberfläche.
OPEN_METEO_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"


class ConditionsDay(BaseModel):
    """Ein Tag des Ausblicks.

    Invariante 10: Der Gesamtscore bleibt in seine vier Faktoren
    aufschlüsselbar — keine Blackbox-Zahl. Fehlen Eingaben, sind alle fünf
    Werte null und `reason` nennt im Klartext, was fehlt; das Zielfenster
    steht trotzdem, weil es nur am Datum hängt und nicht am Wetter.
    """

    date: date
    total: float | None
    season: float | None
    soil_moisture: float | None
    rain: float | None
    field: float | None
    window_key: str
    window_label: str
    reason: str | None


class ConditionsMeta(BaseModel):
    attribution: str = OPEN_METEO_ATTRIBUTION
    days: int


class ConditionsOutlook(BaseModel):
    area_id: UUID
    meta: ConditionsMeta
    days: list[ConditionsDay]
