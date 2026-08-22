"""The /version build-info endpoint."""

from starlette.testclient import TestClient

from schematalog.app import presentation
from schematalog.app.presentation import app
from schematalog.app.wiring.config import Environment, Platform


def test_version_reports_build_and_deploy_axes(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "abc1234")
    monkeypatch.setenv("GIT_COMMIT_DATE", "2026-06-07")
    payload = TestClient(app).get("/version").json()
    assert payload["version"] == app.version
    assert payload["commit"] == "abc1234"
    assert payload["commit_date"] == "2026-06-07"
    assert set(payload) == {"version", "commit", "commit_date", "environment", "platform"}


def test_version_surfaces_environment_and_platform(monkeypatch):
    monkeypatch.setattr(presentation.settings, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(presentation.settings, "PLATFORM", Platform.FLY)
    payload = TestClient(app).get("/version").json()
    assert payload["environment"] == "production"
    assert payload["platform"] == "fly"
