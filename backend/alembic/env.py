from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  — Modelle registrieren
from alembic import context
from app.core.db import Base, database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Eine Quelle für die URL, damit Migration und App nie auseinanderlaufen —
# inklusive der Normalisierung von postgres:// (Railway).
# Prozentzeichen verdoppeln: configparser wuerde sie sonst als Interpolation
# lesen und an einem Passwort mit % scheitern.
config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

target_metadata = Base.metadata

# GeoAlchemy2 legt für Geometry-Spalten eigene Indizes an; wir verwalten
# GIST-Indizes explizit in den Migrationen (Spec §4) und filtern Autogenerate.


def include_object(obj, name, type_, reflected, compare_to):
    # PostGIS-eigene Tabellen nie anfassen.
    return not (type_ == "table" and name in {"spatial_ref_sys"})


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
