"""The /health endpoint: whether this instance can reach its store."""

from http import HTTPStatus

from starlette.testclient import TestClient

from schematalog.app.infrastructure.repositories.memory import MemorySchemaRepository
from schematalog.app.presentation import app


class UnreachableStore:
    """A store that answers the way a wrong host or password does: not at all.

    An async iterator rather than a generator, so the failure lands on the first pull -
    which is where a lazily-connecting backend puts it.
    """

    def list_names(self):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise OSError("could not connect to postgresql://user:hunter2@host/db")  # noqa: TRY003


def test_health_reports_ok_when_the_store_answers(monkeypatch):
    # The store is set rather than inherited: the app is a module-level singleton, and
    # sibling suites leave their own repository on it.
    monkeypatch.setattr(app.state, "schemas", MemorySchemaRepository())
    response = TestClient(app).get("/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok", "storage": "ok"}


def test_health_reports_unavailable_when_the_store_cannot_be_reached(monkeypatch):
    """An instance whose store is unreachable serves pages fine, so uptime answers nothing."""
    monkeypatch.setattr(app.state, "schemas", UnreachableStore())
    response = TestClient(app).get("/health", follow_redirects=False)
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json() == {"status": "unavailable", "storage": "unreachable"}


def test_health_keeps_the_failure_detail_out_of_a_public_response(monkeypatch):
    """The endpoint is unauthenticated, and a driver's error names hosts and credentials."""
    monkeypatch.setattr(app.state, "schemas", UnreachableStore())
    body = TestClient(app).get("/health", follow_redirects=False).text
    assert "hunter2" not in body
    assert "postgresql" not in body
    assert "host" not in body
