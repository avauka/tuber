"""backup_download — Nachweis ueber heruntergeladene Dumps

Revision ID: 67f54b4aa884
Revises: 603a116c19c0
Create Date: 2026-08-10 21:40:12.884301

Begruendung (nicht im Spec): Spec §4 kennt keine Backup-Tabelle. ADR 0004
haelt aber fest, dass eine Kopie auf demselben Volume kein Backup ist —
Projekt- oder Accountverlust nimmt sie mit. Erst der Download off-platform
macht aus dem Dump eine Sicherung.

Ohne festgehaltenen Download laesst sich genau das nicht unterscheiden. Die
Tabelle traegt deshalb je Download eine Zeile; daraus leitet
GET /api/backups das Feld `stale` ab (nie heruntergeladen und aelter als
sieben Tage).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '67f54b4aa884'
down_revision = '603a116c19c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'backup_download',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column(
            'downloaded_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name='pk_backup_download'),
    )
    op.create_index(
        'ix_backup_download_filename', 'backup_download', ['filename'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_backup_download_filename', table_name='backup_download')
    op.drop_table('backup_download')
