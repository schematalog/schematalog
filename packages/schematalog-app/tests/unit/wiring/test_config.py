"""Settings: defaults and environment overrides."""

from schematalog.app.wiring.config import Environment, Platform, Settings
from schematalog.app.wiring.storage import DEFAULT_STORAGE_URL


def test_storage_defaults_to_sqlite_in_the_working_directory():
    """A bare run needs no configuration: no external service, no variable to set."""
    settings = Settings(_env_file=None)
    assert settings.STORAGE_URL == DEFAULT_STORAGE_URL
    assert settings.STORAGE_URL.startswith("sqlite:")


def test_the_storage_url_comes_from_one_environment_variable(monkeypatch):
    monkeypatch.setenv("SCHEMATALOG_STORAGE_URL", "postgresql://localhost/schematalog")
    settings = Settings(_env_file=None)
    assert settings.STORAGE_URL == "postgresql://localhost/schematalog"


def test_environment_and_platform_default_to_development_local():
    settings = Settings(_env_file=None)
    assert settings.ENVIRONMENT is Environment.DEVELOPMENT
    assert settings.PLATFORM is Platform.LOCAL


def test_environment_and_platform_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("SCHEMATALOG_ENVIRONMENT", "production")
    monkeypatch.setenv("SCHEMATALOG_PLATFORM", "fly")
    settings = Settings(_env_file=None)
    assert settings.ENVIRONMENT is Environment.PRODUCTION
    assert settings.PLATFORM is Platform.FLY
