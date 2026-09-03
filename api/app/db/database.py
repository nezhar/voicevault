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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
