"""Bedingungen eines Gebiets über die Zeit (Spec §5).

Zwei Verwendungen, ein Codepfad: das Einfrieren beim Session-Ende (§5
"Wichtig") und der 7-Tage-Ausblick. Beide holen ihre Eingaben hier und
rechnen über conditions.total_score — ein zweiter, leicht abweichender
Nachbau wäre genau die Sorte Abweichung, die später niemand mehr erklärt.

Ehrlichkeitsprinzip: Ein Score entsteht nur bei vollständigen Eingaben.
Fehlt etwas, bleibt er null und der Grund steht im Klartext. Eine Zahl aus
geratenen Eingaben wäre schlimmer als keine Zahl, weil sie sich später nicht
mehr als Schätzung erkennen lässt.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core import params
from app.models.core import ConditionsSnapshot
from app.services.conditions import ScoreBreakdown, total_score

# So weit blickt der Regen-Nachlauf im Scoring zurück; kürzer geht nicht,
# ohne die Kurve aus AP2 zu verfälschen.
RAIN_WINDOW_DAYS = params.RAIN_LAG_MAX_DAYS

# Passend zur Spaltenbezeichnung session.precip_prev_7d_mm.
PRECIP_SUM_DAYS = 7


@dataclass(frozen=True)
class DayScore:
    breakdown: ScoreBreakdown | None
    reason: str | None


@dataclass(frozen=True)
class FrozenConditions:
    temperature_c: float | None
    wind_kmh: float | None
    soil_moisture_0_7: float | None
    precip_prev_7d_mm: float | None
    conditions_score: float | None
    score_reason: str | None


def _number(value: Any) -> float | None:
    """DB-Numeric in float, sonst None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_range(
    db: OrmSession, area_id: UUID, start: date, end: date
) -> dict[date, ConditionsSnapshot]:
    """Snapshots eines Datumsbereichs, nach Tag ansprechbar."""
    rows = (
        db.execute(
            select(ConditionsSnapshot).where(
                ConditionsSnapshot.area_id == area_id,
                ConditionsSnapshot.date >= start,
                ConditionsSnapshot.date <= end,
            )
        )
        .scalars()
        .all()
    )
    return {row.date: row for row in rows}


def _recent(db: OrmSession, area_id: UUID, at: date) -> list[ConditionsSnapshot]:
    """Die jüngsten Snapshots bis einschliesslich `at`, neueste zuerst."""
    return list(
        db.execute(
            select(ConditionsSnapshot)
            .where(ConditionsSnapshot.area_id == area_id, ConditionsSnapshot.date <= at)
            .order_by(ConditionsSnapshot.date.desc())
            .limit(RAIN_WINDOW_DAYS)
        )
        .scalars()
        .all()
    )


def _precip_series(by_date: Mapping[date, ConditionsSnapshot], at: date) -> tuple[list[float], int]:
    """Regenreihe für das Scoring: Index 0 = `at`, dann rückwärts."""
    series: list[float] = []
    fehlende_tage = 0
    for offset in range(RAIN_WINDOW_DAYS):
        snapshot = by_date.get(at - timedelta(days=offset))
        value = _number(snapshot.precip_mm) if snapshot is not None else None
        if value is None:
            fehlende_tage += 1
            series.append(0.0)
        else:
            series.append(value)
    return series, fehlende_tage


def score_day(by_date: Mapping[date, ConditionsSnapshot], at: date) -> DayScore:
    """Vollständige Aufschlüsselung für einen Tag — oder der Grund dagegen."""
    snapshot = by_date.get(at)
    if snapshot is None:
        return DayScore(None, f"Kein conditions_snapshot fuer den {at.isoformat()}.")

    moisture = _number(snapshot.soil_moisture_7_28)
    temp_c = _number(snapshot.temp_mean_c)
    soil_temp_c = _number(snapshot.soil_temp_7_28)
    wind_kmh = _number(snapshot.wind_kmh)
    precip_series, fehlende_tage = _precip_series(by_date, at)

    fehlt: list[str] = []
    if temp_c is None:
        fehlt.append("temp_mean_c")
    if moisture is None:
        fehlt.append("soil_moisture_7_28")
    if soil_temp_c is None:
        fehlt.append("soil_temp_7_28")
    if wind_kmh is None:
        fehlt.append("wind_kmh")
    if fehlende_tage:
        fehlt.append(
            f"{fehlende_tage} von {RAIN_WINDOW_DAYS} Snapshot-Tagen fuer den Regen-Nachlauf"
        )

    if fehlt or moisture is None or temp_c is None or soil_temp_c is None or wind_kmh is None:
        return DayScore(None, "Kein Score berechnet, es fehlt: " + "; ".join(fehlt) + ".")

    return DayScore(
        total_score(
            at,
            moisture=moisture,
            precip_daily_mm=precip_series,
            temp_c=temp_c,
            wind_kmh=wind_kmh,
            soil_temp_c=soil_temp_c,
        ),
        None,
    )


def freeze_conditions(db: OrmSession, area_id: UUID | None, at: date) -> FrozenConditions:
    """Werte aus dem jüngsten conditions_snapshot des Gebiets bis `at`."""
    if area_id is None:
        return FrozenConditions(
            None,
            None,
            None,
            None,
            None,
            "Session ohne area_id — ohne Gebiet gibt es keine Wetterhistorie zum Einfrieren.",
        )

    snapshots = _recent(db, area_id, at)
    if not snapshots:
        return FrozenConditions(
            None,
            None,
            None,
            None,
            None,
            f"Kein conditions_snapshot fuer das Gebiet mit Datum bis {at.isoformat()}.",
        )

    by_date = {snapshot.date: snapshot for snapshot in snapshots}
    latest = snapshots[0]

    woche = [
        value
        for offset in range(PRECIP_SUM_DAYS)
        if (snapshot := by_date.get(at - timedelta(days=offset))) is not None
        and (value := _number(snapshot.precip_mm)) is not None
    ]

    day = score_day(by_date, at)
    return FrozenConditions(
        temperature_c=_number(latest.temp_mean_c),
        wind_kmh=_number(latest.wind_kmh),
        soil_moisture_0_7=_number(latest.soil_moisture_0_7),
        precip_prev_7d_mm=sum(woche) if woche else None,
        conditions_score=day.breakdown.total if day.breakdown is not None else None,
        score_reason=day.reason,
    )
