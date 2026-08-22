"""Unit-lane fixtures: in-process storage backends only (no Docker)."""

from pathlib import Path

import pytest

from schematalog.app.wiring.storage import build_schema_repository

# In-process backends: memory, filesystem, and SQLite (the SQLAlchemy repo over an
# in-memory DB). Real Postgres lives in the integration lane.
IN_PROCESS_BACKENDS = ("memory", "filesystem", "sqlalchemy")


def _storage_url(backend: str, tmp_path: Path) -> str:
    """A URL whose store is private to one test.

    Every backend here starts empty and is discarded afterwards - a new dictionary, a
    new temporary directory, a new in-memory database - so no test has to clean up after
    itself and none can see another's writes.
    """
    match backend:
        case "memory":
            return "memory://"
        case "filesystem":
            return f"file://{tmp_path / 'schemas'}"
        case _:
            return "sqlite+aiosqlite:///:memory:"


@pytest.fixture(params=IN_PROCESS_BACKENDS)
async def schema_repo(request, tmp_path):
    repo = build_schema_repository(_storage_url(request.param, tmp_path))
    yield repo
    # The SQLAlchemy backend holds an engine whose aiosqlite worker thread outlives
    # this test's event loop unless it is disposed, and then raises into a later one.
    engine = getattr(repo, "engine", None)
    if engine is not None:
        await engine.dispose()
