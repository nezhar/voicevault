"""add entry consumption metrics

Revision ID: c7e1a9b4d2f3
Revises: a1b2c3d4e5f6
Create Date: 2026-08-20

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c7e1a9b4d2f3"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entries",
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
    )
    op.add_column("entries", sa.Column("duration_seconds", sa.Float(), nullable=True))
    op.add_column("entries", sa.Column("word_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("entries", "word_count")
    op.drop_column("entries", "duration_seconds")
    op.drop_column("entries", "file_size_bytes")
