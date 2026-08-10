"""session.area_id — Verknuepfung Session -> Area

Revision ID: 8ae31a5ef377
Revises: f5f060841f99
Create Date: 2026-08-10 20:30:54.914034

Begruendung (Spec-Luecke): Spec §5 "Wichtig" verlangt, dass der
Bedingungsscore bei jeder Session mitgespeichert wird. Die Werte dafuer
stehen in conditions_snapshot, und die haengen an einem Gebiet (area_id).
Die session-Tabelle in Spec §4 listet aber nur ein freies Textfeld
area_label — damit laesst sich kein Snapshot finden.

Deshalb bekommt session eine echte, nullable Referenz auf area. Nullable,
weil ein Feldgang ohne vorher angelegtes Gebiet moeglich bleiben muss; dann
entfaellt das Einfrieren der Wetterwerte, statt Zahlen zu raten.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '8ae31a5ef377'
down_revision = 'f5f060841f99'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'session',
        sa.Column('area_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_session_area_id_area', 'session', 'area', ['area_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_session_area_id_area', 'session', type_='foreignkey')
    op.drop_column('session', 'area_id')
