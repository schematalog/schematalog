import pytest
from starlette.testclient import TestClient

from schematalog.app.presentation import app as application


@pytest.fixture
async def test_app(schema_repo, monkeypatch):
    """The full FastAPI app with its storage swapped for the parametrized test repo.

    Swapped through `monkeypatch` rather than assigned: the app is built once at import
    and shared by every suite, so an assignment here outlives the test and hands the
    next one a repository whose engine has since been disposed.
    """
    monkeypatch.setattr(application.state, "schemas", schema_repo)
    monkeypatch.setattr(application, "debug", True)
    return application


@pytest.fixture
def client(test_app):
    return TestClient(test_app, base_url="http://testserver")
