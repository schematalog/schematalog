"""Integration-lane fixtures: real Postgres (via `compose.yaml`).

The URL defaults to the local compose service and can be overridden by env var
(e.g. for CI).
"""

import asyncio
import os

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from schematalog.app.infrastructure.repositories.sqlalchemy import tables
from schematalog.app.wiring.storage import build_schema_repository

PG_URL = os.environ.get(
    "SCHEMATALOG_TEST_DATABASE_URL",
    "postgresql+asyncpg://schematalog:schematalog@localhost:5432/schematalog",
)


@pytest.fixture(scope="session", autouse=True)
def _conformance_schema():
    """Recreate the conformance DB's tables to match the current metadata.

    The repos auto-create via `create_all`, which never ALTERs an existing table, so
    a persistent compose volume goes stale when columns change. Dropping + recreating
    once per session keeps the conformance lane matching the code.

    The drop is a `DROP SCHEMA public CASCADE` rather than metadata-driven, because a
    table the code no longer defines is invisible to `drop_all` yet can still block it:
    a removed table holding a foreign key into a surviving one makes the survivor
    undroppable. That is not hypothetical - it is what the teardown does repeatedly.
    """

    async def _recreate() -> None:
        engine = create_async_engine(PG_URL)
        try:
            async with engine.begin() as conn:
                await conn.execute(sa.text("DROP SCHEMA public CASCADE"))
                await conn.execute(sa.text("CREATE SCHEMA public"))
                await conn.run_sync(tables.db_metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(_recreate())


@pytest.fixture
async def pg_schema_repo():
    """A `SQLAlchemySchemaRepository` over real Postgres (auto-creates its table).

    Unlike the in-process backends, this one shares a database between tests, so the
    fixture empties it afterwards. It does that directly rather than through a method on
    the repository: clearing a store is a test concern, and the storage contract should
    not carry an operation the running application never performs.
    """
    repo = build_schema_repository(PG_URL)
    yield repo
    async with repo.engine.begin() as conn:
        await conn.execute(sa.delete(tables.schema))
    await repo.engine.dispose()
