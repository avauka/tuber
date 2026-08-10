import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.db import Base
import app.models  # noqa: F401  — Modelle registrieren

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# URL aus ENV; Fallback = lokale Dev-DB aus docker-compose.
db_url = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://tuber:tuber@localhost:5432/tuber"
)
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata

# GeoAlchemy2 legt für Geometry-Spalten eigene Indizes an; wir verwalten
# GIST-Indizes explizit in den Migrationen (Spec §4) und filtern Autogenerate.


def include_object(obj, name, type_, reflected, compare_to):
    # PostGIS-eigene Tabellen nie anfassen.
    if type_ == "table" and name in {"spatial_ref_sys"}:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
