"""SQLAlchemy-Basis. Geometrien: EPSG:4326 als geography (Invariante 11)."""

import os
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Deterministische Constraint-Namen, damit Alembic-Migrationen stabil bleiben.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Gleicher Fallback wie in alembic/env.py: lokale Dev-DB aus docker-compose.
DEFAULT_DATABASE_URL = "postgresql+psycopg://tuber:tuber@localhost:5433/tuber"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def normalize_database_url(url: str) -> str:
    """Treiber-Präfix ergänzen, falls keins gesetzt ist.

    Railway (und viele andere Anbieter) liefern `postgres://…` — ein Schema,
    das SQLAlchemy 2 nicht mehr kennt. Ohne Normalisierung scheitert der
    Start mit einem Fehler, der nichts mit der Ursache zu tun hat. Eine
    bereits gesetzte Treiberangabe (`postgresql+…`) bleibt unangetastet.
    """
    for legacy in ("postgres://", "postgresql://"):
        if url.startswith(legacy):
            return "postgresql+psycopg://" + url[len(legacy) :]
    return url


def database_url() -> str:
    return normalize_database_url(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Engine erst beim ersten Zugriff bauen, nicht beim Import.

    Die Tests setzen DATABASE_URL in einer Fixture — also nach dem Import
    dieses Moduls. Eine Engine auf Modulebene würde auf die Dev-DB zeigen
    und die Testdaten dort hineinschreiben.
    """
    return create_engine(database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    # expire_on_commit=False: nach dem Commit sollen die Felder für die
    # Antwort lesbar bleiben, ohne dass ein zweiter SELECT nötig wird.
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI-Dependency: eine Session pro Request."""
    with get_sessionmaker()() as session:
        yield session


# Als Annotated-Alias, nicht als Default-Argument: Depends() im Default
# ist ein Funktionsaufruf zur Definitionszeit (ruff B008).
DbSession = Annotated[Session, Depends(get_db)]
