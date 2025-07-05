"""Manually rename original_filename to filename

Revision ID: ed489105ef37
Revises: 044f16bfbcdb
Create Date: 2025-07-05 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ed489105ef37'
down_revision = '044f16bfbcdb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename original_filename column to filename
    op.alter_column('entries', 'original_filename', new_column_name='filename')


def downgrade() -> None:
    # Rename filename back to original_filename
    op.alter_column('entries', 'filename', new_column_name='original_filename')
