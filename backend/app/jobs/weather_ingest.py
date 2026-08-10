"""Open-Meteo-Ingest (Spec §5, ADR 0001 Railway-Cron).

Aufruf:  python -m app.jobs.weather_ingest

Ein Aufruf je Gebiet gegen die Forecast-API deckt beide Zeitraeume ab:
past_days=14 fuer den Regen-Nachlauf, forecast_days=7 fuer den Ausblick
(ADR 0007 — die Archiv-API haengt rund zwei Tage nach, und zwar genau im
Fenster, das rain_score am staerksten gewichtet).

Die Tageszeilen landen in conditions_snapshot, damit GET /api/conditions
ausschliesslich aus der DB liest: deterministisch, testbar und im Feld auch
dann bedienbar, wenn Open-Meteo gerade nicht erreichbar ist. Der Upsert
laeuft ueber UNIQUE(area_id, date).

Fehlerisolation: Ein Gebiet, das scheitert, stoppt die uebrigen nicht. Am
Ende steht eine Zusammenfassung, und der Exit-Code ist ungleich 0, sobald
mindestens ein Gebiet gescheitert ist — sonst meldet der Cron-Job Erfolg,
obwohl Daten fehlen.
"""

import sys
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import httpx
from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as OrmSession

from app.core.db import get_sessionmaker
from app.models.core import Area, ConditionsSnapshot
from app.services.conditions import validate_openmeteo_response

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Exakt die sechs Variablen aus Spec §5. Reihenfolge egal, Schreibweise nicht:
# falsch geschriebene Namen ignoriert die API stillschweigend.
HOURLY_VARIABLES = (
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "soil_temperature_7_to_28cm",
    "precipitation",
    "temperature_2m",
    "wind_speed_10m",
)

# So weit blickt rain_score zurueck bzw. so weit reicht der Ausblick.
PAST_DAYS = 14
FORECAST_DAYS = 7
REQUEST_TIMEOUT_S = 30.0

# Tagesaggregation: Mittel fuer Zustandsgroessen, Summe fuer Niederschlag.
# Ein gemittelter Niederschlag waere sinnlos, eine summierte Temperatur auch.
MEAN_VARIABLES = {
    "soil_moisture_0_to_7cm": "soil_moisture_0_7",
    "soil_moisture_7_to_28cm": "soil_moisture_7_28",
    "soil_temperature_7_to_28cm": "soil_temp_7_28",
    "temperature_2m": "temp_mean_c",
    "wind_speed_10m": "wind_kmh",
}
SUM_VARIABLES = {"precipitation": "precip_mm"}


@dataclass
class IngestSummary:
    areas_total: int = 0
    areas_ok: int = 0
    rows_written: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0

    def as_text(self) -> str:
        zeilen = [
            (
                f"Gebiete: {self.areas_ok}/{self.areas_total} erfolgreich, "
                f"{self.rows_written} Tageszeilen geschrieben."
            )
        ]
        zeilen.extend(f"FEHLER: {message}" for message in self.failures)
        return "\n".join(zeilen)


def _hourly_params(latitude: float, longitude: float) -> dict[str, str]:
    return {
        "latitude": f"{latitude}",
        "longitude": f"{longitude}",
        "hourly": ",".join(HOURLY_VARIABLES),
        # UTC, damit die Tagesgrenzen zu den TIMESTAMPTZ-Konventionen passen.
        "timezone": "UTC",
        "wind_speed_unit": "kmh",
    }


def _fetch(client: httpx.Client, url: str, params: dict[str, str]) -> dict:
    response = client.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
    response.raise_for_status()
    payload = response.json()
    # Pflicht vor jeder Verarbeitung (Spec §5): fehlende Variablen sind der
    # stille Fehlerfall, den die API selbst nicht meldet.
    validate_openmeteo_response(HOURLY_VARIABLES, payload)
    return payload


def _daily_rows(payload: dict) -> dict[date, dict[str, float]]:
    """Stundenwerte zu Tageswerten verdichten."""
    hourly = payload["hourly"]
    times: Sequence[str] = hourly["time"]

    buckets: dict[date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for index, stamp in enumerate(times):
        tag = date.fromisoformat(stamp[:10])
        for variable in HOURLY_VARIABLES:
            werte = hourly.get(variable) or []
            if index >= len(werte):
                continue
            wert = werte[index]
            if wert is None:
                continue
            buckets[tag][variable].append(float(wert))

    rows: dict[date, dict[str, float]] = {}
    for tag, werte in buckets.items():
        spalten: dict[str, float] = {}
        for variable, spalte in MEAN_VARIABLES.items():
            if werte.get(variable):
                spalten[spalte] = sum(werte[variable]) / len(werte[variable])
        for variable, spalte in SUM_VARIABLES.items():
            if werte.get(variable):
                spalten[spalte] = sum(werte[variable])
        if spalten:
            rows[tag] = spalten
    return rows


def _upsert(
    db: OrmSession, area_id: uuid.UUID, tag: date, spalten: dict[str, float], raw: dict
) -> None:
    stmt = insert(ConditionsSnapshot).values(
        id=uuid.uuid4(), area_id=area_id, date=tag, raw=raw, **spalten
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=[ConditionsSnapshot.area_id, ConditionsSnapshot.date],
            set_={**spalten, "raw": raw},
        )
    )


def _area_points(db: OrmSession) -> list[tuple[uuid.UUID, str, float, float]]:
    """Ein Abrufpunkt je Gebiet: der Schwerpunkt der Gebietsgeometrie."""
    centroid = func.ST_Centroid(cast(Area.geom, Geometry))
    rows = db.execute(
        select(Area.id, Area.name, func.ST_Y(centroid), func.ST_X(centroid)).order_by(Area.name)
    ).all()
    return [(row[0], row[1], float(row[2]), float(row[3])) for row in rows]


def ingest_area(
    db: OrmSession, client: httpx.Client, area_id: uuid.UUID, lat: float, lon: float
) -> int:
    """Ein Aufruf, beide Zeitraeume — Vergangenheit und Ausblick aus einem
    Modelllauf, damit an der Tagesgrenze kein Sprung entsteht (ADR 0007)."""
    payload = _fetch(
        client,
        FORECAST_URL,
        {
            **_hourly_params(lat, lon),
            "past_days": str(PAST_DAYS),
            "forecast_days": str(FORECAST_DAYS),
        },
    )

    geschrieben = 0
    for tag, spalten in _daily_rows(payload).items():
        _upsert(db, area_id, tag, spalten, payload)
        geschrieben += 1
    db.commit()
    return geschrieben


def run_ingest(db: OrmSession, client: httpx.Client) -> IngestSummary:
    summary = IngestSummary()

    for area_id, name, lat, lon in _area_points(db):
        summary.areas_total += 1
        try:
            summary.rows_written += ingest_area(db, client, area_id, lat, lon)
            summary.areas_ok += 1
        except Exception as exc:  # noqa: BLE001 — ein Gebiet darf die uebrigen nicht stoppen
            db.rollback()
            summary.failures.append(f"{name} ({area_id}): {exc}")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # Der Job nimmt keine Argumente; Konfiguration kommt aus der ENV.
    with get_sessionmaker()() as db, httpx.Client() as client:
        summary = run_ingest(db, client)
    print(summary.as_text())
    return summary.exit_code


if __name__ == "__main__":
    sys.exit(main())
