"""Single-User-Auth — ADR 0005.

Der Ablauf steckt im signierten Token selbst, es gibt kein User-Modell und
keine DB-Berührung. Geprüft wird deshalb am HTTP-Vertrag: Wer kommt rein,
wer nicht, und was passiert bei zu vielen Fehlversuchen.
"""

import os
import time

import pytest
from itsdangerous import TimestampSigner, URLSafeTimedSerializer

from app.core.auth import (
    LOGIN_MAX_FAILURES,
    SESSION_COOKIE,
    SESSION_MAX_AGE_S,
    SESSION_SALT,
    TOKEN_SUBJECT,
)

pytestmark = pytest.mark.db


def _abgelaufenes_token(secret: str) -> str:
    """Token mit künstlich altem Zeitstempel.

    itsdangerous stempelt beim Signieren die aktuelle Zeit; für den
    Ablauftest wird genau dieser Zeitpunkt zurückdatiert.
    """
    zu_alt = SESSION_MAX_AGE_S + 3600

    class _AlterSigner(TimestampSigner):
        def get_timestamp(self) -> int:
            return int(time.time()) - zu_alt

    serializer = URLSafeTimedSerializer(secret, salt=SESSION_SALT, signer=_AlterSigner)
    return serializer.dumps(TOKEN_SUBJECT)


# --------------------------------------------------------------- Login


def test_login_setzt_session_cookie(anon_client, auth_env):
    r = anon_client.post("/api/auth/login", json={"password": auth_env})
    assert r.status_code == 200

    gesetzt = r.headers["set-cookie"]
    klein = gesetzt.lower()
    assert SESSION_COOKIE in gesetzt
    assert "httponly" in klein
    assert "secure" in klein
    assert "samesite=lax" in klein
    assert f"max-age={SESSION_MAX_AGE_S}" in klein
    assert "path=/" in klein


def test_falsches_passwort_ist_401(anon_client, auth_env):
    r = anon_client.post("/api/auth/login", json={"password": "falsch"})
    assert r.status_code == 401
    assert SESSION_COOKIE not in anon_client.cookies


def test_rate_limit_nach_fuenf_fehlversuchen(anon_client, auth_env):
    for _ in range(LOGIN_MAX_FAILURES):
        assert anon_client.post("/api/auth/login", json={"password": "falsch"}).status_code == 401

    gesperrt = anon_client.post("/api/auth/login", json={"password": "falsch"})
    assert gesperrt.status_code == 429

    # Auch das richtige Passwort kommt jetzt nicht mehr durch — sonst waere
    # die Sperre wirkungslos.
    assert anon_client.post("/api/auth/login", json={"password": auth_env}).status_code == 429


def test_erfolgreicher_login_setzt_den_zaehler_zurueck(anon_client, auth_env):
    for _ in range(LOGIN_MAX_FAILURES - 1):
        anon_client.post("/api/auth/login", json={"password": "falsch"})

    assert anon_client.post("/api/auth/login", json={"password": auth_env}).status_code == 200

    # Nach dem Reset sind wieder volle Fehlversuche frei.
    for _ in range(LOGIN_MAX_FAILURES):
        assert anon_client.post("/api/auth/login", json={"password": "falsch"}).status_code == 401


# ------------------------------------------------------- Schutz der Routen


def test_geschuetzte_route_ohne_cookie_ist_401(anon_client, db_session):
    assert anon_client.get("/api/finds").status_code == 401


def test_geschuetzte_route_mit_cookie_geht(client):
    assert client.get("/api/finds").status_code == 200


def test_health_ist_oeffentlich(anon_client):
    r = anon_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_abgelaufenes_token_ist_401(anon_client, db_session, auth_env):
    anon_client.cookies.set(SESSION_COOKIE, _abgelaufenes_token(os.environ["SESSION_SECRET"]))
    assert anon_client.get("/api/finds").status_code == 401


def test_gefaelschtes_token_ist_401(anon_client, db_session, auth_env):
    anon_client.cookies.set(SESSION_COOKIE, "offensichtlich.kein.gueltiges.token")
    assert anon_client.get("/api/finds").status_code == 401


def test_logout_beendet_die_sitzung(client, db_session):
    assert client.get("/api/finds").status_code == 200

    assert client.post("/api/auth/logout").status_code == 200

    assert client.get("/api/finds").status_code == 401


def test_alle_api_routen_sind_geschuetzt(anon_client, db_session):
    """Fail-closed: Die Dependency haengt global, nicht pro Router."""
    geschuetzt = [
        ("get", "/api/finds"),
        ("get", "/api/areas"),
        ("get", "/api/coverage"),
        ("post", "/api/signals"),
        ("post", "/api/sessions"),
        ("post", "/api/tracks/import"),
    ]
    for methode, pfad in geschuetzt:
        antwort = getattr(anon_client, methode)(pfad)
        assert antwort.status_code == 401, f"{methode.upper()} {pfad} war nicht geschuetzt"
