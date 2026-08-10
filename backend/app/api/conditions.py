"""Bedingungs-Ausblick (Spec §5, §12).

Liest ausschliesslich aus conditions_snapshot — kein API-Aufruf zur Laufzeit.
Der Ingest-Job fuellt die Tabelle; damit ist der Endpunkt deterministisch,
testbar und auch dann bedienbar, wenn Open-Meteo gerade nicht erreichbar ist.

Der "Beste-Tage-Hinweis" aus Spec §5 ist bewusst nicht hier: Der Server
liefert die Strukturdaten, die Formulierung macht der Planer.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.db import DbSession
from app.models.core import Area, ConditionsSnapshot
from app.schemas.conditions import ConditionsDay, ConditionsMeta, ConditionsOutlook
from app.services.area_conditions import RAIN_WINDOW_DAYS, load_range, score_day
from app.services.conditions import best_window

router = APIRouter(prefix="/api/conditions", tags=["conditions"])

OUTLOOK_DAYS = 7


@router.get("/{area_id}", response_model=ConditionsOutlook)
def area_outlook(area_id: UUID, db: DbSession) -> ConditionsOutlook:
    if db.get(Area, area_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Gebiet {area_id} nicht gefunden."
        )

    heute = datetime.now(UTC).date()
    letzter_tag = heute + timedelta(days=OUTLOOK_DAYS - 1)
    # Einmal breit laden statt sieben Mal schmal: jeder Tag braucht seine
    # eigene 14-Tage-Regenhistorie.
    by_date = load_range(db, area_id, heute - timedelta(days=RAIN_WINDOW_DAYS - 1), letzter_tag)

    return ConditionsOutlook(
        area_id=area_id,
        meta=ConditionsMeta(days=OUTLOOK_DAYS),
        days=[_day(by_date, heute + timedelta(days=offset)) for offset in range(OUTLOOK_DAYS)],
    )


def _day(by_date: Mapping[date, ConditionsSnapshot], tag: date) -> ConditionsDay:
    fenster, _ = best_window(tag)
    ergebnis = score_day(by_date, tag)
    breakdown = ergebnis.breakdown

    return ConditionsDay(
        date=tag,
        total=breakdown.total if breakdown else None,
        season=breakdown.season if breakdown else None,
        soil_moisture=breakdown.soil_moisture if breakdown else None,
        rain=breakdown.rain if breakdown else None,
        field=breakdown.field if breakdown else None,
        window_key=fenster.key,
        window_label=fenster.label,
        reason=ergebnis.reason,
    )
