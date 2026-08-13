"""suitability_weight_set — Gewichtssaetze der Eignungskarte

Revision ID: a3f1c72d5b40
Revises: 67f54b4aa884
Create Date: 2026-08-13 08:55:00.000000

Begruendung (nicht im Spec): Spec §6 nennt die Faktorgewichte als
kalibrierbare Startwerte. ADR 0008 §7 praezisiert, wo sie leben —
`params.py` bleibt fuer strukturelle Konstanten, zur Laufzeit aenderbare
Scoring-Parameter gehoeren in die Datenbank.

Versioniert, weil `suitability.meta.json` die verwendete Version mitfuehrt.
Ohne diese Verknuepfung laesst sich spaeter nicht mehr sagen, welche
Kartenfassung zu welchem Fund gehoerte.

Der Startsatz ist Version 1 aus ADR 0008 §3. Ein Schreib-Endpunkt existiert
bewusst noch nicht (AP17a §5): Die Settings-Seite ist ein eigenes Paket, und
ein PATCH ohne Oberflaeche waere unbenutzt und ungetestet.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a3f1c72d5b40"
down_revision = "67f54b4aa884"
branch_labels = None
depends_on = None

# ADR 0008 §3. Summe 100.
STARTGEWICHTE = {
    "kalk": 30,
    "wasser": 20,
    "exposition": 15,
    "wirtsbaum": 15,
    "struktur": 10,
    "klima": 10,
}


def upgrade() -> None:
    tabelle = op.create_table(
        "suitability_weight_set",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_suitability_weight_set"),
        sa.UniqueConstraint("version", name="uq_suitability_weight_set_version"),
    )

    # Hoechstens ein aktiver Satz — in der Datenbank erzwungen und nicht nur
    # in der Anwendung. Zwei aktive Saetze waeren im Nachhinein nicht mehr
    # aufloesbar: Man wuesste nicht, mit welchem die Kacheln entstanden.
    op.create_index(
        "uq_suitability_weight_set_aktiv",
        "suitability_weight_set",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.bulk_insert(
        tabelle,
        [
            {
                "id": uuid.uuid4(),
                "version": 1,
                "weights": STARTGEWICHTE,
                "note": "Startsatz aus ADR 0008 §3.",
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_suitability_weight_set_aktiv", table_name="suitability_weight_set")
    op.drop_table("suitability_weight_set")
