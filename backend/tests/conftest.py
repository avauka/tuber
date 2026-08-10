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
    from alembic import command
    from alembic.config import Config

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
        session.execute(text(
            "TRUNCATE coverage, track, find, signal, media, "
            "conditions_snapshot, session, area CASCADE"
        ))
        session.commit()


@pytest.fixture(scope="session")
def gpx_fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "gpx"
