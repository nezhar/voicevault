"""Add ERROR enum value manually

Revision ID: 1d2161cf4a62
Revises: 2b80756aa864
Create Date: 2025-07-05 20:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1d2161cf4a62'
down_revision = '2b80756aa864'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ERROR value to entrystatus enum
    op.execute("ALTER TYPE entrystatus ADD VALUE 'error'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type
    pass
