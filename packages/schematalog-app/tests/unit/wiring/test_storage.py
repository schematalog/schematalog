"""Resolving a storage URL to a backend."""

from pathlib import Path

import pytest

from schematalog.app.infrastructure.repositories import (
    FilesystemSchemaRepository,
    MemorySchemaRepository,
    SQLAlchemySchemaRepository,
)
from schematalog.app.wiring.storage import (
    InvalidStorageUrlError,
    SQLAlchemyOptions,
    UnknownStorageSchemeError,
    _split_options,
    build_schema_repository,
    check_storage,
    get_storage_summary,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("memory://", MemorySchemaRepository),
        ("sqlite+aiosqlite:///:memory:", SQLAlchemySchemaRepository),
        ("postgresql://user:pw@localhost/db", SQLAlchemySchemaRepository),
        ("postgres://user:pw@localhost/db", SQLAlchemySchemaRepository),
    ],
)
def test_the_scheme_selects_the_backend(url, expected):
    assert isinstance(build_schema_repository(url), expected)


def test_a_file_url_resolves_to_a_directory(tmp_path):
    repo = build_schema_repository(f"file://{tmp_path / 'schemas'}")
    assert isinstance(repo, FilesystemSchemaRepository)
    assert repo.directory == tmp_path / "schemas"


def test_a_two_slash_file_url_is_relative_to_the_working_directory(tmp_path, monkeypatch):
    """`file://x` is relative and `file:///x` absolute, as SQLite URLs read."""
    monkeypatch.chdir(tmp_path)
    repo = build_schema_repository("file://relative_store")
    assert repo.directory == Path("relative_store")
    assert not repo.directory.is_absolute()


def test_an_unknown_scheme_names_the_ones_that_are_known():
    with pytest.raises(UnknownStorageSchemeError, match=r"rabbit.*Known schemes"):
        build_schema_repository("rabbit://somewhere")


def test_an_unparseable_option_is_refused():
    with pytest.raises(InvalidStorageUrlError):
        build_schema_repository("sqlite:///x.db?pool_recycle=soon")


def test_a_backend_takes_only_the_options_it_declares():
    """The driver's query parameters must survive; only ours are consumed."""
    remainder, options = _split_options(
        "postgresql://h/db?pool_recycle=900&sslmode=require", SQLAlchemyOptions
    )
    assert options.pool_recycle == 900
    assert remainder == "postgresql://h/db?sslmode=require"


def test_a_url_without_options_is_left_exactly_as_it_was():
    """`urlunsplit` would drop the `//` here, turning `sqlite:///db` into `sqlite:/db`."""
    remainder, _ = _split_options("sqlite:///data/schematalog.db", SQLAlchemyOptions)
    assert remainder == "sqlite:///data/schematalog.db"


def test_the_summary_carries_the_scheme_and_no_credentials():
    summary = get_storage_summary("postgresql://user:hunter2@host/db")
    assert summary == {"scheme": "postgresql", "known": True}
    assert "hunter2" not in str(summary)


# ---- third-party backends: entry points and the dotted escape hatch ------------------

_PROBE_MODULE = "tests.unit.wiring._plugin_probe.backend"


def test_python_url_imports_the_module_directly():
    """The escape hatch: a backend nobody wants to package, named by import path.

    The module path is the authority rather than the scheme because a URL scheme may not
    contain an underscore - and this very probe module has one, so the scheme form would
    have failed here while passing for a module named without.
    """
    repo = build_schema_repository(f"python://{_PROBE_MODULE}?x=1")
    assert type(repo).__name__ == "ProbeRepository"
    assert "_plugin_probe" in _PROBE_MODULE  # the underscore the scheme form could not carry


def test_a_python_url_that_does_not_import_is_an_unknown_scheme():
    with pytest.raises(UnknownStorageSchemeError):
        build_schema_repository("python://no.such.module.anywhere")


def test_a_python_url_without_the_conventional_factory_is_refused():
    with pytest.raises(UnknownStorageSchemeError, match=r"build_repository"):
        build_schema_repository("python://json")


def test_an_entry_point_registers_a_scheme(monkeypatch):
    from schematalog.app.wiring import storage

    monkeypatch.setattr(storage, "_discover_builders", lambda: {"probe": _build_probe})
    assert type(build_schema_repository("probe://x")).__name__ == "ProbeRepository"


def test_a_plugin_may_not_shadow_a_built_in_scheme(monkeypatch):
    """An installed package taking over `postgresql` could redirect an instance's data."""
    from schematalog.app.wiring import storage

    monkeypatch.setattr(
        storage,
        "entry_points",
        lambda group: [_FakeEntryPoint("postgresql", "evil:build")],
    )
    storage._discover_builders.cache_clear()
    try:
        assert "postgresql" not in storage._discover_builders()
        assert isinstance(
            build_schema_repository("postgresql://h/db"), SQLAlchemySchemaRepository
        )
    finally:
        storage._discover_builders.cache_clear()


def test_a_plugin_that_fails_to_load_does_not_stop_the_others(monkeypatch):
    """One broken package must not prevent starting on a backend nobody asked it for."""
    from schematalog.app.wiring import storage

    monkeypatch.setattr(
        storage,
        "entry_points",
        lambda group: [
            _FakeEntryPoint("broken", "nope:build", explode=True),
            _FakeEntryPoint("probe", f"{_PROBE_MODULE}:build_repository"),
        ],
    )
    storage._discover_builders.cache_clear()
    try:
        assert sorted(storage._discover_builders()) == ["probe"]
    finally:
        storage._discover_builders.cache_clear()


def _build_probe(url: str):
    from tests.unit.wiring._plugin_probe.backend import build_repository

    return build_repository(url)


class _FakeEntryPoint:
    def __init__(self, name: str, value: str, explode: bool = False):
        self.name = name
        self.value = value
        self._explode = explode

    def load(self):
        if self._explode:
            raise ImportError
        module_path, _, attribute = self.value.partition(":")
        from importlib import import_module

        return getattr(import_module(module_path), attribute)


async def test_a_five_method_backend_gets_the_latest_rule_for_free():
    """The point of the whole seam, end to end.

    The probe backend is defined outside `schematalog`, implements only the five required
    methods, and knows nothing about deprecation, succession or publication ordering. It
    should still answer `latest` correctly - skipping a deprecated head, and falling back
    when every version is disqualified - because those are derived, not delegated.
    """
    from schematalog.app.application.schema import (
        GetSchemaCommand,
        MetadataUpdateCommand,
        PublishCommand,
        SchemaService,
    )

    service = SchemaService(build_schema_repository(f"python://{_PROBE_MODULE}"))
    for version in ("1.0", "10.0"):
        await service.publish_schema(
            PublishCommand(name="probe", version=version, json_schema={"type": "object"})
        )

    # Publication order, not string order: 10.0 wins despite sorting below 1.0.
    assert (await service.get_schema(GetSchemaCommand(name="probe"))).version == "10.0"

    await service.update_schema_metadata(
        MetadataUpdateCommand(name="probe", version="10.0", deprecated=True)
    )
    assert (await service.get_schema(GetSchemaCommand(name="probe"))).version == "1.0"

    await service.update_schema_metadata(
        MetadataUpdateCommand(name="probe", version="1.0", deprecated=True)
    )
    assert (await service.get_schema(GetSchemaCommand(name="probe"))).version == "10.0"


async def test_check_storage_accepts_an_empty_store(schema_repo):
    """Empty is a healthy answer; the probe asks whether the store answers, not what it holds."""
    await check_storage(schema_repo)


async def test_check_storage_pulls_at_most_one_name():
    """A registry with thousands of schemas must not be walked to answer a health check."""
    produced = []

    class BigStore:
        async def list_names(self):
            for name in ("first", "second", "third"):
                produced.append(name)
                yield name

    await check_storage(BigStore())
    assert produced == ["first"]


async def test_check_storage_propagates_what_the_backend_raises():
    """The caller decides how much of the failure is safe to show, so nothing is swallowed."""

    class BrokenStore:
        def list_names(self):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise OSError("connection refused")

    with pytest.raises(OSError, match="connection refused"):
        await check_storage(BrokenStore())
