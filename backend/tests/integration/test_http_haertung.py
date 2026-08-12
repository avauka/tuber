"""Produktions-Härtung (AP9c).

Der Befund aus AP9b: /docs, /redoc und /openapi.json lagen ausserhalb von
/api/ und damit ausserhalb des Auth-Schutzes. Hier wird festgehalten, dass
sie standardmässig gar nicht existieren — und dass sie auch aktiviert nicht
ohne Anmeldung herausgeben, wie die API aufgebaut ist.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.http_security import HSTS_VALUE
from app.main import create_app

# Auch die alten Pfade duerfen nicht wieder auftauchen.
ALLE_DOCS_PFADE = ("/docs", "/redoc", "/openapi.json", "/api/docs", "/api/openapi.json")


@pytest.fixture()
def docs_client(monkeypatch, auth_env):
    """Eigene App-Instanz mit aktivierten Docs."""
    monkeypatch.setenv("DOCS_ENABLED", "true")
    with TestClient(create_app(), base_url="https://testserver") as client:
        yield client


# ----------------------------------------------------------------- Docs aus


def test_docs_sind_standardmaessig_abgeschaltet(anon_client):
    for pfad in ALLE_DOCS_PFADE:
        assert anon_client.get(pfad).status_code == 404, pfad


def test_abgeschaltet_heisst_auch_fuer_angemeldete_weg(client):
    """Kein Schlupfloch ueber eine gueltige Sitzung."""
    for pfad in ALLE_DOCS_PFADE:
        assert client.get(pfad).status_code == 404, pfad


@pytest.mark.parametrize("wert", ["", "false", "0", "yes", "TRUE-ish"])
def test_nur_exakt_true_aktiviert(monkeypatch, wert):
    """Alles ausser 'true' laesst die Docs aus — ein Tippfehler in der ENV
    darf das Schema nicht versehentlich oeffnen."""
    monkeypatch.setenv("DOCS_ENABLED", wert)
    with TestClient(create_app(), base_url="https://testserver") as client:
        assert client.get("/api/openapi.json").status_code == 404


# -------------------------------------------------------------- Docs an


def test_aktivierte_docs_brauchen_eine_sitzung(docs_client):
    assert docs_client.get("/api/docs").status_code == 401
    assert docs_client.get("/api/openapi.json").status_code == 401


def test_aktivierte_docs_bleiben_ausserhalb_von_api_unerreichbar(docs_client):
    for pfad in ("/docs", "/redoc", "/openapi.json"):
        assert docs_client.get(pfad).status_code == 404, pfad


def test_angemeldet_liefern_die_docs_das_schema(docs_client, auth_env):
    assert docs_client.post("/api/auth/login", json={"password": auth_env}).status_code == 200

    assert docs_client.get("/api/docs").status_code == 200

    schema = docs_client.get("/api/openapi.json")
    assert schema.status_code == 200
    assert schema.json()["info"]["title"] == "TUBER"
    assert "/api/finds" in schema.json()["paths"]


# ------------------------------------------------------- Sicherheits-Header


def test_security_header_auf_erfolgsantwort(anon_client):
    kopf = anon_client.get("/api/health").headers

    assert kopf["strict-transport-security"] == HSTS_VALUE
    assert kopf["x-content-type-options"] == "nosniff"
    assert kopf["x-frame-options"] == "DENY"


def test_csp_erlaubt_maplibres_worker(anon_client):
    """Im Browser nachgeprüft (AP10b): MapLibre 6 laedt seinen Kachel-Worker
    als eigene Datei von der eigenen Origin.

    Mit `worker-src blob:` allein blockiert der Browser ihn — und zwar
    lautlos, was die Karte weiss laesst, ohne dass im Netzwerk-Tab etwas
    auffaellt. Genau dieser Fall ist hier festgehalten.
    """
    csp = anon_client.get("/api/health").headers["content-security-policy"]

    assert "worker-src 'self' blob:" in csp
    assert "child-src 'self' blob:" in csp


def test_csp_oeffnet_keinen_fremden_host(anon_client):
    """Schriften, Sprite und Kacheln liegen alle bei uns (ADR 0002).

    Sobald hier ein fremder Host auftaucht, haengt die Karte wieder an einem
    Dienst, den wir nicht kontrollieren — und im Wald ohne Netz fehlen die
    Ortsnamen.
    """
    csp = anon_client.get("/api/health").headers["content-security-policy"]

    assert "http://" not in csp
    assert "https://" not in csp
    assert "default-src 'none'" in csp
    # eval() braucht nichts in diesem Frontend.
    assert "unsafe-eval" not in csp


def test_hsts_ohne_preload(anon_client):
    """preload ist praktisch nicht zurueckzuholen — bewusst nicht gesetzt."""
    assert "preload" not in anon_client.get("/api/health").headers["strict-transport-security"]
    assert "max-age=63072000" in HSTS_VALUE
    assert "includeSubDomains" in HSTS_VALUE


def test_security_header_auch_auf_fehlerantworten(anon_client, db_session):
    """Gerade die 401 geht an nicht angemeldete Aufrufer — die Header muessen
    auch da stehen."""
    antwort = anon_client.get("/api/finds")

    assert antwort.status_code == 401
    assert antwort.headers["strict-transport-security"] == HSTS_VALUE
    assert antwort.headers["x-content-type-options"] == "nosniff"
    assert antwort.headers["x-frame-options"] == "DENY"
