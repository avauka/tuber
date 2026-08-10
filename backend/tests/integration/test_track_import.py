"""Track-Import — Spec §9/§12, Invariante 5.

Der Rohtrack ist das Original und bleibt es. Coverage entsteht daneben aus
den bereinigten Punkten und darf ausfallen, ohne den Rohtrack mitzunehmen.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.models.core import Session as SessionModel

pytestmark = pytest.mark.db

# Die Fixtures laufen alle vom 01.08.2026 09:00:00Z bis 09:00:59Z (60 Punkte).
TRACK_VON = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)
TRACK_BIS = datetime(2026, 8, 1, 9, 0, 59, tzinfo=UTC)

# Beide Punkte melden hdop 8.0 -> 40 m Schaetzung -> ueber TRACK_ACCURACY_MAX_M.
# Der Rohtrack ist speicherbar, nach der Bereinigung bleibt nichts uebrig.
ZWEI_ZU_UNGENAUE_PUNKTE = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>ungenau</name><trkseg>
    <trkpt lat="50.5300000" lon="6.5500000"><time>2026-08-01T09:00:00Z</time><hdop>8.0</hdop></trkpt>
    <trkpt lat="50.5300000" lon="6.5500170"><time>2026-08-01T09:00:01Z</time><hdop>8.0</hdop></trkpt>
  </trkseg></trk>
</gpx>
"""


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def _upload(client, content: bytes, name: str = "track.gpx"):
    return client.post(
        "/api/tracks/import",
        files={"file": (name, content, "application/gpx+xml")},
    )


def _fixture_bytes(gpx_fixture_dir, name: str) -> bytes:
    return (gpx_fixture_dir / name).read_bytes()


def _session(db, started_at: datetime, ended_at: datetime) -> uuid.UUID:
    s = SessionModel(id=uuid.uuid4(), started_at=started_at, ended_at=ended_at)
    db.add(s)
    db.commit()
    return s.id


# ------------------------------------------------------------- Happy path


def test_import_legt_rohtrack_und_coverage_an(client, gpx_fixture_dir):
    r = _upload(client, _fixture_bytes(gpx_fixture_dir, "track_accuracy_meters.gpx"))
    assert r.status_code == 201
    body = r.json()

    # Track-Felder beschreiben den ROHEN Track.
    assert body["point_count"] == 60
    assert body["length_m"] > 0
    assert body["mean_accuracy_m"] == pytest.approx(6.0, rel=0.2)
    assert body["source_filename"] == "track.gpx"

    # Coverage entsteht aus den bereinigten Punkten.
    assert body["coverage"] is not None
    assert body["coverage_skipped_reason"] is None
    assert body["coverage"]["confidence"] == "hoch"
    assert body["coverage"]["area_m2"] > 0
    assert body["coverage"]["track_id"] == body["track_id"]


def test_rohtrack_behaelt_den_ausreisser(client, db_session, gpx_fixture_dir):
    """Invariante 5: Der Geschwindigkeitsausreisser fliegt aus der Coverage,
    nicht aus dem gespeicherten Rohtrack."""
    r = _upload(client, _fixture_bytes(gpx_fixture_dir, "track_speed_outlier.gpx"))
    assert r.status_code == 201
    body = r.json()

    assert body["point_count"] == 60
    assert body["dropped_speed"] >= 1
    assert body["kept_count"] < body["point_count"]
    assert body["coverage"] is not None

    gespeichert = db_session.execute(
        text("SELECT ST_NumPoints(geom::geometry) FROM track WHERE id = :i"),
        {"i": body["track_id"]},
    ).scalar()
    assert gespeichert == 60


# --------------------------------------------------------------- Duplikat


def test_zweiter_identischer_upload_wird_abgelehnt(client, gpx_fixture_dir):
    """Ein Upload ist eine bewusste Nutzeraktion, kein Queue-Replay —
    hier ist die ehrliche Ablehnung richtig, nicht stille Idempotenz."""
    content = _fixture_bytes(gpx_fixture_dir, "track_accuracy_meters.gpx")
    erster = _upload(client, content)
    assert erster.status_code == 201

    zweiter = _upload(client, content)
    assert zweiter.status_code == 409
    assert zweiter.json()["detail"]["existing_track_id"] == erster.json()["track_id"]


# ------------------------------------------------------- Session-Zuordnung


def test_session_zuordnung_eindeutig(client, db_session, gpx_fixture_dir):
    session_id = _session(db_session, TRACK_VON, TRACK_BIS)
    r = _upload(client, _fixture_bytes(gpx_fixture_dir, "track_accuracy_meters.gpx"))
    assert r.status_code == 201
    assert r.json()["session_assignment"] == "unique"
    assert r.json()["session_id"] == str(session_id)


def test_session_zuordnung_ohne_ueberlappung(client, db_session, gpx_fixture_dir):
    _session(
        db_session,
        datetime(2026, 8, 1, 14, 0, tzinfo=UTC),
        datetime(2026, 8, 1, 15, 0, tzinfo=UTC),
    )
    r = _upload(client, _fixture_bytes(gpx_fixture_dir, "track_accuracy_meters.gpx"))
    assert r.status_code == 201
    assert r.json()["session_assignment"] == "none"
    assert r.json()["session_id"] is None


def test_session_zuordnung_bei_gleichstand_bleibt_offen(client, db_session, gpx_fixture_dir):
    """Gleich starke Ueberlappung: der Server ordnet nicht per Muenzwurf zu."""
    _session(db_session, TRACK_VON, TRACK_BIS)
    _session(db_session, TRACK_VON, TRACK_BIS)
    r = _upload(client, _fixture_bytes(gpx_fixture_dir, "track_accuracy_meters.gpx"))
    assert r.status_code == 201
    assert r.json()["session_assignment"] == "ambiguous"
    assert r.json()["session_id"] is None


def test_staerkere_ueberlappung_gewinnt(client, db_session, gpx_fixture_dir):
    schwach = _session(
        db_session,
        datetime(2026, 8, 1, 8, 0, tzinfo=UTC),
        datetime(2026, 8, 1, 9, 0, 10, tzinfo=UTC),
    )
    stark = _session(db_session, TRACK_VON, TRACK_BIS)
    r = _upload(client, _fixture_bytes(gpx_fixture_dir, "track_accuracy_meters.gpx"))
    assert r.status_code == 201
    assert r.json()["session_id"] == str(stark)
    assert r.json()["session_id"] != str(schwach)


# ----------------------------------------------- Coverage faellt aus, Track bleibt


def test_zu_wenige_bereinigte_punkte_ueberspringt_coverage(client, db_session):
    r = _upload(client, ZWEI_ZU_UNGENAUE_PUNKTE, name="ungenau.gpx")
    assert r.status_code == 201
    body = r.json()

    assert body["coverage"] is None
    assert body["coverage_skipped_reason"]
    assert body["kept_count"] == 0
    assert body["dropped_accuracy"] == 2

    # Entscheidend: der Rohtrack ist trotzdem gespeichert (Invariante 5).
    assert body["point_count"] == 2
    vorhanden = db_session.execute(
        text("SELECT count(*) FROM track WHERE id = :i"), {"i": body["track_id"]}
    ).scalar()
    assert vorhanden == 1
    keine_coverage = db_session.execute(
        text("SELECT count(*) FROM coverage WHERE track_id = :i"), {"i": body["track_id"]}
    ).scalar()
    assert keine_coverage == 0


# ------------------------------------------------------------ Abwehr/Fehler


def test_zu_grosse_datei_wird_abgelehnt(client):
    zu_gross = b"<gpx>" + b"x" * (10 * 1024 * 1024 + 1)
    r = _upload(client, zu_gross, name="riesig.gpx")
    assert r.status_code == 413


def test_unparsebares_gpx_ist_422(client):
    r = _upload(client, b"das ist kein XML", name="kaputt.gpx")
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)


def test_gpx_ohne_zeitstempel_ist_422(client):
    ohne_zeit = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        b'<trkpt lat="50.53" lon="6.55"></trkpt>'
        b'<trkpt lat="50.53" lon="6.56"></trkpt>'
        b"</trkseg></trk></gpx>"
    )
    r = _upload(client, ohne_zeit, name="ohne_zeit.gpx")
    assert r.status_code == 422


def test_entity_expansion_wird_abgewehrt(client):
    """Backlog AP5: der Upload-Pfad muss gegen XML-Entity-Expansion haerten."""
    billion_laughs = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE gpx [<!ENTITY a "aaaaaaaaaa">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
        b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
        b'<gpx version="1.1"><trk><name>&c;</name></trk></gpx>'
    )
    r = _upload(client, billion_laughs, name="angriff.gpx")
    assert r.status_code == 422


# ------------------------------------------------------------- GET coverage


def test_get_coverage_liefert_polygon_je_track(client, gpx_fixture_dir):
    _upload(client, _fixture_bytes(gpx_fixture_dir, "track_accuracy_meters.gpx"))

    r = client.get("/api/coverage", params={"bbox": "6.5,50.5,6.6,50.6"})
    assert r.status_code == 200
    features = r.json()
    assert len(features) == 1
    assert features[0]["geometry"]["type"] == "Polygon"
    assert features[0]["area_m2"] > 0

    # Bbox anderswo: nichts.
    leer = client.get("/api/coverage", params={"bbox": "1.0,1.0,1.1,1.1"})
    assert leer.status_code == 200
    assert leer.json() == []


def test_get_coverage_mit_kaputter_bbox_ist_422(client):
    r = client.get("/api/coverage", params={"bbox": "1,2,3"})
    assert r.status_code == 422
