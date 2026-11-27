"""Shared SQLite fixtures for tests that need real tables."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers every table)
from app.db.database import Base


@compiles(PGUUID, "sqlite")
def _sqlite_uuid(type_, compiler, **kwargs):
    return "CHAR(32)"


def sqlite_sessionmaker(testcase):
    """Fresh database for one test; cleaned up with the test."""

    temp = TemporaryDirectory()
    testcase.addCleanup(temp.cleanup)
    engine = create_engine(
        f"sqlite:///{temp.name}/test.db",
        connect_args={"check_same_thread": False},
    )
    testcase.addCleanup(engine.dispose)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
