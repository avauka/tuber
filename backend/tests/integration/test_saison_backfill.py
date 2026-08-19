"""Saison-Backfill gegen die Datenbank (AP-Saisonzustand §4, §5).

Kein Netzwerk: `httpx.MockTransport` liefert nachgebildete Antworten der
Archiv-API. Geprüft wird, was die Rechenschicht nicht abdeckt — dass die
Normale nur einmal geholt wird, dass ein zweiter Lauf keine Dublette
erzeugt, und dass eine lückenhafte Antwort als unvollständig in der
Datenbank landet statt als glatte Zahl.

**Der laufende Wetter-Ingest wird hier nicht berührt.** Der Saisonzustand
hat eigene Tabellen, eine eigene Quelle und einen eigenen Job (ADR 0007).
"""

import uuid
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core import params
from app.jobs.season_backfill import (
    ARCHIV_URL,
    RUECKSCHAU_TAGE,
    backfill_gebiet,
    normale_besorgen,
)
from app.models.core import Area, ConditionsSnapshot, SeasonNormal, SeasonState

pytestmark = pytest.mark.db

QUADRAT = "SRID=4326;POLYGON((6.5 50.5, 6.6 50.5, 6.6 50.6, 6.5 50.6, 6.5 50.5))"

STICHTAG = date(2026, 8, 31)


def _area(db, name: str = "Sötenich") -> uuid.UUID:
    area = Area(id=uuid.uuid4(), name=name, geom=QUADRAT)
    db.add(area)
    db.commit()
    return area.id


def _tage(ende: date, anzahl: int) -> list[str]:
    return [(ende - timedelta(days=i)).isoformat() for i in reversed(range(anzahl))]


def _antwort(
    tage: list[str],
    niederschlag: float | list[float | None] = 1.0,
    feuchte: float | list[float | None] = 0.20,
) -> dict:
    def reihe(vorgabe):
        return list(vorgabe) if isinstance(vorgabe, list) else [vorgabe] * len(tage)

    return {
        "latitude": 50.55,
        "longitude": 6.55,
        "daily_units": {"precipitation_sum": "mm", "soil_moisture_7_to_28cm_mean": "m³/m³"},
        "daily": {
            "time": tage,
            "precipitation_sum": reihe(niederschlag),
            "soil_moisture_7_to_28cm_mean": reihe(feuchte),
        },
    }


def _client(antworten: dict[str, dict], protokoll: list[httpx.Request] | None = None):
    """MockTransport, der nach dem Startjahr unterscheidet."""

    def handler(request: httpx.Request) -> httpx.Response:
        if protokoll is not None:
            protokoll.append(request)
        start = request.url.params.get("start_date", "")
        schluessel = "normale" if start.startswith(str(params.SEASON_NORMAL_FROM_YEAR)) else "ist"
        return httpx.Response(200, json=antworten[schluessel])

    return httpx.Client(transport=httpx.MockTransport(handler))


def _antworten(
    niederschlag: float | list[float | None] = 1.0,
    feuchte: float | list[float | None] = 0.20,
) -> dict[str, dict]:
    normal_tage = [
        d.isoformat()
        for d in (
            date(params.SEASON_NORMAL_FROM_YEAR, 1, 1) + timedelta(days=i) for i in range(366 * 2)
        )
    ]
    return {
        "normale": _antwort(normal_tage, niederschlag=2.0, feuchte=0.25),
        "ist": _antwort(_tage(STICHTAG, RUECKSCHAU_TAGE), niederschlag, feuchte),
    }


# --------------------------------------------------------------- Normale


def test_normale_wird_einmal_geholt_und_dann_wiederverwendet(db_session):
    """Der 30-Jahres-Abruf ist der teuerste Aufruf des Pakets (§2)."""
    area_id = _area(db_session)
    protokoll: list[httpx.Request] = []
    client = _client(_antworten(), protokoll)

    erste = normale_besorgen(db_session, client, area_id, 50.55, 6.55)
    zweite = normale_besorgen(db_session, client, area_id, 50.55, 6.55)

    assert erste.id == zweite.id
    assert len(protokoll) == 1
    assert str(protokoll[0].url).startswith(ARCHIV_URL)


def test_normale_traegt_ihren_referenzzeitraum(db_session):
    area_id = _area(db_session)
    normale = normale_besorgen(db_session, _client(_antworten()), area_id, 50.55, 6.55)

    assert normale.reference_from_year == params.SEASON_NORMAL_FROM_YEAR
    assert normale.reference_to_year == params.SEASON_NORMAL_TO_YEAR
    # Je Kalendertag ein Wert, der Schalttag eingeschlossen.
    assert "02-29" in normale.precipitation_by_day
    assert len(normale.precipitation_by_day) == 366


# --------------------------------------------------------------- Backfill


def test_backfill_schreibt_die_kennzahlen(db_session):
    area_id = _area(db_session)

    zustand = backfill_gebiet(
        db_session, _client(_antworten()), area_id, 50.55, 6.55, stichtag=STICHTAG
    )

    assert zustand.area_id == area_id
    assert zustand.window_end == STICHTAG
    # Numeric-Spalten kommen als Decimal zurueck; fuer den Vergleich in
    # float wandeln, nicht die Erwartung aufweichen.
    assert float(zustand.precipitation_30d_mm) == pytest.approx(30.0)
    assert float(zustand.precipitation_180d_mm) == pytest.approx(180.0)
    # Ist 1,0 mm gegen Normale 2,0 mm je Tag.
    assert float(zustand.precipitation_90d_percent) == pytest.approx(50.0, abs=0.5)
    assert float(zustand.soil_moisture_90d) == pytest.approx(0.20)
    assert zustand.complete is True


def test_zweiter_lauf_erzeugt_keine_dublette(db_session):
    """§5: Idempotenz über (Gebiet, Stichtag)."""
    area_id = _area(db_session)
    client = _client(_antworten())

    erst = backfill_gebiet(db_session, client, area_id, 50.55, 6.55, stichtag=STICHTAG)
    zweit = backfill_gebiet(db_session, client, area_id, 50.55, 6.55, stichtag=STICHTAG)

    zeilen = (
        db_session.execute(select(SeasonState).where(SeasonState.area_id == area_id))
        .scalars()
        .all()
    )

    assert len(zeilen) == 1
    assert erst.id == zweit.id


def test_luecke_landet_als_unvollstaendig_in_der_datenbank(db_session):
    """Keine stille Teilsumme (§5)."""
    area_id = _area(db_session)
    werte: list[float | None] = [1.0] * RUECKSCHAU_TAGE
    werte[-1] = None
    werte[-2] = None

    zustand = backfill_gebiet(
        db_session,
        _client(_antworten(niederschlag=werte)),
        area_id,
        50.55,
        6.55,
        stichtag=STICHTAG,
    )

    assert zustand.complete is False
    assert zustand.missing_days == 2


def test_rohantwort_wird_archiviert(db_session):
    """§4: Herkunft nachvollziehbar, analog zu conditions_snapshot.raw."""
    area_id = _area(db_session)

    zustand = backfill_gebiet(
        db_session, _client(_antworten()), area_id, 50.55, 6.55, stichtag=STICHTAG
    )

    assert zustand.raw["daily"]["precipitation_sum"]
    assert zustand.source == "era5-archive"


def test_trockenperiode_wird_gespeichert(db_session):
    area_id = _area(db_session)
    werte: list[float | None] = [0.0] * RUECKSCHAU_TAGE
    werte[0] = 10.0

    zustand = backfill_gebiet(
        db_session,
        _client(_antworten(niederschlag=werte)),
        area_id,
        50.55,
        6.55,
        stichtag=STICHTAG,
    )

    assert zustand.dry_spell_days == RUECKSCHAU_TAGE - 1


# ------------------------------------------- Abgrenzung zur Bedingungs-Engine


def test_backfill_ruehrt_conditions_snapshot_nicht_an(db_session):
    """Der Saisonzustand ist eine zweite, getrennte Grösse (ADR 0007).

    Er schreibt in eigene Tabellen und lässt die Engine in Ruhe — auch
    dann, wenn für dasselbe Gebiet Snapshots existieren.
    """
    area_id = _area(db_session)
    db_session.add(
        ConditionsSnapshot(id=uuid.uuid4(), area_id=area_id, date=STICHTAG, precip_mm=3.0)
    )
    db_session.commit()

    backfill_gebiet(db_session, _client(_antworten()), area_id, 50.55, 6.55, stichtag=STICHTAG)

    snapshot = db_session.execute(
        select(ConditionsSnapshot).where(ConditionsSnapshot.area_id == area_id)
    ).scalar_one()
    assert float(snapshot.precip_mm) == pytest.approx(3.0)
    assert db_session.execute(select(SeasonNormal)).scalars().all()


# --------------------------------------------------- Anzeige am Gebiet (§6)


def test_gebiet_traegt_den_saisonzustand(client, db_session):
    """§6: Gebietsattribut in der bestehenden Ansicht, keine neue Seite."""
    area_id = _area(db_session, name="Kall")
    backfill_gebiet(db_session, _client(_antworten()), area_id, 50.55, 6.55, stichtag=STICHTAG)

    gebiet = next(g for g in client.get("/api/areas").json() if g["id"] == str(area_id))
    saison = gebiet["season"]

    assert saison["window_end"] == STICHTAG.isoformat()
    assert saison["precipitation_90d_percent"] == pytest.approx(50.0, abs=0.5)
    assert saison["soil_moisture_90d_percent"] == pytest.approx(80.0, abs=0.5)
    assert saison["dry_spell_days"] == 0
    assert saison["complete"] is True
    # Der Bezugszeitraum gehoert an die Zahl, sonst ist sie nicht lesbar.
    assert saison["reference_from_year"] == params.SEASON_NORMAL_FROM_YEAR
    assert saison["reference_to_year"] == params.SEASON_NORMAL_TO_YEAR
    assert saison["source"] == "era5-archive"


def test_gebiet_ohne_saisonzustand_bleibt_gueltig(client, db_session):
    """Vor dem ersten Backfill gibt es die Zahlen noch nicht."""
    area_id = _area(db_session, name="Ohne Backfill")

    gebiet = next(g for g in client.get("/api/areas").json() if g["id"] == str(area_id))

    assert gebiet["season"] is None


def test_nur_der_juengste_stichtag_erscheint(client, db_session):
    """Zwei Laeufe, zwei Stichtage — angezeigt wird der neuere."""
    area_id = _area(db_session, name="Zwei Stichtage")
    mock = _client(_antworten())
    backfill_gebiet(db_session, mock, area_id, 50.55, 6.55, stichtag=STICHTAG - timedelta(days=30))
    backfill_gebiet(db_session, mock, area_id, 50.55, 6.55, stichtag=STICHTAG)

    gebiet = next(g for g in client.get("/api/areas").json() if g["id"] == str(area_id))

    assert gebiet["season"]["window_end"] == STICHTAG.isoformat()


# ------------------------------------------- Ratenbegrenzung (Produktionsbefund)


def test_429_wird_wiederholt_statt_das_gebiet_zu_verlieren(db_session, monkeypatch):
    """Befund aus dem ersten echten Lauf am 2026-08-19.

    Vier Gebiete ergaben beim ersten Mal acht Abrufe in drei Sekunden — je
    Gebiet die 30-Jahres-Normale und das 180-Tage-Fenster. Open-Meteo
    beantwortete den letzten mit `429 Too Many Requests`, und das Gebiet
    blieb ohne Saisonzustand zurueck.

    Ein 429 ist kein Fehler der Anfrage, sondern eine Bitte um Geduld: Er
    gehoert abgewartet, nicht gemeldet.
    """
    from app.jobs import season_backfill

    gewartet: list[float] = []
    monkeypatch.setattr(season_backfill.time, "sleep", gewartet.append)

    antworten = _antworten()
    versuche = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        start = request.url.params.get("start_date", "")
        schluessel = "normale" if start.startswith(str(params.SEASON_NORMAL_FROM_YEAR)) else "ist"
        if schluessel == "ist":
            versuche["n"] += 1
            if versuche["n"] == 1:
                return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(200, json=antworten[schluessel])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    area_id = _area(db_session)

    backfill_gebiet(db_session, client, area_id, 50.55, 6.55, stichtag=STICHTAG)

    zustand = db_session.execute(
        select(SeasonState).where(SeasonState.area_id == area_id)
    ).scalar_one()
    assert zustand.precipitation_180d_mm is not None
    assert versuche["n"] == 2, "der zweite Versuch muss die Werte holen"
    assert gewartet, "zwischen den Versuchen wird gewartet"


def test_dauerhafter_429_scheitert_am_ende_doch(db_session, monkeypatch):
    """Endlos wiederholt wird nicht — sonst haengt der Cron."""
    from app.jobs import season_backfill

    monkeypatch.setattr(season_backfill.time, "sleep", lambda _s: None)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(429, text="Too Many Requests"))
    )
    area_id = _area(db_session)

    with pytest.raises(httpx.HTTPStatusError):
        backfill_gebiet(db_session, client, area_id, 50.55, 6.55, stichtag=STICHTAG)


def test_andere_fehler_werden_nicht_wiederholt(db_session, monkeypatch):
    """Ein 400 wird durch Warten nicht besser."""
    from app.jobs import season_backfill

    monkeypatch.setattr(season_backfill.time, "sleep", lambda _s: None)
    aufrufe = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        aufrufe["n"] += 1
        return httpx.Response(400, text="Bad Request")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    area_id = _area(db_session)

    with pytest.raises(httpx.HTTPStatusError):
        backfill_gebiet(db_session, client, area_id, 50.55, 6.55, stichtag=STICHTAG)
    assert aufrufe["n"] == 1
