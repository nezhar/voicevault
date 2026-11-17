"""Add single-use upload links.

Revision ID: d9f2b7c4e8a1
Revises: b4d8e2f6a1c3
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d9f2b7c4e8a1"
down_revision = "b4d8e2f6a1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pat_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("expected_sha256", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_upload_sessions_user_created_at",
        "upload_sessions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_upload_sessions_user_created_at", table_name="upload_sessions")
    op.drop_table("upload_sessions")
