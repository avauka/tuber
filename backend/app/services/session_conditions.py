"""Einfrieren der Bedingungen beim Session-Ende (Spec §5 "Wichtig").

Ohne mitgespeicherten Score kann spaeter niemand rekonstruieren, ob ein
Nullgang am Standort oder an den Bedingungen lag.

Ehrlichkeitsprinzip: Der Score entsteht nur, wenn alle Eingaben wirklich
vorliegen. Fehlt etwas, bleibt er null und der Grund wird im Klartext
genannt — eine Zahl aus geratenen Eingaben waere schlimmer als keine Zahl,
weil sie sich spaeter nicht mehr als Schaetzung erkennen laesst.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core import params
from app.models.core import ConditionsSnapshot
from app.services.conditions import total_score

# Der Regen-Nachlauf im Scoring blickt so weit zurueck; kuerzer geht nicht,
# ohne die Kurve aus AP2 zu verfaelschen.
RAIN_WINDOW_DAYS = params.RAIN_LAG_MAX_DAYS

# Passend zur Spaltenbezeichnung session.precip_prev_7d_mm.
PRECIP_SUM_DAYS = 7

# Schluessel im raw-JSONB des Snapshots. AP7 befuellt den Ingest genau so.
WIND_RAW_KEY = "wind_kmh"


@dataclass(frozen=True)
class FrozenConditions:
    temperature_c: float | None
    wind_kmh: float | None
    soil_moisture_0_7: float | None
    precip_prev_7d_mm: float | None
    conditions_score: float | None
    score_reason: str | None


def _number(value: Any) -> float | None:
    """Zahlenwert aus DB-Numeric oder JSONB in float, sonst None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _wind_from_raw(raw: Any) -> float | None:
    if not isinstance(raw, dict):
        return None
    return _number(raw.get(WIND_RAW_KEY))


def _empty(reason: str) -> FrozenConditions:
    return FrozenConditions(None, None, None, None, None, reason)


def _score(
    at: date,
    moisture: float | None,
    precip_daily_mm: list[float],
    temp_c: float | None,
    wind_kmh: float | None,
    soil_temp_c: float | None,
) -> float | None:
    """Genau ein Codepfad fuer den Score — dieselbe Funktion, die auch der
    Ausblick benutzt (AP2). Kein zweiter, leicht abweichender Nachbau."""
    if moisture is None or temp_c is None or wind_kmh is None or soil_temp_c is None:
        return None
    return total_score(
        at,
        moisture=moisture,
        precip_daily_mm=precip_daily_mm,
        temp_c=temp_c,
        wind_kmh=wind_kmh,
        soil_temp_c=soil_temp_c,
    ).total


def freeze_conditions(db: OrmSession, area_id: UUID | None, at: date) -> FrozenConditions:
    """Werte aus dem juengsten conditions_snapshot des Gebiets bis `at`."""
    if area_id is None:
        return _empty(
            "Session ohne area_id — ohne Gebiet gibt es keine Wetterhistorie zum Einfrieren."
        )

    # Ein Snapshot je Tag (UNIQUE area_id/date): die juengsten RAIN_WINDOW_DAYS
    # Zeilen decken damit jeden vorhandenen Tag des Rueckblickfensters ab.
    snapshots = (
        db.execute(
            select(ConditionsSnapshot)
            .where(ConditionsSnapshot.area_id == area_id, ConditionsSnapshot.date <= at)
            .order_by(ConditionsSnapshot.date.desc())
            .limit(RAIN_WINDOW_DAYS)
        )
        .scalars()
        .all()
    )
    if not snapshots:
        return _empty(f"Kein conditions_snapshot fuer das Gebiet mit Datum bis {at.isoformat()}.")

    by_date = {snapshot.date: snapshot for snapshot in snapshots}
    latest = snapshots[0]

    temperature_c = _number(latest.temp_mean_c)
    soil_moisture_0_7 = _number(latest.soil_moisture_0_7)
    wind_kmh = _wind_from_raw(latest.raw)

    precip_week = [
        _number(by_date[at - timedelta(days=offset)].precip_mm)
        for offset in range(PRECIP_SUM_DAYS)
        if at - timedelta(days=offset) in by_date
    ]
    vorhandene_woche = [value for value in precip_week if value is not None]
    precip_prev_7d_mm = sum(vorhandene_woche) if vorhandene_woche else None

    # --- Score: nur bei vollstaendigen Eingaben ---------------------------
    moisture = _number(latest.soil_moisture_7_28)
    soil_temp_c = _number(latest.soil_temp_7_28)

    precip_series: list[float] = []
    fehlende_tage = 0
    for offset in range(RAIN_WINDOW_DAYS):
        snapshot = by_date.get(at - timedelta(days=offset))
        value = _number(snapshot.precip_mm) if snapshot is not None else None
        if value is None:
            fehlende_tage += 1
            precip_series.append(0.0)
        else:
            precip_series.append(value)

    fehlt: list[str] = []
    if temperature_c is None:
        fehlt.append("temp_mean_c")
    if moisture is None:
        fehlt.append("soil_moisture_7_28")
    if soil_temp_c is None:
        fehlt.append("soil_temp_7_28")
    if wind_kmh is None:
        fehlt.append(f"{WIND_RAW_KEY} im raw-JSONB des Snapshots")
    if fehlende_tage:
        fehlt.append(
            f"{fehlende_tage} von {RAIN_WINDOW_DAYS} Snapshot-Tagen fuer den Regen-Nachlauf"
        )

    if fehlt:
        return FrozenConditions(
            temperature_c=temperature_c,
            wind_kmh=wind_kmh,
            soil_moisture_0_7=soil_moisture_0_7,
            precip_prev_7d_mm=precip_prev_7d_mm,
            conditions_score=None,
            score_reason="Kein Score berechnet, es fehlt: " + "; ".join(fehlt) + ".",
        )

    return FrozenConditions(
        temperature_c=temperature_c,
        wind_kmh=wind_kmh,
        soil_moisture_0_7=soil_moisture_0_7,
        precip_prev_7d_mm=precip_prev_7d_mm,
        conditions_score=_score(at, moisture, precip_series, temperature_c, wind_kmh, soil_temp_c),
        score_reason=None,
    )
