"""GET /api/signals (Spec §4, §12, AP10b).

Der Endpunkt fehlte bis AP10b komplett — angelegt werden konnten Signale,
gelesen nicht. Aufbau bewusst wie bei GET /api/finds: bbox-Filter, neueste
zuerst, keine Pagination.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.db

JETZT = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)

# Eifel, innerhalb der Basiskarten-Bbox.
SOETENICH = (50.55, 6.55)
AACHEN = (50.78, 6.08)


def _anlegen(client, lat: float, lon: float, *, observed_at: datetime | None, typ: str) -> str:
    antwort = client.post(
        "/api/signals",
        json={
            "client_uuid": str(uuid.uuid4()),
            "lat": lat,
            "lon": lon,
            "signal_type": typ,
            "observed_at": observed_at.isoformat() if observed_at else None,
        },
    )
    assert antwort.status_code == 201, antwort.text
    return antwort.json()["id"]


def test_liste_braucht_eine_sitzung(anon_client, db_session):
    assert anon_client.get("/api/signals").status_code == 401


def test_leere_liste(client):
    assert client.get("/api/signals").json() == []


def test_neueste_zuerst(client):
    aelter = _anlegen(
        client, *SOETENICH, observed_at=JETZT - timedelta(days=3), typ="truffelfliege"
    )
    neuer = _anlegen(client, *SOETENICH, observed_at=JETZT - timedelta(days=1), typ="brule_erkannt")

    ids = [eintrag["id"] for eintrag in client.get("/api/signals").json()]

    assert ids == [neuer, aelter]


def test_signal_ohne_zeitpunkt_steht_hinten(client):
    """observed_at ist optional (Spec §4). PostgreSQL sortierte NULL bei DESC
    von sich aus nach oben — ein Signal ohne Zeitpunkt waere dann das
    "neueste"."""
    ohne = _anlegen(client, *SOETENICH, observed_at=None, typ="habitat_auffaellig")
    mit = _anlegen(client, *SOETENICH, observed_at=JETZT - timedelta(days=9), typ="truffelfliege")

    ids = [eintrag["id"] for eintrag in client.get("/api/signals").json()]

    assert ids == [mit, ohne]


def test_bbox_filtert_raeumlich(client):
    drin = _anlegen(client, *SOETENICH, observed_at=JETZT, typ="truffelfliege")
    _anlegen(client, *AACHEN, observed_at=JETZT, typ="truffelfliege")

    body = client.get("/api/signals", params={"bbox": "6.4,50.4,6.7,50.7"}).json()

    assert [eintrag["id"] for eintrag in body] == [drin]


def test_zeitfenster_filtert(client):
    alt = JETZT - timedelta(days=30)
    _anlegen(client, *SOETENICH, observed_at=alt, typ="truffelfliege")
    neu = _anlegen(client, *SOETENICH, observed_at=JETZT, typ="truffelfliege")

    body = client.get(
        "/api/signals", params={"from": (JETZT - timedelta(days=2)).isoformat()}
    ).json()

    assert [eintrag["id"] for eintrag in body] == [neu]


@pytest.mark.parametrize("boesartig", ["6.4,50.4,6.7", "a,b,c,d", ""])
def test_unbrauchbare_bbox_ist_422(client, boesartig):
    """4xx, damit die Offline-Queue den Aufruf nicht wiederholt."""
    assert client.get("/api/signals", params={"bbox": boesartig}).status_code == 422


def test_liste_gibt_koordinaten_und_typ_zurueck(client):
    _anlegen(client, *SOETENICH, observed_at=JETZT, typ="hund_anzeige_ohne_fund")

    eintrag = client.get("/api/signals").json()[0]

    assert eintrag["lat"] == pytest.approx(SOETENICH[0])
    assert eintrag["lon"] == pytest.approx(SOETENICH[1])
    assert eintrag["signal_type"] == "hund_anzeige_ohne_fund"
