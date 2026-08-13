"""Eignungskarte: Gewichte, Auslieferung, Upload (ADR 0008, AP17a).

Kein echtes Archiv im Testlauf — die Route liest die Datei nur, sie
versteht sie nicht. Geprüft wird, was schiefgehen kann: dass Range-Requests
wirklich 206 liefern, dass eine fehlende Karte 503 ergibt und nicht 500,
und dass ein misslungener Upload die bestehende Karte in Ruhe lässt.
"""

import json

import pytest

from app.services.suitability import META_NAME, PMTILES_MAGIC, TILES_NAME, TILES_ROUTE

pytestmark = pytest.mark.db

# Spec §12: Der Auslieferungspfad heisst tiles.pmtiles, die Datei auf dem
# Volume suitability.pmtiles. Beides absichtlich getrennt.
KACHEL_PFAD = f"/api/suitability/{TILES_ROUTE}"

# Kein echtes PMTiles-Archiv, aber mit gültiger Signatur — mehr prüft der
# Dienst nicht, und mehr soll er auch nicht prüfen.
ARCHIV = PMTILES_MAGIC + bytes(range(256)) * 8

META = {
    "gewichtssatz_version": 1,
    "faktoren": {"kalk": 100.0},
    "faktoren_fehlend": ["wasser", "exposition", "wirtsbaum", "struktur", "klima"],
    "rasterweite_m": 20,
    "epsg_verarbeitung": 25832,
    "bbox_wgs84": [5.4, 49.7, 7.2, 51.1],
    "klassengrenzen": [25.0, 50.0, 75.0],
    "min_zoom": 6,
    "max_zoom": 13,
    "flaechen": 7934,
    "quellen": [{"name": "IS GK 100", "lizenz": "dl-de/by-2-0"}],
    "bytes": len(ARCHIV),
    "sha256": "a" * 64,
    "generated_at": "2026-08-13T06:41:49Z",
}


@pytest.fixture()
def karten_verzeichnis(tmp_path, monkeypatch):
    monkeypatch.setenv("SUITABILITY_DIR", str(tmp_path))
    (tmp_path / TILES_NAME).write_bytes(ARCHIV)
    (tmp_path / META_NAME).write_text(json.dumps(META))
    return tmp_path


@pytest.fixture()
def leeres_verzeichnis(tmp_path, monkeypatch):
    monkeypatch.setenv("SUITABILITY_DIR", str(tmp_path))
    return tmp_path


# ------------------------------------------------------------- Gewichtssatz


def test_gewichtssatz_liegt_versioniert_in_der_datenbank(db_session):
    """Version 1 aus ADR 0008 §3, angelegt von der Migration.

    Die Tabelle ist der Versionierungsanker: `suitability.meta.json` hält
    fest, mit welcher Version die Kacheln entstanden sind. Ohne das liesse
    sich in Phase 3 nicht rekonstruieren, welche Karte zu welchem Fund
    gehoerte (ADR 0008 §7).
    """
    from sqlalchemy import select

    from app.models.core import SuitabilityWeightSet

    satz = db_session.execute(
        select(SuitabilityWeightSet).where(SuitabilityWeightSet.is_active)
    ).scalar_one()

    assert satz.version == 1
    assert satz.weights["kalk"] == 30
    assert sum(satz.weights.values()) == pytest.approx(100)
    assert set(satz.weights) == {
        "kalk",
        "wasser",
        "exposition",
        "wirtsbaum",
        "struktur",
        "klima",
    }


def test_hoechstens_ein_aktiver_satz(db_session):
    """In der Datenbank erzwungen, nicht nur in der Anwendung.

    Zwei aktive Saetze waeren im Nachhinein nicht aufloesbar: Man wuesste
    nicht, mit welchem die vorhandenen Kacheln entstanden sind.
    """
    import uuid

    from sqlalchemy.exc import IntegrityError

    from app.models.core import SuitabilityWeightSet

    db_session.add(
        SuitabilityWeightSet(id=uuid.uuid4(), version=99, weights={"kalk": 100}, is_active=True)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("methode", ["get", "post", "patch"])
def test_kein_endpunkt_fuer_den_gewichtssatz(client, methode):
    """AP17a-Nachtrag B6: bewusst entfernt.

    Der Endpunkt haette den aktiven DB-Satz geliefert, waehrend der Planer
    die tatsaechlich angewandten Gewichte aus suitability.meta.json liest.
    Nach einer Umgewichtung ohne Pipelinelauf haette er eine Zahl geliefert,
    die zu keiner ausgelieferten Karte gehoert. Zurueck kommt er mit der
    Settings-Seite.
    """
    antwort = getattr(client, methode)("/api/suitability/weights")

    assert antwort.status_code in (404, 405)


# ------------------------------------------------------------ Auslieferung


def test_kacheln_brauchen_eine_sitzung(anon_client, karten_verzeichnis):
    assert anon_client.get(KACHEL_PFAD).status_code == 401


def test_voller_abruf_meldet_range_faehigkeit(client, karten_verzeichnis):
    antwort = client.get(KACHEL_PFAD)

    assert antwort.status_code == 200
    assert antwort.content == ARCHIV
    assert antwort.headers["accept-ranges"] == "bytes"
    # Doppeltes gzip über eine Teilantwort verschöbe die Byte-Offsets.
    assert "content-encoding" not in antwort.headers


def test_range_liefert_206_mit_genau_diesen_bytes(client, karten_verzeichnis):
    antwort = client.get(KACHEL_PFAD, headers={"Range": "bytes=8-39"})

    assert antwort.status_code == 206
    assert antwort.headers["content-range"] == f"bytes 8-39/{len(ARCHIV)}"
    assert antwort.content == ARCHIV[8:40]


def test_unsinniger_bereich_ist_416(client, karten_verzeichnis):
    antwort = client.get(KACHEL_PFAD, headers={"Range": f"bytes={len(ARCHIV) + 10}-"})

    assert antwort.status_code == 416


def test_fehlende_kacheln_sind_503(client, leeres_verzeichnis):
    """503, nicht 500: Die Pipeline ist noch nicht gelaufen."""
    antwort = client.get(KACHEL_PFAD)

    assert antwort.status_code == 503
    assert "geoprocessing" in antwort.json()["detail"]


def test_meta_nennt_faktoren_und_gewichtssatz(client, karten_verzeichnis):
    """Invariante 10: Der Score muss aufschlüsselbar bleiben."""
    body = client.get("/api/suitability/meta").json()

    assert body["gewichtssatz_version"] == 1
    assert body["faktoren"] == {"kalk": 100.0}
    assert "wasser" in body["faktoren_fehlend"]


def test_fehlende_meta_ist_503(client, leeres_verzeichnis):
    antwort = client.get("/api/suitability/meta")

    assert antwort.status_code == 503
    assert "geoprocessing" in antwort.json()["detail"]


def test_unvollstaendige_meta_ist_503(client, leeres_verzeichnis):
    (leeres_verzeichnis / META_NAME).write_text('{"faktoren": {}}')

    antwort = client.get("/api/suitability/meta")

    assert antwort.status_code == 503


# ------------------------------------------------------------------ Upload


def _hochladen(client, kacheln: bytes, meta: dict | str):
    rohtext = meta if isinstance(meta, str) else json.dumps(meta)
    return client.post(
        "/api/suitability/upload",
        files={
            "tiles": (TILES_NAME, kacheln, "application/octet-stream"),
            "meta": (META_NAME, rohtext, "application/json"),
        },
    )


def test_upload_braucht_eine_sitzung(anon_client, leeres_verzeichnis):
    assert _hochladen(anon_client, ARCHIV, META).status_code == 401


def test_upload_legt_beide_dateien_ab(client, leeres_verzeichnis):
    antwort = _hochladen(client, ARCHIV, META)

    assert antwort.status_code == 201
    assert antwort.json()["gewichtssatz_version"] == 1
    assert antwort.json()["faktoren"] == ["kalk"]
    assert (leeres_verzeichnis / TILES_NAME).read_bytes() == ARCHIV
    assert json.loads((leeres_verzeichnis / META_NAME).read_text())["faktoren"] == {"kalk": 100.0}

    # Danach ist die Karte auch abrufbar.
    assert client.get(KACHEL_PFAD).status_code == 200


def test_ohne_pmtiles_signatur_wird_abgelehnt(client, karten_verzeichnis):
    """Eine falsche Datei darf nie zur aktiven Karte werden."""
    antwort = _hochladen(client, b"das ist ein PDF" + bytes(200), META)

    assert antwort.status_code == 422
    assert "PMTiles" in antwort.json()["detail"]
    # Die bestehende Karte ist unberührt.
    assert (karten_verzeichnis / TILES_NAME).read_bytes() == ARCHIV
    assert not list(karten_verzeichnis.glob("*.tmp"))


def test_metadatei_ohne_pflichtfelder_wird_abgelehnt(client, karten_verzeichnis):
    antwort = _hochladen(client, ARCHIV, {"faktoren": {"kalk": 100}})

    assert antwort.status_code == 422
    assert "gewichtssatz_version" in antwort.json()["detail"]
    assert (karten_verzeichnis / TILES_NAME).read_bytes() == ARCHIV


def test_kaputte_metadatei_wird_abgelehnt(client, karten_verzeichnis):
    antwort = _hochladen(client, ARCHIV, "{kein json")

    assert antwort.status_code == 422
    assert (karten_verzeichnis / TILES_NAME).read_bytes() == ARCHIV
    assert not list(karten_verzeichnis.glob("*.tmp"))


def test_zu_wenig_platz_bricht_vor_dem_schreiben_ab(client, karten_verzeichnis, monkeypatch):
    """Auf demselben Volume liegen die Backups (ADR 0004, AP15).

    Ein volles Volume bricht die Rotation still — auffallen würde es erst
    beim Restore.
    """
    from collections import namedtuple

    from app.services import suitability

    platz = namedtuple("platz", "total used free")
    monkeypatch.setattr(
        suitability.shutil,
        "disk_usage",
        lambda _p: platz(5_000_000_000, 4_500_000_000, 500_000_000),
    )

    antwort = _hochladen(client, ARCHIV, META)

    assert antwort.status_code == 422
    assert "Zu wenig Platz" in antwort.json()["detail"]
    assert (karten_verzeichnis / TILES_NAME).read_bytes() == ARCHIV


def test_erneuter_upload_ersetzt_die_karte(client, karten_verzeichnis):
    neu = PMTILES_MAGIC + b"zweiter-lauf"
    zweite_meta = {**META, "gewichtssatz_version": 2, "generated_at": "2026-09-01T10:00:00Z"}

    antwort = _hochladen(client, neu, zweite_meta)

    assert antwort.status_code == 201
    assert (karten_verzeichnis / TILES_NAME).read_bytes() == neu
    assert client.get("/api/suitability/meta").json()["gewichtssatz_version"] == 2
