from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_entry_schema() -> None:
    """Backfill additive columns for older databases without requiring Alembic."""

    inspector = inspect(engine)
    if "entries" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("entries")}
    statements = []

    if "archived" not in columns:
        statements.append(
            text(
                "ALTER TABLE entries ADD COLUMN archived BOOLEAN NOT NULL DEFAULT false",
            ),
        )

    if "speakers" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN speakers TEXT"),
        )

    if "additional_context" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN additional_context TEXT"),
        )

    if "transcript_words" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN transcript_words TEXT"),
        )

    if "transcript_segments" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN transcript_segments TEXT"),
        )

    if "user_id" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN user_id UUID"),
        )

    if "project_id" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN project_id UUID"),
        )

    if "file_size_bytes" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN file_size_bytes BIGINT"),
        )

    if "duration_seconds" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN duration_seconds DOUBLE PRECISION"),
        )

    if "word_count" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN word_count INTEGER"),
        )

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(statement)


def ensure_auth_schema() -> None:
    """Add auth columns for installations that rely on create_all at startup."""

    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_active" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true",
                ),
            )

    if "personal_access_tokens" not in inspector.get_table_names():
        return
    pat_columns = {
        column["name"] for column in inspector.get_columns("personal_access_tokens")
    }
    pat_statements = []
    if "project_ids" not in pat_columns:
        pat_statements.append(
            "ALTER TABLE personal_access_tokens ADD COLUMN project_ids JSON",
        )
    if "source" not in pat_columns:
        pat_statements.append(
            "ALTER TABLE personal_access_tokens "
            "ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'manual'",
        )
    if "oauth_client_id" not in pat_columns:
        pat_statements.append(
            "ALTER TABLE personal_access_tokens ADD COLUMN oauth_client_id VARCHAR(64)",
        )
    if pat_statements:
        with engine.begin() as connection:
            for statement in pat_statements:
                connection.execute(text(statement))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
