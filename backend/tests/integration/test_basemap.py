"""Auslieferung der Basiskarte und Ausliefern der SPA (ADR 0002, AP10b).

Der Range-Request ist hier der eigentliche Prüfstein: PMTiles holt sich
Kachelbereiche über `Range`, und ein Server, der stattdessen 200 mit der
ganzen Datei antwortet, ergibt eine Karte, die 208 MB laedt und trotzdem
leer bleibt. Deshalb wird der Bereich wirklich angefordert und der Inhalt
byteweise verglichen.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.basemap import ARCHIVE_NAME, META_NAME

pytestmark = pytest.mark.db

ARCHIV_PFAD = f"/api/basemap/{ARCHIVE_NAME}"

# Kein echtes PMTiles-Archiv: Die Route liest die Datei nur, sie versteht sie
# nicht. Fuer Range-Arithmetik genuegt bekannter Inhalt.
INHALT = bytes(range(256)) * 8

META = {
    "build_date": "20260812",
    "osm_data_timestamp": "2026-08-12T04:00:00Z",
    "tileset_version": "4.15.2",
    "bbox": [5.4, 49.7, 7.2, 51.1],
    "maxzoom": 14,
    "bytes": len(INHALT),
    "sha256": "a" * 64,
    "fetched_at": "2026-08-12T12:17:59Z",
}


@pytest.fixture()
def basemap_verzeichnis(tmp_path, monkeypatch):
    monkeypatch.setenv("BASEMAP_DIR", str(tmp_path))
    (tmp_path / ARCHIVE_NAME).write_bytes(INHALT)
    (tmp_path / META_NAME).write_text(json.dumps(META))
    return tmp_path


@pytest.fixture()
def leeres_verzeichnis(tmp_path, monkeypatch):
    """Volume haengt, aber der Extract-Job ist noch nicht gelaufen."""
    monkeypatch.setenv("BASEMAP_DIR", str(tmp_path))
    return tmp_path


# ------------------------------------------------------------------- Zugang


def test_archiv_braucht_eine_sitzung(anon_client, basemap_verzeichnis):
    """Selbstgehostete Datei, kein oeffentlicher Tile-Server (ADR 0005)."""
    assert anon_client.get(ARCHIV_PFAD).status_code == 401


def test_meta_braucht_eine_sitzung(anon_client, basemap_verzeichnis):
    assert anon_client.get("/api/basemap/meta").status_code == 401


# -------------------------------------------------------------- Range (206)


def test_voller_abruf_meldet_range_faehigkeit(client, basemap_verzeichnis):
    antwort = client.get(ARCHIV_PFAD)

    assert antwort.status_code == 200
    assert antwort.content == INHALT
    assert antwort.headers["accept-ranges"] == "bytes"
    assert int(antwort.headers["content-length"]) == len(INHALT)
    # Doppeltes gzip ueber eine Teilantwort wuerde die Byte-Offsets
    # verschieben, auf die PMTiles baut.
    assert "content-encoding" not in antwort.headers


def test_range_liefert_206_mit_genau_diesen_bytes(client, basemap_verzeichnis):
    antwort = client.get(ARCHIV_PFAD, headers={"Range": "bytes=16-47"})

    assert antwort.status_code == 206
    assert antwort.headers["content-range"] == f"bytes 16-47/{len(INHALT)}"
    assert int(antwort.headers["content-length"]) == 32
    assert antwort.content == INHALT[16:48]


def test_range_ohne_ende_geht_bis_zum_dateiende(client, basemap_verzeichnis):
    """Genau die Form, in der pmtiles den Header liest."""
    antwort = client.get(ARCHIV_PFAD, headers={"Range": "bytes=2000-"})

    assert antwort.status_code == 206
    assert antwort.headers["content-range"] == f"bytes 2000-{len(INHALT) - 1}/{len(INHALT)}"
    assert antwort.content == INHALT[2000:]


def test_unsinniger_bereich_ist_416(client, basemap_verzeichnis):
    antwort = client.get(ARCHIV_PFAD, headers={"Range": f"bytes={len(INHALT) + 10}-"})

    assert antwort.status_code == 416
    assert antwort.headers["content-range"] == f"bytes */{len(INHALT)}"


def test_keine_kompressions_middleware_auf_dem_weg(client, basemap_verzeichnis):
    """Haelt fest, was der Kommentar in api/basemap.py verspricht.

    Eine global eingehaengte GZipMiddleware wuerde die Antwort ein zweites
    Mal komprimieren — die Kacheln im Archiv sind es bereits — und damit die
    Byte-Offsets zerstoeren. Der Test schlaegt an, sobald jemand eine
    einbaut, ohne diese Route auszunehmen.
    """
    from app.main import app

    namen = [middleware.cls.__name__ for middleware in app.user_middleware]
    assert "GZipMiddleware" not in namen, namen


# --------------------------------------------------------------- Metadaten


def test_meta_traegt_den_datenstand(client, basemap_verzeichnis):
    """Ohne diese Werte gibt es keine Attribution mit Datenstand (Spec §15)."""
    body = client.get("/api/basemap/meta").json()

    assert body["osm_data_timestamp"] == "2026-08-12T04:00:00Z"
    assert body["tileset_version"] == "4.15.2"
    assert body["bbox"] == [5.4, 49.7, 7.2, 51.1]
    assert body["maxzoom"] == 14


# ------------------------------------------------------- Karte fehlt (503)


def test_fehlendes_archiv_ist_503(client, leeres_verzeichnis):
    """503, nicht 500: Der Job ist noch nicht gelaufen — ein Zustand des
    Dienstes, kein Programmfehler."""
    antwort = client.get(ARCHIV_PFAD)

    assert antwort.status_code == 503
    assert ARCHIVE_NAME in antwort.json()["detail"]


def test_fehlende_metadaten_sind_503(client, leeres_verzeichnis):
    antwort = client.get("/api/basemap/meta")

    assert antwort.status_code == 503
    assert "basemap_extract" in antwort.json()["detail"]


def test_unvollstaendige_metadaten_sind_503(client, leeres_verzeichnis):
    """Eine Metadatei ohne Datenstand ist so unbrauchbar wie keine."""
    (leeres_verzeichnis / META_NAME).write_text('{"build_date": "20260812"}')

    antwort = client.get("/api/basemap/meta")

    assert antwort.status_code == 503
    assert "unvollstaendig" in antwort.json()["detail"]


# ----------------------------------------------------------- SPA-Ausliefern


@pytest.fixture()
def spa_client(tmp_path, monkeypatch, auth_env):
    """App mit gebautem Frontend — das Mount entsteht beim App-Aufbau."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>TUBER</title>")
    (dist / "assets" / "app.js").write_text("console.log('tuber')")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))

    with TestClient(create_app(), base_url="https://testserver") as client:
        yield client


def test_shell_ist_oeffentlich(spa_client):
    """Sonst waere die Login-Ansicht nicht erreichbar."""
    antwort = spa_client.get("/")

    assert antwort.status_code == 200
    assert "TUBER" in antwort.text


def test_unbekannter_pfad_liefert_die_shell(spa_client):
    """Neuladen auf einer SPA-Route darf kein 404 sein."""
    assert spa_client.get("/planer/gebiete").status_code == 200
    assert "TUBER" in spa_client.get("/planer/gebiete").text


def test_asset_wird_ausgeliefert(spa_client):
    antwort = spa_client.get("/assets/app.js")

    assert antwort.status_code == 200
    assert "tuber" in antwort.text


def test_unbekannter_api_pfad_bleibt_ein_fehler(spa_client, auth_env):
    """Das Mount darf /api/* nicht beschatten.

    Ohne diese Ausnahme bekaeme ein Tippfehler im Pfad die index.html mit
    Status 200 — und der Client suchte den Fehler an der falschen Stelle.
    """
    assert spa_client.post("/api/auth/login", json={"password": auth_env}).status_code == 200

    antwort = spa_client.get("/api/gibtesnicht")

    assert antwort.status_code == 404
    assert "text/html" not in antwort.headers["content-type"]


def test_api_routen_gehen_weiterhin_vor(spa_client):
    """Die bestehenden Endpunkte bleiben erreichbar, das Mount kommt danach."""
    assert spa_client.get("/api/health").json() == {"status": "ok"}
    assert spa_client.get("/api/finds").status_code == 401


def test_kein_ausbruch_aus_dem_build_verzeichnis(spa_client):
    """Ein Pfad, der nach oben zeigt, bekommt die Shell — keine Datei."""
    antwort = spa_client.get("/../conftest.py")

    assert antwort.status_code == 200
    assert "TUBER" in antwort.text
