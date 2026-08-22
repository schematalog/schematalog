from http import HTTPStatus

from fastapi.testclient import TestClient
import pytest

from schematalog.app.infrastructure.repositories.memory import MemorySchemaRepository
from schematalog.app.presentation import app


@pytest.fixture
async def client():
    app.state.schemas = MemorySchemaRepository()
    return TestClient(app, base_url="http://testserver")


@pytest.fixture
def published(client, example_schema):
    """A schema published through the API, to be read back over the browser routes."""
    response = client.post("/api/schemas", json={**example_schema})
    assert response.status_code == HTTPStatus.CREATED
    return example_schema
