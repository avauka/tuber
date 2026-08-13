"""Schemas der Eignungskarte (ADR 0008, AP17a).

Sprachregelung, nicht verhandelbar (Invariante 9): „Eignung", „suitability" —
nie „Wahrscheinlichkeit" oder „probability", auch nicht in Feldnamen.
"""

from datetime import datetime

from pydantic import BaseModel


class WeightSet(BaseModel):
    """Der aktive Gewichtssatz (ADR 0008 §3).

    `weights` ist Faktor -> Prozent. Die Version steht auch in
    `suitability.meta.json` der erzeugten Kacheln; stimmen beide nicht
    überein, wurde seit dem letzten Pipeline-Lauf umgewichtet.
    """

    version: int
    weights: dict[str, float]
    note: str | None
    created_at: datetime


class SuitabilityMeta(BaseModel):
    """Spiegel von `suitability.meta.json`, geschrieben von Stufe 2.

    Bewusst nachsichtig geschnitten: Pflicht ist nur, was der Planer für
    die ehrliche Anzeige braucht — welche Faktoren enthalten sind und mit
    welchem Gewichtssatz gerechnet wurde. Alles Weitere ist Beiwerk und
    darf sich zwischen Pipeline-Versionen ändern, ohne den Endpunkt zu
    brechen.
    """

    gewichtssatz_version: int
    faktoren: dict[str, float]
    faktoren_fehlend: list[str] = []
    rasterweite_m: int | None = None
    epsg_verarbeitung: int | None = None
    bbox_wgs84: list[float] = []
    klassengrenzen: list[float] = []
    min_zoom: int | None = None
    max_zoom: int | None = None
    flaechen: int | None = None
    quellen: list[dict] = []
    bytes: int | None = None
    sha256: str | None = None
    generated_at: str


class UploadErgebnis(BaseModel):
    bytes: int
    gewichtssatz_version: int | None
    faktoren: list[str]
    generated_at: str | None
