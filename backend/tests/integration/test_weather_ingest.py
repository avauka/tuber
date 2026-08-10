"""Open-Meteo-Ingest und Bedingungs-Ausblick — Spec §5, §12.

Kein Netzwerk: httpx.MockTransport liefert nachgebildete API-Antworten in
der Struktur der echten Open-Meteo-Antwort. Ein Fall bildet ausdruecklich
nach, wie die API eine falsch geschriebene Variable stillschweigend weglaesst.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.jobs.weather_ingest import (
    ARCHIVE_DAYS,
    FORECAST_DAYS,
    HOURLY_VARIABLES,
    run_ingest,
)
from app.main import app
from app.models.core import Area, ConditionsSnapshot

pytestmark = pytest.mark.db

QUADRAT = {
    "type": "Polygon",
    "coordinates": [[[6.5, 50.5], [6.6, 50.5], [6.6, 50.6], [6.5, 50.6], [6.5, 50.5]]],
}

# Werte, die in AP2 einen vollen Score ergeben: Feuchte im Optimum, mildes
# Wetter, schwacher Wind.
STUNDENWERTE = {
    "soil_moisture_0_to_7cm": 0.25,
    "soil_moisture_7_to_28cm": 0.28,
    "soil_temperature_7_to_28cm": 12.0,
    "temperature_2m": 14.0,
    "wind_speed_10m": 8.0,
    "precipitation": 0.0,
}


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def _area(db) -> uuid.UUID:
    area = Area(id=uuid.uuid4(), name="Sötenich", geom=_wkt(QUADRAT))
    db.add(area)
    db.commit()
    return area.id


def _wkt(geometry: dict) -> str:
    ring = geometry["coordinates"][0]
    return "SRID=4326;POLYGON((" + ", ".join(f"{lon} {lat}" for lon, lat in ring) + "))"


def _payload(
    tage: list[date], *, weglassen: str | None = None, regen_am: date | None = None
) -> dict:
    """Open-Meteo-Antwort nachbilden: stuendliche Reihen ueber ganze Tage."""
    zeiten: list[str] = []
    reihen: dict[str, list[float]] = {name: [] for name in HOURLY_VARIABLES}

    for tag in tage:
        for stunde in range(24):
            zeiten.append(f"{tag.isoformat()}T{stunde:02d}:00")
            for name, wert in STUNDENWERTE.items():
                if name == "precipitation" and tag == regen_am:
                    # 22 mm ueber den Tag verteilt: der ideale Nachlauf aus AP2.
                    reihen[name].append(22.0 / 24)
                else:
                    reihen[name].append(wert)

    hourly: dict[str, object] = {"time": zeiten}
    for name, werte in reihen.items():
        if name == weglassen:
            # Genau so verhaelt sich die API bei einem Tippfehler: das Feld
            # fehlt einfach, ohne Fehlermeldung.
            continue
        hourly[name] = werte

    return {
        "latitude": 50.55,
        "longitude": 6.55,
        "generationtime_ms": 0.42,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "timezone_abbreviation": "GMT",
        "elevation": 450.0,
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "precipitation": "mm",
            "soil_moisture_0_to_7cm": "m³/m³",
            "soil_moisture_7_to_28cm": "m³/m³",
            "soil_temperature_7_to_28cm": "°C",
            "wind_speed_10m": "km/h",
        },
        "hourly": hourly,
    }


def _mock_client(
    heute: date, *, weglassen: str | None = None, archiv_tage: int = ARCHIVE_DAYS
) -> httpx.Client:
    regen_am = heute - timedelta(days=5)

    def handler(request: httpx.Request) -> httpx.Response:
        if "archive" in request.url.path:
            tage = [heute - timedelta(days=offset) for offset in range(archiv_tage)]
        else:
            tage = [heute + timedelta(days=offset) for offset in range(FORECAST_DAYS)]
        return httpx.Response(
            200, json=_payload(sorted(tage), weglassen=weglassen, regen_am=regen_am)
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def _snapshots(db, area_id: uuid.UUID) -> list[ConditionsSnapshot]:
    return list(
        db.execute(
            select(ConditionsSnapshot)
            .where(ConditionsSnapshot.area_id == area_id)
            .order_by(ConditionsSnapshot.date)
        )
        .scalars()
        .all()
    )


# ------------------------------------------------------------------ Ingest


def test_ingest_schreibt_tageszeilen(db_session):
    area_id = _area(db_session)
    heute = date(2026, 8, 1)

    with _mock_client(heute) as client:
        summary = run_ingest(db_session, client, today=heute)

    assert summary.exit_code == 0
    assert summary.areas_ok == 1
    assert not summary.failures

    rows = _snapshots(db_session, area_id)
    # 14 Archivtage + 7 Forecasttage, der heutige Tag liegt in beiden.
    assert len(rows) == ARCHIVE_DAYS + FORECAST_DAYS - 1
    assert rows[0].date == heute - timedelta(days=ARCHIVE_DAYS - 1)
    assert rows[-1].date == heute + timedelta(days=FORECAST_DAYS - 1)

    heutige = next(row for row in rows if row.date == heute)
    assert float(heutige.wind_kmh) == pytest.approx(8.0)
    assert float(heutige.temp_mean_c) == pytest.approx(14.0)
    assert float(heutige.soil_moisture_0_7) == pytest.approx(0.25)
    assert float(heutige.soil_moisture_7_28) == pytest.approx(0.28)
    assert float(heutige.soil_temp_7_28) == pytest.approx(12.0)
    assert heutige.raw is not None

    # Mittel fuer Zustandsgroessen, Summe fuer Niederschlag.
    regentag = next(row for row in rows if row.date == heute - timedelta(days=5))
    assert float(regentag.precip_mm) == pytest.approx(22.0)


def test_doppellauf_erzeugt_keine_duplikate(db_session):
    area_id = _area(db_session)
    heute = date(2026, 8, 1)

    with _mock_client(heute) as client:
        run_ingest(db_session, client, today=heute)
        erste = len(_snapshots(db_session, area_id))
        run_ingest(db_session, client, today=heute)

    assert len(_snapshots(db_session, area_id)) == erste


def test_fehlende_variable_schlaegt_hart_fehl(db_session):
    """Open-Meteo ignoriert Tippfehler stillschweigend — der Ingest nicht."""
    area_id = _area(db_session)
    heute = date(2026, 8, 1)

    with _mock_client(heute, weglassen="soil_moisture_7_to_28cm") as client:
        summary = run_ingest(db_session, client, today=heute)

    assert summary.exit_code != 0
    assert summary.areas_ok == 0
    assert "soil_moisture_7_to_28cm" in summary.failures[0]
    # Nichts halb Geschriebenes zurueckgelassen.
    assert _snapshots(db_session, area_id) == []


def test_ein_scheiterndes_gebiet_stoppt_die_uebrigen_nicht(db_session):
    gut = _area(db_session)
    schlecht = Area(id=uuid.uuid4(), name="Zzz-Kaputt", geom=_wkt(QUADRAT))
    db_session.add(schlecht)
    db_session.commit()
    heute = date(2026, 8, 1)

    def handler(request: httpx.Request) -> httpx.Response:
        # Der zweite Abruf je Gebiet ist das Archiv; hier scheitert es fuer
        # das alphabetisch spaetere Gebiet ueber einen Serverfehler.
        if "Zzz" in str(request.url) or handler.calls >= 2:  # type: ignore[attr-defined]
            handler.calls += 1  # type: ignore[attr-defined]
            return httpx.Response(500, json={"error": True})
        handler.calls += 1  # type: ignore[attr-defined]
        tage = (
            [heute - timedelta(days=o) for o in range(ARCHIVE_DAYS)]
            if "archive" in request.url.path
            else [heute + timedelta(days=o) for o in range(FORECAST_DAYS)]
        )
        return httpx.Response(200, json=_payload(sorted(tage), regen_am=heute))

    handler.calls = 0  # type: ignore[attr-defined]

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summary = run_ingest(db_session, client, today=heute)

    assert summary.areas_total == 2
    assert summary.areas_ok == 1
    assert summary.exit_code != 0
    # Das erste Gebiet ist trotzdem vollstaendig geschrieben.
    assert len(_snapshots(db_session, gut)) == ARCHIVE_DAYS + FORECAST_DAYS - 1


# ------------------------------------------------------- Ausblick-Endpunkt


def test_ausblick_ist_aufschluesselbar_und_konsistent(client, db_session):
    area_id = _area(db_session)
    heute = datetime.now(UTC).date()

    with _mock_client(heute) as http_client:
        run_ingest(db_session, http_client, today=heute)

    r = client.get(f"/api/conditions/{area_id}")
    assert r.status_code == 200
    body = r.json()

    assert body["meta"]["attribution"] == "Weather data by Open-Meteo.com (CC BY 4.0)"
    assert body["meta"]["days"] == 7
    assert len(body["days"]) == 7

    for tag in body["days"]:
        assert tag["window_key"]
        assert tag["window_label"]
        assert tag["reason"] is None
        # Invariante 10: die Summe der vier Teilscores ergibt den Gesamtwert.
        teilsumme = tag["season"] + tag["soil_moisture"] + tag["rain"] + tag["field"]
        assert tag["total"] == pytest.approx(teilsumme)
        assert 0.0 <= tag["total"] <= 100.0


def test_luecken_tag_nennt_den_grund(client, db_session):
    area_id = _area(db_session)
    heute = datetime.now(UTC).date()

    with _mock_client(heute) as http_client:
        run_ingest(db_session, http_client, today=heute)

    # Ein Tag mitten im Ausblick verschwindet.
    luecke = heute + timedelta(days=3)
    db_session.query(ConditionsSnapshot).filter(
        ConditionsSnapshot.area_id == area_id, ConditionsSnapshot.date == luecke
    ).delete()
    db_session.commit()

    tage = client.get(f"/api/conditions/{area_id}").json()["days"]
    betroffen = next(tag for tag in tage if tag["date"] == luecke.isoformat())

    assert betroffen["total"] is None
    assert betroffen["season"] is None
    assert "conditions_snapshot" in betroffen["reason"]
    # Das Zielfenster haengt am Datum, nicht am Wetter — es steht trotzdem.
    assert betroffen["window_key"]

    # Die Folgetage verlieren nur den fehlenden Regentag aus ihrer Historie.
    danach = next(tag for tag in tage if tag["date"] == (luecke + timedelta(days=1)).isoformat())
    assert danach["total"] is None
    assert "1 von 14" in danach["reason"]


def test_ausblick_fuer_unbekanntes_gebiet_ist_404(client):
    r = client.get(f"/api/conditions/{uuid.uuid4()}")
    assert r.status_code == 404
