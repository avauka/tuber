"""Gebiete und Sessions — Spec §4, §5 "Wichtig", §12.

Kern des Pakets: Beim Session-Ende werden die Bedingungen eingefroren, und
zwar nur dann, wenn sie vollstaendig vorliegen. Ein Score aus geratenen
Eingaben waere schlimmer als kein Score.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.core import ConditionsSnapshot

pytestmark = pytest.mark.db

ENDE = datetime(2026, 8, 1, 17, 0, tzinfo=UTC)
ENDE_TAG = ENDE.date()

QUADRAT = {
    "type": "Polygon",
    "coordinates": [[[6.5, 50.5], [6.6, 50.5], [6.6, 50.6], [6.5, 50.6], [6.5, 50.5]]],
}
NICHT_GESCHLOSSEN = {
    "type": "Polygon",
    "coordinates": [[[6.5, 50.5], [6.6, 50.5], [6.6, 50.6], [6.5, 50.6]]],
}
SELBSTUEBERSCHNEIDEND = {
    "type": "Polygon",
    "coordinates": [[[6.5, 50.5], [6.6, 50.6], [6.6, 50.5], [6.5, 50.6], [6.5, 50.5]]],
}
AUSSERHALB_WGS84 = {
    "type": "Polygon",
    "coordinates": [[[6.5, 50.5], [6.6, 50.5], [6.6, 95.0], [6.5, 95.0], [6.5, 50.5]]],
}


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def _area(client, name: str = "Sötenich") -> str:
    r = client.post("/api/areas", json={"name": name, "geometry": QUADRAT})
    assert r.status_code == 201
    return r.json()["id"]


def _snapshots(db, area_id: str, tage: int = 14, *, wind: float | None = 8.0) -> None:
    """Lueckenlose Snapshot-Reihe, die auf ENDE_TAG endet."""
    for offset in range(tage):
        tag = ENDE_TAG - timedelta(days=offset)
        db.add(
            ConditionsSnapshot(
                id=uuid.uuid4(),
                area_id=uuid.UUID(area_id),
                date=tag,
                soil_moisture_0_7=0.25,
                soil_moisture_7_28=0.28,
                soil_temp_7_28=12.0,
                # 22 mm vor fuenf Tagen: der ideale Nachlauf aus AP2.
                precip_mm=22.0 if offset == 5 else 0.0,
                temp_mean_c=14.0,
                # Seit Migration 0003 eine echte Spalte, nicht mehr raw-JSONB.
                wind_kmh=wind,
                raw={"quelle": "test-fixture"},
            )
        )
    db.commit()


def _ende(client, session_id: str):
    return client.patch(f"/api/sessions/{session_id}/end", json={"ended_at": ENDE.isoformat()})


# ------------------------------------------------------- Gebiets-Validierung


def test_gueltiges_polygon_wird_angelegt(client):
    r = client.post("/api/areas", json={"name": "Sötenich", "geometry": QUADRAT})
    assert r.status_code == 201
    body = r.json()
    assert body["geometry"]["type"] == "Polygon"
    assert body["area_m2"] > 0
    assert body["name"] == "Sötenich"

    liste = client.get("/api/areas").json()
    assert len(liste) == 1


def test_offener_ring_wird_abgelehnt(client):
    r = client.post("/api/areas", json={"name": "offen", "geometry": NICHT_GESCHLOSSEN})
    assert r.status_code == 422
    assert "geschlossen" in r.json()["detail"]
    assert client.get("/api/areas").json() == []


def test_selbstueberschneidendes_polygon_wird_abgelehnt(client):
    """ST_IsValid faengt die Bow-Tie-Geometrie, die strukturell in Ordnung ist."""
    r = client.post("/api/areas", json={"name": "bowtie", "geometry": SELBSTUEBERSCHNEIDEND})
    assert r.status_code == 422
    assert "ungueltig" in r.json()["detail"]
    assert client.get("/api/areas").json() == []


def test_koordinaten_ausserhalb_wgs84_werden_abgelehnt(client):
    r = client.post("/api/areas", json={"name": "mond", "geometry": AUSSERHALB_WGS84})
    assert r.status_code == 422
    assert "lat" in r.json()["detail"]


def test_nicht_polygon_wird_abgelehnt(client):
    r = client.post(
        "/api/areas",
        json={"name": "punkt", "geometry": {"type": "Point", "coordinates": [6.5, 50.5]}},
    )
    assert r.status_code == 422


# ---------------------------------------------------------- Session-Lebenszyklus


def test_session_anlegen_und_beenden(client):
    r = client.post("/api/sessions", json={"dog_name": "Fina"})
    assert r.status_code == 201
    angelegt = r.json()
    assert angelegt["started_at"] is not None
    assert angelegt["ended_at"] is None
    assert angelegt["dog_name"] == "Fina"

    ende = client.patch(
        f"/api/sessions/{angelegt['id']}/end",
        json={"ended_at": ENDE.isoformat(), "dog_work_minutes": 95, "subjective_rating": "gut"},
    )
    assert ende.status_code == 200
    beendet = ende.json()
    assert beendet["ended_at"] is not None
    assert beendet["dog_work_minutes"] == 95
    assert beendet["subjective_rating"] == "gut"
    assert beendet["already_ended"] is False


def test_session_mit_unbekanntem_gebiet_wird_abgelehnt(client):
    r = client.post("/api/sessions", json={"area_id": str(uuid.uuid4())})
    assert r.status_code == 422


def test_ende_unbekannter_session_ist_404(client):
    r = client.patch(f"/api/sessions/{uuid.uuid4()}/end", json={})
    assert r.status_code == 404


# ------------------------------------------------------------- Einfrieren


def test_einfrieren_mit_vollstaendigen_daten(client, db_session):
    area_id = _area(client)
    _snapshots(db_session, area_id)
    session_id = client.post("/api/sessions", json={"area_id": area_id}).json()["id"]

    body = _ende(client, session_id).json()

    assert body["temperature_c"] == pytest.approx(14.0)
    assert body["wind_kmh"] == pytest.approx(8.0)
    assert body["soil_moisture_0_7"] == pytest.approx(0.25)
    assert body["precip_prev_7d_mm"] == pytest.approx(22.0)
    # season 30 + Bodenfeuchte 30 + Regen 22 + Feld 15
    assert body["conditions_score"] == pytest.approx(97.0)
    assert body["score_reason"] is None


def test_fehlender_wind_verhindert_den_score(client, db_session):
    """Ehrlichkeitsprinzip: lieber kein Score als einer aus geratenem Wind.

    Wind kommt seit Migration 0003 aus conditions_snapshot.wind_kmh; die
    frühere Verabredung über den raw-JSONB-Schlüssel ist entfallen.
    """
    area_id = _area(client)
    _snapshots(db_session, area_id, wind=None)
    session_id = client.post("/api/sessions", json={"area_id": area_id}).json()["id"]

    body = _ende(client, session_id).json()

    assert body["conditions_score"] is None
    assert "wind_kmh" in body["score_reason"]
    # Die uebrigen Werte werden trotzdem eingefroren.
    assert body["temperature_c"] == pytest.approx(14.0)
    assert body["precip_prev_7d_mm"] == pytest.approx(22.0)
    assert body["wind_kmh"] is None


def test_unvollstaendige_regenreihe_verhindert_den_score(client, db_session):
    area_id = _area(client)
    _snapshots(db_session, area_id, tage=10)
    session_id = client.post("/api/sessions", json={"area_id": area_id}).json()["id"]

    body = _ende(client, session_id).json()

    assert body["conditions_score"] is None
    assert "4 von 14" in body["score_reason"]


def test_gebiet_ohne_snapshots(client):
    area_id = _area(client)
    session_id = client.post("/api/sessions", json={"area_id": area_id}).json()["id"]

    body = _ende(client, session_id).json()

    assert body["conditions_score"] is None
    assert "conditions_snapshot" in body["score_reason"]
    assert body["temperature_c"] is None


def test_session_ohne_area_id_kann_enden(client):
    """Ein Feldgang ohne vorher angelegtes Gebiet bleibt moeglich."""
    session_id = client.post("/api/sessions", json={"dog_name": "Fina"}).json()["id"]

    r = _ende(client, session_id)
    assert r.status_code == 200
    body = r.json()

    assert body["ended_at"] is not None
    assert body["conditions_score"] is None
    assert body["temperature_c"] is None
    assert body["wind_kmh"] is None
    assert body["precip_prev_7d_mm"] is None
    assert "area_id" in body["score_reason"]


# ---------------------------------------------------------- Doppeltes Ende


def test_zweites_ende_rechnet_nichts_neu(client, db_session):
    """Eingefroren heisst eingefroren."""
    area_id = _area(client)
    _snapshots(db_session, area_id)
    session_id = client.post("/api/sessions", json={"area_id": area_id}).json()["id"]

    erstes = _ende(client, session_id).json()
    assert erstes["already_ended"] is False

    # Zwischendurch aendert sich die Wetterlage — der eingefrorene Wert nicht.
    db_session.query(ConditionsSnapshot).filter(
        ConditionsSnapshot.area_id == uuid.UUID(area_id),
        ConditionsSnapshot.date == date(2026, 8, 1),
    ).update({"temp_mean_c": 33.0})
    db_session.commit()

    zweites = client.patch(
        f"/api/sessions/{session_id}/end",
        json={"ended_at": datetime(2026, 8, 2, 9, 0, tzinfo=UTC).isoformat()},
    )
    assert zweites.status_code == 200
    body = zweites.json()

    assert body["already_ended"] is True
    assert body["ended_at"] == erstes["ended_at"]
    assert body["temperature_c"] == pytest.approx(erstes["temperature_c"])
    assert body["conditions_score"] == pytest.approx(erstes["conditions_score"])
    assert "eingefroren" in body["score_reason"]
