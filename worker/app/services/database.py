from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Synchronous engine for migrations
engine = create_engine(settings.database_url)
Base = declarative_base()

# Async engine for worker operations
async_engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


def ensure_entry_schema() -> None:
    """Backfill additive columns for older databases without requiring Alembic."""

    inspector = inspect(engine)
    if "entries" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("entries")}
    statements = []

    if "archived" not in columns:
        statements.append(
            text("ALTER TABLE entries ADD COLUMN archived BOOLEAN NOT NULL DEFAULT false")
        )

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(statement)

async def get_async_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
