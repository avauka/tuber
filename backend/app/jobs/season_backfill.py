"""Saison-Backfill aus dem ERA5-Archiv (AP-Saisonzustand, ADR 0007).

Aufruf:  python -m app.jobs.season_backfill

**Nicht der Wetter-Ingest.** Der laeuft taeglich gegen die Forecast-API und
fuellt `conditions_snapshot` fuer die Bedingungs-Engine; dieser Job laeuft
**monatlich** gegen `archive-api.open-meteo.com` und fuellt `season_state`.
Zwei Fragen, zwei Quellen, zwei Tabellen — ADR 0007 sieht das so vor, und
`app/jobs/weather_ingest.py` wird dabei nicht angefasst.

Warum monatlich: Die Groesse aendert sich langsam. Ein 180-Tage-Fenster
verschiebt sich in einem Monat um einen Sechstel; taeglich abzurufen waere
Last ohne Erkenntnis.

Ablauf je Gebiet:

1. Normale besorgen — einmalig ueber 30 Jahre, danach aus der Datenbank.
   Das ist der groesste Einzelaufruf des Pakets (rund 260 KB), und er
   gehoert genau einmal gemacht.
2. Die letzten 180 Tage holen.
3. Kennzahlen rechnen (`app/services/saisonzustand.py`) und je Gebiet und
   Stichtag upserten.

Fehlerisolation wie beim Wetter-Ingest: Ein Gebiet, das scheitert, stoppt
die uebrigen nicht, und der Exit-Code ist ungleich 0, sobald eines
gescheitert ist.
"""

import sys
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import httpx
from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session as OrmSession

from app.core import params
from app.core.db import get_sessionmaker
from app.models.core import Area, SeasonNormal, SeasonState
from app.services.saisonzustand import (
    normale_je_kalendertag,
    saisonkennzahlen,
)

ARCHIV_URL = "https://archive-api.open-meteo.com/v1/archive"

# Open-Meteo begrenzt die Aufrufe je Minute, und der 30-Jahres-Abruf wiegt
# schwer. Beim ersten Lauf ueber mehrere Gebiete faellt genau das auf:
# je Gebiet zwei Abrufe, der letzte kam am 2026-08-19 als 429 zurueck und
# das Gebiet blieb ohne Saisonzustand.
#
# Ein 429 ist keine Ablehnung der Anfrage, sondern eine Bitte um Geduld —
# also warten und wiederholen. Jeder andere Fehlerstatus wird durch Warten
# nicht besser und fliegt sofort.
WIEDERHOLUNGEN_BEI_429 = 3
WARTEZEIT_BEI_429_S = (20.0, 45.0, 90.0)

# Kleine Pause zwischen den Gebieten, damit der Minutenzaehler gar nicht
# erst volllaeuft. Der Job laeuft monatlich; ein paar Sekunden sind gratis.
PAUSE_JE_GEBIET_S = 3.0

# Geprueft gegen die Archiv-API am 2026-08-17: Beide Groessen existieren
# dort unter denselben Namen wie in der Forecast-API, als Tagesaggregat.
# Die Tiefe 7-28 cm ist dieselbe, die auch die Bedingungs-Engine bewertet.
NIEDERSCHLAG = "precipitation_sum"
BODENFEUCHTE = "soil_moisture_7_to_28cm_mean"
TAGESWERTE = (NIEDERSCHLAG, BODENFEUCHTE)

QUELLE = "era5-archive"

RUECKSCHAU_TAGE = max(params.SEASON_WINDOWS_DAYS)

# ERA5 haengt rund zwei Tage nach (ADR 0007). Fuer eine Sechsmonatsbilanz
# unkritisch — aber der Stichtag muss es beruecksichtigen, sonst faengt
# sich jeder Lauf zwei leere Tage am Fensterende ein.
ARCHIV_NACHLAUF_TAGE = 3

REQUEST_TIMEOUT_S = 120.0


@dataclass
class BackfillSummary:
    areas_total: int = 0
    areas_ok: int = 0
    normalen_geholt: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0

    def as_text(self) -> str:
        zeilen = [
            (
                f"Gebiete: {self.areas_ok}/{self.areas_total} erfolgreich, "
                f"{self.normalen_geholt} Normale neu berechnet."
            )
        ]
        zeilen.extend(f"FEHLER: {meldung}" for meldung in self.failures)
        return "\n".join(zeilen)


def stichtag_heute(heute: date | None = None) -> date:
    return (heute or datetime.now(UTC).date()) - timedelta(days=ARCHIV_NACHLAUF_TAGE)


def _abrufen(client: httpx.Client, lat: float, lon: float, von: date, bis: date) -> dict:
    parameter = {
        "latitude": f"{lat}",
        "longitude": f"{lon}",
        "start_date": von.isoformat(),
        "end_date": bis.isoformat(),
        "daily": ",".join(TAGESWERTE),
        "timezone": "UTC",
    }

    for versuch in range(WIEDERHOLUNGEN_BEI_429 + 1):
        antwort = client.get(ARCHIV_URL, params=parameter, timeout=REQUEST_TIMEOUT_S)
        if antwort.status_code != 429 or versuch == WIEDERHOLUNGEN_BEI_429:
            break
        wartezeit = WARTEZEIT_BEI_429_S[min(versuch, len(WARTEZEIT_BEI_429_S) - 1)]
        print(f"   429 der Archiv-API, warte {wartezeit:.0f} s und versuche es erneut")
        time.sleep(wartezeit)

    antwort.raise_for_status()
    nutzlast = antwort.json()
    fehlend = [name for name in TAGESWERTE if name not in nutzlast.get("daily", {})]
    if fehlend:
        # Open-Meteo laesst falsch geschriebene Variablen stillschweigend
        # weg — derselbe stille Fehlerfall wie beim Wetter-Ingest.
        raise ValueError(f"Archiv-Antwort ohne {', '.join(fehlend)}.")
    return nutzlast


def _tagesreihe(nutzlast: dict, feld: str) -> dict[date, float | None]:
    taeglich = nutzlast["daily"]
    werte = taeglich.get(feld) or []
    reihe: dict[date, float | None] = {}
    for index, stempel in enumerate(taeglich["time"]):
        wert = werte[index] if index < len(werte) else None
        reihe[date.fromisoformat(stempel)] = None if wert is None else float(wert)
    return reihe


def normale_besorgen(
    db: OrmSession, client: httpx.Client, area_id: uuid.UUID, lat: float, lon: float
) -> SeasonNormal:
    """Die 30-Jahres-Normale — einmal holen, dann wiederverwenden (§2)."""
    vorhanden = db.execute(
        select(SeasonNormal).where(SeasonNormal.area_id == area_id)
    ).scalar_one_or_none()
    if vorhanden is not None:
        return vorhanden

    nutzlast = _abrufen(
        client,
        lat,
        lon,
        date(params.SEASON_NORMAL_FROM_YEAR, 1, 1),
        date(params.SEASON_NORMAL_TO_YEAR, 12, 31),
    )
    normale = SeasonNormal(
        id=uuid.uuid4(),
        area_id=area_id,
        reference_from_year=params.SEASON_NORMAL_FROM_YEAR,
        reference_to_year=params.SEASON_NORMAL_TO_YEAR,
        precipitation_by_day=normale_je_kalendertag(_tagesreihe(nutzlast, NIEDERSCHLAG)),
        soil_moisture_by_day=normale_je_kalendertag(_tagesreihe(nutzlast, BODENFEUCHTE)),
        source=QUELLE,
    )
    db.add(normale)
    db.commit()
    return normale


def backfill_gebiet(
    db: OrmSession,
    client: httpx.Client,
    area_id: uuid.UUID,
    lat: float,
    lon: float,
    stichtag: date | None = None,
) -> SeasonState:
    """Kennzahlen fuer ein Gebiet berechnen und ablegen."""
    ende = stichtag or stichtag_heute()
    normale = normale_besorgen(db, client, area_id, lat, lon)

    nutzlast = _abrufen(client, lat, lon, ende - timedelta(days=RUECKSCHAU_TAGE - 1), ende)
    kennzahlen = saisonkennzahlen(
        ende,
        _tagesreihe(nutzlast, NIEDERSCHLAG),
        _tagesreihe(nutzlast, BODENFEUCHTE),
        normale.precipitation_by_day,
        normale.soil_moisture_by_day,
    )

    # Upsert ueber (area_id, window_end): Ein zweiter Lauf fuer denselben
    # Stichtag aktualisiert die Zeile, statt eine zweite anzulegen (§5).
    zustand = db.execute(
        select(SeasonState).where(SeasonState.area_id == area_id, SeasonState.window_end == ende)
    ).scalar_one_or_none()
    if zustand is None:
        zustand = SeasonState(id=uuid.uuid4(), area_id=area_id, window_end=ende)
        db.add(zustand)

    zustand.precipitation_30d_mm = kennzahlen.niederschlag_30d.wert
    zustand.precipitation_90d_mm = kennzahlen.niederschlag_90d.wert
    zustand.precipitation_180d_mm = kennzahlen.niederschlag_180d.wert
    zustand.precipitation_30d_percent = kennzahlen.niederschlag_30d_prozent
    zustand.precipitation_90d_percent = kennzahlen.niederschlag_90d_prozent
    zustand.precipitation_180d_percent = kennzahlen.niederschlag_180d_prozent
    zustand.soil_moisture_90d = kennzahlen.bodenfeuchte_90d.wert
    zustand.soil_moisture_90d_percent = kennzahlen.bodenfeuchte_90d_prozent
    zustand.dry_spell_days = kennzahlen.trockenperiode_180d_tage
    zustand.complete = kennzahlen.vollstaendig
    zustand.missing_days = kennzahlen.fehlende_tage
    zustand.source = QUELLE
    zustand.raw = nutzlast
    zustand.computed_at = datetime.now(UTC)

    db.commit()
    db.refresh(zustand)
    return zustand


def _area_points(db: OrmSession) -> list[tuple[uuid.UUID, str, float, float]]:
    """Ein Abrufpunkt je Gebiet: der Schwerpunkt — wie beim Wetter-Ingest."""
    centroid = func.ST_Centroid(cast(Area.geom, Geometry))
    zeilen = db.execute(
        select(Area.id, Area.name, func.ST_Y(centroid), func.ST_X(centroid)).order_by(Area.name)
    ).all()
    return [(zeile[0], zeile[1], float(zeile[2]), float(zeile[3])) for zeile in zeilen]


def run_backfill(
    db: OrmSession, client: httpx.Client, stichtag: date | None = None
) -> BackfillSummary:
    summary = BackfillSummary()
    ende = stichtag or stichtag_heute()

    for nummer, (area_id, name, lat, lon) in enumerate(_area_points(db)):
        # Zwischen den Gebieten kurz durchatmen: Beim ersten Lauf holt jedes
        # zwei Abrufe, davon den schweren 30-Jahres-Abruf. Ohne Pause laeuft
        # der Minutenzaehler von Open-Meteo voll (Befund 2026-08-19).
        if nummer:
            time.sleep(PAUSE_JE_GEBIET_S)
        summary.areas_total += 1
        hatte_normale = (
            db.execute(
                select(SeasonNormal.id).where(SeasonNormal.area_id == area_id)
            ).scalar_one_or_none()
            is not None
        )
        try:
            zustand = backfill_gebiet(db, client, area_id, lat, lon, stichtag=ende)
            summary.areas_ok += 1
            if not hatte_normale:
                summary.normalen_geholt += 1
            print(
                f"{name}: 180 Tage bis {ende} — "
                f"{zustand.precipitation_180d_mm:.0f} mm "
                f"({zustand.precipitation_180d_percent:.0f} % der Normale), "
                f"laengste Trockenphase {zustand.dry_spell_days} Tage"
                + ("" if zustand.complete else f", UNVOLLSTAENDIG ({zustand.missing_days} Tage)")
            )
        except Exception as exc:  # noqa: BLE001 — ein Gebiet darf die uebrigen nicht stoppen
            db.rollback()
            summary.failures.append(f"{name} ({area_id}): {exc}")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # Keine Argumente; Konfiguration kommt aus der ENV.
    with get_sessionmaker()() as db, httpx.Client() as client:
        summary = run_backfill(db, client)
    print(summary.as_text())
    return summary.exit_code


if __name__ == "__main__":
    sys.exit(main())
