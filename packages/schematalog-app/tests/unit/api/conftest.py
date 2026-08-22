import pytest
from starlette.testclient import TestClient

from schematalog.app.presentation import app as application


@pytest.fixture
async def test_app(schema_repo):
    """The full FastAPI app with its storage swapped for the parametrized test repo."""
    application.state.schemas = schema_repo
    application.debug = True
    return application


@pytest.fixture
def client(test_app):
    return TestClient(test_app, base_url="http://testserver")
