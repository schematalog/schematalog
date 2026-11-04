"""Regression tests for the seed loader (`scripts/seed.py`).

`scripts/` is otherwise untested; these guard the bit that broke silently once - the
seed's re-run idempotency depends on catching the exact error the service raises on a
duplicate publish, which a layer refactor can change out from under it.
"""

import pytest

from schematalog.app.application.schema import (
    GetSchemaCommand,
    ListPredecessorsCommand,
    SchemaService,
)
from schematalog.app.infrastructure.repositories.memory import MemorySchemaRepository
from schematalog.app.wiring.storage import build_schema_repository
from scripts.seed import SAMPLE_SCHEMAS, _apply_metadata, _publish_samples, seed


def _service() -> SchemaService:
    return SchemaService(MemorySchemaRepository())


async def test_publish_samples_is_idempotent():
    # First run publishes everything; a second run skips it all (the DuplicateSchemaError
    # path) rather than crashing - which is what broke when the service stopped raising the
    # domain SchemaConflictError.
    service = _service()
    assert await _publish_samples(service) == (len(SAMPLE_SCHEMAS), 0)
    assert await _publish_samples(service) == (0, len(SAMPLE_SCHEMAS))


async def test_apply_metadata_applies_and_is_idempotent():
    service = _service()
    await _publish_samples(service)
    # Runs cleanly (internal successor targets resolve) and can be re-applied.
    await _apply_metadata(service, "http://localhost:3000")
    await _apply_metadata(service, "http://localhost:3000")


@pytest.fixture
def seeded_service(tmp_path):
    """Build a service over a store `seed` has populated, given where it is browsed."""

    async def build(base_url):
        storage_url = f"file://{tmp_path}"
        await seed(storage_url, base_url)
        return SchemaService(build_schema_repository(storage_url))

    return build


@pytest.mark.parametrize(
    "base_url", ["https://registry.example.org", "https://registry.example.org/"]
)
async def test_seed_stores_an_internal_successor_under_the_base_url(seeded_service, base_url):
    """Stored under localhost, a demo's "Superseded by" link would lead nowhere."""
    service = await seeded_service(base_url)

    superseded = await service.get_schema(GetSchemaCommand(name="example.order", version="1.1"))

    assert str(superseded.successor) == (
        "https://registry.example.org/api/schemas/example.order/versions/2.0"
    )


async def test_seed_lets_the_successor_find_its_predecessor(seeded_service):
    """A predecessor is found by comparing the stored URL with the canonical one."""
    service = await seeded_service("https://registry.example.org")

    predecessors = [
        view.version
        async for view in service.list_schema_predecessors(
            ListPredecessorsCommand(
                successor_url="https://registry.example.org/api/schemas/example.order/versions/2.0"
            )
        )
    ]

    assert predecessors == ["1.1"]


async def test_seed_offers_labels_to_filter_by(seeded_service):
    """Without any, the demo has no label badges to show."""
    service = await seeded_service("https://registry.example.org")

    labels = [label async for label in service.list_labels()]

    assert labels == ["analytics", "billing", "catalog", "commerce", "customer", "identity"]


async def test_seed_labels_versions_an_earlier_run_published(tmp_path):
    """Re-seeding is how a store already holding the samples gains their labels."""
    storage_url = f"file://{tmp_path}"
    await _publish_samples(SchemaService(build_schema_repository(storage_url)))

    await seed(storage_url, "https://registry.example.org")

    service = SchemaService(build_schema_repository(storage_url))
    order = await service.get_schema(GetSchemaCommand(name="example.order", version="1.1"))
    assert order.labels == ["billing", "commerce"]
