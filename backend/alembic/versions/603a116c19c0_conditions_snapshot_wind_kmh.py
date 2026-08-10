"""conditions_snapshot.wind_kmh — Wind als eigene Spalte

Revision ID: 603a116c19c0
Revises: 8ae31a5ef377
Create Date: 2026-08-10 21:12:03.551902

Begruendung (Spec-Luecke): Spec §5 listet wind_speed_10m als eine der sechs
stuendlichen Ingest-Variablen, und das Feld-Scoring (conditions.field_score)
braucht den Wind zwingend. Die Tabelle conditions_snapshot in Spec §4 hat
dafuer aber keine Spalte.

AP6 hatte den Wert uebergangsweise aus dem raw-JSONB gelesen. Das war eine
Verabredung ueber einen Schluesselnamen, die kein Schema erzwingt: ein
Tippfehler im Ingest waere erst dadurch aufgefallen, dass Sessions dauerhaft
ohne Score enden. Ab hier steht der Wind in einer echten Spalte; raw bleibt
als unveraendertes Roharchiv der API-Antwort erhalten.
"""

import sqlalchemy as sa
from alembic import op

revision = '603a116c19c0'
down_revision = '8ae31a5ef377'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'conditions_snapshot',
        sa.Column('wind_kmh', sa.Numeric(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conditions_snapshot', 'wind_kmh')
