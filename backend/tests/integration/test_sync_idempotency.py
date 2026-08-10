"""Offline-Sync und Idempotenz — Invarianten 1, 2, 3, 6 am HTTP-Vertrag.

Die Offline-Queue des Clients wiederholt POSTs beliebig oft; der Server
darf daraus nie Duplikate machen (client_uuid ist der Schlüssel).
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.core import params

pytestmark = pytest.mark.db


def _payload(**overrides) -> dict:
    base = {
        "client_uuid": str(uuid.uuid4()),
        "lat": 50.53,
        "lon": 6.55,
        "gps_accuracy_m": 6.5,
        "found_at": datetime(2026, 8, 1, 9, 30, tzinfo=UTC).isoformat(),
    }
    base.update(overrides)
    return base


def test_erster_post_legt_fund_mit_feld_defaults_an(client):
    r = client.post("/api/finds", json=_payload())
    assert r.status_code == 201
    body = r.json()
    # Invariante 6: kein Rateklick im Feld — offene Bestimmung ist Default.
    assert body["species_guess"] == "tuber_spec"
    assert body["id_pending"] is True
    assert "id" in body


def test_wiederholter_post_erzeugt_kein_duplikat(client):
    p = _payload()
    r1 = client.post("/api/finds", json=p)
    r2 = client.post("/api/finds", json=p)
    r3 = client.post("/api/finds", json=p)
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r3.status_code == 200
    assert r1.json()["id"] == r2.json()["id"] == r3.json()["id"]

    liste = client.get("/api/finds").json()
    assert len(liste) == 1


def test_fund_ohne_genauigkeit_wird_abgelehnt(client):
    """Invariante 1: verletzt = Bug, keine Diskussion."""
    p = _payload()
    del p["gps_accuracy_m"]
    r = client.post("/api/finds", json=p)
    assert r.status_code == 422
    assert client.get("/api/finds").json() == []


def test_fund_mit_kilometer_genauigkeit_wird_blockiert(client):
    """Invariante 2: iOS ohne 'Genauer Standort' liefert 3-9 km."""
    r = client.post("/api/finds", json=_payload(gps_accuracy_m=4200.0))
    assert r.status_code == 422
    assert client.get("/api/finds").json() == []
    # Schwelle kommt aus params, nicht hartkodiert:
    knapp_drunter = client.post(
        "/api/finds", json=_payload(gps_accuracy_m=params.FIND_ACCURACY_BLOCK_M - 1)
    )
    assert knapp_drunter.status_code == 201


def test_signal_post_ist_ebenfalls_idempotent(client):
    p = {
        "client_uuid": str(uuid.uuid4()),
        "lat": 50.531,
        "lon": 6.552,
        "observed_at": datetime(2026, 8, 1, 10, 0, tzinfo=UTC).isoformat(),
        "signal_type": "hund_anzeige_ohne_fund",
        "dog_confidence": "stark",
    }
    r1 = client.post("/api/signals", json=p)
    r2 = client.post("/api/signals", json=p)
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_revisit_due_wird_serverseitig_abgeleitet(client):
    """Spec §10: revisit_due = found_at + params.REVISIT_OFFSET, vom Server
    gesetzt. Der Client darf den Termin nicht bestimmen — sonst driftet die
    Wiederbesuchslogik mit der Uhr des Geräts."""
    found_at = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)
    r = client.post("/api/finds", json=_payload(found_at=found_at.isoformat()))
    assert r.status_code == 201
    erwartet = (found_at + params.REVISIT_OFFSET).date().isoformat()
    assert r.json()["revisit_due"] == erwartet


def test_revisit_due_vom_client_wird_ignoriert(client):
    """Ein mitgeschickter Termin darf die serverseitige Ableitung nicht
    überschreiben."""
    found_at = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)
    r = client.post(
        "/api/finds",
        json=_payload(found_at=found_at.isoformat(), revisit_due="2099-01-01"),
    )
    assert r.status_code == 201
    assert r.json()["revisit_due"] == (found_at + params.REVISIT_OFFSET).date().isoformat()
