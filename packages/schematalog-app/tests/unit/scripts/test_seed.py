"""Regression tests for the dev seed loader (`scripts/seed.py`).

`scripts/` is otherwise untested; these guard the bit that broke silently once - the
seed's re-run idempotency depends on catching the exact error the service raises on a
duplicate publish, which a layer refactor can change out from under it.
"""

import pytest

from schematalog.app.application.schema import GetSchemaCommand, SchemaService
from schematalog.app.infrastructure.repositories.memory import MemorySchemaRepository
from scripts.seed import SAMPLE_SCHEMAS, _apply_metadata, _publish_samples


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
    await _apply_metadata(service)
    await _apply_metadata(service)


@pytest.mark.parametrize(
    "base_url", ["https://registry.example.org", "https://registry.example.org/"]
)
async def test_apply_metadata_stores_an_internal_successor_under_the_base_url(base_url):
    """Stored under localhost, a demo's "Superseded by" link would lead nowhere."""
    service = _service()
    await _publish_samples(service)

    await _apply_metadata(service, base_url)

    superseded = await service.get_schema(GetSchemaCommand(name="example.order", version="1.1"))
    assert str(superseded.successor) == (
        "https://registry.example.org/api/schemas/example.order/versions/2.0"
    )


async def test_apply_metadata_stores_an_internal_successor_under_localhost_by_default():
    service = _service()
    await _publish_samples(service)

    await _apply_metadata(service)

    superseded = await service.get_schema(GetSchemaCommand(name="example.order", version="1.1"))
    assert str(superseded.successor) == (
        "http://localhost:3000/api/schemas/example.order/versions/2.0"
    )
