"""Add users, sessions, projects and entry ownership

Revision ID: a1b2c3d4e5f6
Revises: ed489105ef37
Create Date: 2026-07-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "ed489105ef37"
branch_labels = None
depends_on = None

project_role = sa.Enum("OWNER", "EDITOR", "VIEWER", name="projectrole")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("issuer", sa.String(512), nullable=True),
        sa.Column("subject", sa.String(512), nullable=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "project_members",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", project_role, nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "entries",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "entries",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_entries_user_id", "entries", ["user_id"])
    op.create_index("ix_entries_project_id", "entries", ["project_id"])
    op.create_foreign_key(
        "fk_entries_user_id",
        "entries",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_entries_project_id",
        "entries",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_entries_project_id", "entries", type_="foreignkey")
    op.drop_constraint("fk_entries_user_id", "entries", type_="foreignkey")
    op.drop_index("ix_entries_project_id", table_name="entries")
    op.drop_index("ix_entries_user_id", table_name="entries")
    op.drop_column("entries", "project_id")
    op.drop_column("entries", "user_id")
    op.drop_table("project_members")
    op.drop_table("projects")
    op.drop_table("sessions")
    op.drop_table("users")
    project_role.drop(op.get_bind(), checkfirst=True)
