"""Test-Setup. Unit-Tests laufen ohne DB; @pytest.mark.db-Tests brauchen
die lokale PostGIS (docker compose up -d db, Port 5433).

Die Test-DB (tuber_test) wird beim ersten Lauf angelegt und per
Alembic-Migration aufgebaut — damit testet jeder Lauf implizit auch,
dass die Migrationen einen frischen Aufbau überleben.
"""

import os
from pathlib import Path

import pytest

TEST_DB_URL = os.environ.get(
    "TUBER_TEST_DATABASE_URL",
    "postgresql+psycopg://tuber:tuber@localhost:5433/tuber_test",
)


@pytest.fixture(scope="session")
def db_engine():
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(TEST_DB_URL)
    admin_url = url.set(database="tuber")  # Maintenance-DB aus docker-compose

    try:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": url.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
        admin.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"PostGIS-Test-DB nicht erreichbar ({admin_url.render_as_string(hide_password=True)}): {exc}\n"
            "-> docker compose up -d db",
            pytrace=False,
        )

    # Schema über die echten Migrationen aufbauen.
    from alembic.config import Config

    from alembic import command

    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    os.environ["DATABASE_URL"] = TEST_DB_URL
    command.upgrade(cfg, "head")

    engine = create_engine(TEST_DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    with Session(db_engine) as session:
        yield session
        session.rollback()
        # Tabellen leeren, damit Tests unabhängig bleiben.
        session.execute(
            text(
                "TRUNCATE coverage, track, find, signal, media, "
                "conditions_snapshot, session, area CASCADE"
            )
        )
        session.commit()


@pytest.fixture(scope="session")
def gpx_fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "gpx"


# --- Auth (ADR 0005) ------------------------------------------------------

TEST_PASSWORD = "feldgang-2026"


@pytest.fixture(scope="session")
def auth_env():
    """Passwort-Hash einmal pro Testlauf erzeugen — Argon2 ist absichtlich
    langsam, das gehört nicht in jeden einzelnen Test."""
    from argon2 import PasswordHasher

    os.environ["AUTH_PASSWORD_HASH"] = PasswordHasher().hash(TEST_PASSWORD)
    os.environ["SESSION_SECRET"] = "test-secret-nur-fuer-die-suite"
    return TEST_PASSWORD


@pytest.fixture(autouse=True)
def _reset_login_attempts():
    """Der Fehlversuchszähler lebt im Prozess und würde sonst zwischen Tests
    durchschlagen."""
    from app.core.auth import clear_login_attempts

    clear_login_attempts()
    yield
    clear_login_attempts()


@pytest.fixture()
def anon_client(auth_env):
    """Nicht angemeldeter Client.

    base_url ist HTTPS, weil das Session-Cookie mit Secure gesetzt wird —
    über http würde httpx es nicht zurückschicken, und jeder geschützte
    Aufruf liefe ins 401.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="https://testserver") as client:
        yield client


@pytest.fixture()
def client(db_session, anon_client, auth_env):
    """Angemeldeter Client für die geschützten Endpunkte."""
    antwort = anon_client.post("/api/auth/login", json={"password": auth_env})
    assert antwort.status_code == 200, antwort.text
    return anon_client
