"""season_normal und season_state — Saisonzustand je Gebiet

Revision ID: b7e2d4a91c33
Revises: a3f1c72d5b40
Create Date: 2026-08-17 13:40:00.000000

Begruendung (nicht im Spec): ADR 0007 haelt im Abschnitt "Rueckweg" fest,
dass ein Archiv-Backfill als eigenes Paket kommt — **additiv, in eigener
Tabelle**, damit Score-Historie und Auswertung getrennt bleiben. Genau das
sind diese beiden Tabellen.

`conditions_snapshot` bleibt unangetastet. Die Bedingungs-Engine arbeitet
weiter auf Forecast-Werten ueber 14 Tage; der Saisonzustand ist eine
zweite, getrennte Groesse ueber sechs Monate aus dem ERA5-Archiv.

Zwei Tabellen statt einer, weil die Normale einen anderen Lebenszyklus hat:
Sie wird einmal je Gebiet ueber 30 Jahre berechnet und bleibt dann liegen,
waehrend der Zustand monatlich nachgezogen wird.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b7e2d4a91c33"
down_revision = "a3f1c72d5b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "season_normal",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("area_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference_from_year", sa.Integer(), nullable=False),
        sa.Column("reference_to_year", sa.Integer(), nullable=False),
        sa.Column("precipitation_by_day", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("soil_moisture_by_day", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"], name="fk_season_normal_area"),
        sa.PrimaryKeyConstraint("id", name="pk_season_normal"),
        # Eine Normale je Gebiet: Sie haengt nur am Punkt, nicht am Zeitpunkt.
        sa.UniqueConstraint("area_id", name="uq_season_normal_area"),
    )

    op.create_table(
        "season_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("area_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("precipitation_30d_mm", sa.Numeric(), nullable=True),
        sa.Column("precipitation_90d_mm", sa.Numeric(), nullable=True),
        sa.Column("precipitation_180d_mm", sa.Numeric(), nullable=True),
        sa.Column("precipitation_30d_percent", sa.Numeric(), nullable=True),
        sa.Column("precipitation_90d_percent", sa.Numeric(), nullable=True),
        sa.Column("precipitation_180d_percent", sa.Numeric(), nullable=True),
        sa.Column("soil_moisture_90d", sa.Numeric(), nullable=True),
        sa.Column("soil_moisture_90d_percent", sa.Numeric(), nullable=True),
        sa.Column("dry_spell_days", sa.Integer(), nullable=True),
        sa.Column("complete", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("missing_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"], name="fk_season_state_area"),
        sa.PrimaryKeyConstraint("id", name="pk_season_state"),
        # Idempotenz: Ein zweiter Lauf fuer denselben Stichtag aktualisiert
        # die Zeile, statt eine zweite anzulegen.
        sa.UniqueConstraint("area_id", "window_end", name="uq_season_state_area_ende"),
    )
    op.create_index("ix_season_state_area_id", "season_state", ["area_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_season_state_area_id", table_name="season_state")
    op.drop_table("season_state")
    op.drop_table("season_normal")
