"""Schema der Basiskarten-Metadaten (ADR 0002, AP10a/AP10b).

Spiegelt `basemap.meta.json`, wie der Extract-Job sie schreibt. `bbox` und
`maxzoom` braucht der Client für Startansicht und Overzoom, `osm_data_timestamp`
und `tileset_version` für die Attribution mit Datenstand (Spec §15).
"""

from pydantic import BaseModel


class BasemapMeta(BaseModel):
    build_date: str
    osm_data_timestamp: str
    tileset_version: str
    bbox: list[float]
    maxzoom: int
    bytes: int
    sha256: str
    fetched_at: str
