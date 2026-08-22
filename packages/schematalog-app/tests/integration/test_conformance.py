"""The SQLAlchemy backend against the storage contract on real PostgreSQL.

The unit lane runs the same suite over SQLite; this is where dialect divergence shows up
- `max()` over `uuid`, locale collation, JSONB - against the whole contract rather than a
handful of hand-picked cases.

PostgreSQL behaviour that the contract does not cover belongs in `test_sqla_postgres.py`.
"""

import pytest
import sqlalchemy as sa

from schematalog.app.infrastructure.repositories.sqlalchemy import tables
from schematalog.app.wiring.storage import build_schema_repository
from schematalog.testing import SchemaRepositoryConformance

from .conftest import PG_URL


class TestSQLAlchemyRepositoryOnPostgres(SchemaRepositoryConformance):
    @pytest.fixture
    async def repository(self):
        repo = build_schema_repository(PG_URL)
        yield repo
        async with repo.engine.begin() as conn:
            await conn.execute(sa.delete(tables.schema))
        await repo.engine.dispose()
