"""Every in-process backend against the published storage contract.

This is where backends *sign* the contract; `schematalog.testing.SchemaRepositoryConformance`
is the contract itself. Each subclass supplies only a `repository` fixture - the
specification is inherited, which is exactly what a third-party author does.

Behaviour that is true of one backend and not the others does **not** belong here: it
goes in that backend's own file (`test_filesystem.py`, `test_sqlalchemy.py`). The rule is
what the test is *for*, not what it runs on - a case that any backend must satisfy
belongs in the suite so all of them are held to it.

Real PostgreSQL signs the same contract in `tests/integration/test_conformance.py`.
"""

import pytest

from schematalog.app.infrastructure.repositories import (
    FilesystemSchemaRepository,
    MemorySchemaRepository,
)
from schematalog.app.wiring.storage import build_schema_repository
from schematalog.testing import SchemaRepositoryConformance

from ...wiring._plugin_probe.backend import ProbeRepository


class TestMemoryRepository(SchemaRepositoryConformance):
    @pytest.fixture
    def repository(self):
        return MemorySchemaRepository()


class TestFilesystemRepository(SchemaRepositoryConformance):
    @pytest.fixture
    def repository(self, tmp_path):
        return FilesystemSchemaRepository(directory=tmp_path / "schemas")


class TestSQLAlchemyRepositoryOverSQLite(SchemaRepositoryConformance):
    """The SQL backend overrides all three derived methods, so the suite checks its own
    answers against the same expectations as a backend that inherits them - which is the
    entire reason an override is permitted."""

    @pytest.fixture
    async def repository(self):
        repo = build_schema_repository("sqlite+aiosqlite:///:memory:")
        yield repo
        await repo.engine.dispose()


class TestOutOfTreeProbeRepository(SchemaRepositoryConformance):
    """A backend defined outside `schematalog`, implementing only the five required methods.

    It belongs beside the real ones rather than off with the plugin wiring: it is held to
    the same contract, and its passing is what shows the suite is usable from outside and
    that the derived methods are genuinely inherited rather than merely documented.
    """

    @pytest.fixture
    def repository(self):
        return ProbeRepository()
