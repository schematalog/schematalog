"""The `schematalog` command: what a `pip install` gives you."""

import pytest

from schematalog.app import __version__
from schematalog.app.cli import main


def test_version_reports_the_application_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_info_reports_the_version_and_how_storage_resolved(capsys):
    assert main(["info"]) == 0
    output = capsys.readouterr().out
    assert __version__ in output
    assert "sqlite" in output
    assert "recognised" in output


def test_info_never_prints_the_storage_url(capsys, monkeypatch):
    """`info` is what someone pastes into an issue, and a storage URL carries a password."""
    from schematalog.app.wiring.config import settings

    monkeypatch.setattr(settings, "STORAGE_URL", "postgresql://user:hunter2@host/db")
    main(["info"])
    output = capsys.readouterr().out
    assert "hunter2" not in output
    assert "postgresql" in output


def test_info_says_so_when_no_backend_answers_to_the_scheme(capsys, monkeypatch):
    from schematalog.app.wiring.config import settings

    monkeypatch.setattr(settings, "STORAGE_URL", "rabbit://somewhere")
    main(["info"])
    assert "NOT recognised" in capsys.readouterr().out


def test_serve_runs_the_application_on_the_requested_address(monkeypatch):
    # The address is the thing under test, so it has to be an explicit one; binding to
    # every interface is what a container asks for and what the default refuses.
    every_interface = "0.0.0.0"  # noqa: S104
    calls = {}

    def fake_run(app, **kwargs):
        calls.update(app=app, **kwargs)

    monkeypatch.setattr("schematalog.app.cli.uvicorn.run", fake_run)
    assert main(["serve", "--host", every_interface, "--port", "9001"]) == 0
    assert calls == {
        "app": "schematalog.app.presentation:app",
        "host": every_interface,
        "port": 9001,
        "reload": False,
    }


def test_serve_defaults_to_the_loopback_interface(monkeypatch):
    """A default of 0.0.0.0 would expose an unauthenticated registry to the network."""
    calls = {}
    monkeypatch.setattr("schematalog.app.cli.uvicorn.run", lambda app, **kw: calls.update(kw))
    main(["serve"])
    assert calls["host"] == "127.0.0.1"


def _unreachable(message):
    """A `check_storage` that fails the way an unreachable store does."""

    async def fail(_repository):
        raise OSError(message)

    return fail


def test_check_reports_the_store_as_reachable(capsys, monkeypatch):
    from schematalog.app.wiring.config import settings

    monkeypatch.setattr(settings, "STORAGE_URL", "memory://")
    assert main(["check"]) == 0
    output = capsys.readouterr().out
    assert "memory" in output
    assert "reachable" in output


def test_check_exits_non_zero_when_the_store_cannot_be_reached(capsys, monkeypatch):
    """The whole point: a lazily-connecting backend builds fine and fails on first use."""
    from schematalog.app.wiring.config import settings

    monkeypatch.setattr(settings, "STORAGE_URL", "memory://")
    monkeypatch.setattr("schematalog.app.cli.check_storage", _unreachable("connection refused"))
    assert main(["check"]) == 1
    output = capsys.readouterr().out
    assert "unreachable" in output
    assert "connection refused" in output


def test_check_never_prints_the_storage_url(capsys, monkeypatch):
    """A driver names the DSN in its connection errors, and the DSN carries a password."""
    from schematalog.app.wiring.config import settings

    monkeypatch.setattr(settings, "STORAGE_URL", "memory://")
    monkeypatch.setattr(
        "schematalog.app.cli.check_storage",
        _unreachable("could not connect to postgresql://user:hunter2@host/db"),
    )
    assert main(["check"]) == 1
    assert "hunter2" not in capsys.readouterr().out


def test_check_names_an_unrecognised_scheme_rather_than_blaming_the_store(capsys, monkeypatch):
    from schematalog.app.wiring.config import settings

    monkeypatch.setattr(settings, "STORAGE_URL", "rabbit://somewhere")
    assert main(["check"]) == 1
    output = capsys.readouterr().out
    assert "NOT recognised" in output
    assert "unreachable" not in output


def test_check_separates_invalid_options_from_an_unreachable_store(capsys, monkeypatch):
    """Two different fixes: correct the setting, or go and start the database."""
    from schematalog.app.wiring.config import settings

    monkeypatch.setattr(settings, "STORAGE_URL", "sqlite:///./x.db?pool_recycle=soon")
    assert main(["check"]) == 1
    output = capsys.readouterr().out
    assert "misconfigured" in output
    assert "unreachable" not in output
