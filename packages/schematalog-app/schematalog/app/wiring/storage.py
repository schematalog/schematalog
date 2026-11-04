"""Resolving a storage URL to a repository.

One setting selects and configures the store:

    SCHEMATALOG_STORAGE_URL=sqlite:///./schematalog.db
    SCHEMATALOG_STORAGE_URL=postgresql://user:pw@host/db?pool_recycle=900
    SCHEMATALOG_STORAGE_URL=file://./storage_
    SCHEMATALOG_STORAGE_URL=memory://

The scheme picks the backend, and the query string carries that backend's options. One
backend may answer to several schemes (`sqlite` and `postgresql` are both the SQLAlchemy
one), so the mapping is scheme-to-builder rather than one entry per implementation.
"""

from collections.abc import Callable
from functools import cache
from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from schematalog.app.infrastructure.repositories import (
    FilesystemSchemaRepository,
    MemorySchemaRepository,
    SQLAlchemySchemaRepository,
)
from schematalog.common.logging import get_logger
from schematalog.domain.schema import SchemaRepository

log = get_logger(__name__)

type Builder = Callable[[str], SchemaRepository]
"""What a backend registers: a callable taking the storage URL and returning a repository."""

DEFAULT_STORAGE_URL = "sqlite:///./schematalog.db"
"""SQLite in the working directory: no external service, so a bare run just works."""


class UnknownStorageSchemeError(Exception):
    """No backend is registered for the URL's scheme."""

    def __init__(self, scheme: str, known: list[str]):
        super().__init__(
            f"No storage backend for scheme {scheme!r}. Known schemes: {', '.join(known)}."
        )


class InvalidStorageUrlError(Exception):
    """The URL's scheme resolved, but its options did not validate."""


def _split_options[T: BaseModel](url: str, options_model: type[T]) -> tuple[str, T]:
    """Separate a backend's own options from the URL, leaving the rest in place.

    A storage URL carries two kinds of query parameter: ours (`pool_recycle`) and the
    driver's (whatever it understands). Only the keys the backend declares are consumed;
    anything else stays on the returned URL, so a driver option passes through untouched
    and is never mistaken for one of ours.

    Raises:
        InvalidStorageUrlError: If a declared option fails validation.
    """
    base, _, query = url.partition("?")
    params = parse_qsl(query, keep_blank_values=True)
    declared = set(options_model.model_fields)
    ours = {key: value for key, value in params if key in declared}
    theirs = [(key, value) for key, value in params if key not in declared]
    try:
        options = options_model.model_validate(ours)
    except ValidationError as exc:
        raise InvalidStorageUrlError(str(exc)) from exc
    # Rebuilt by hand rather than with `urlunsplit`, which drops the `//` from an
    # authority-less URL and would quietly turn `sqlite:///db` into `sqlite:/db`.
    remainder = f"{base}?{urlencode(theirs)}" if theirs else base
    return remainder, options


class NoOptions(BaseModel):
    """A backend that takes no options of its own."""


class SQLAlchemyOptions(BaseModel):
    """Connection-pool tuning for the SQLAlchemy backend."""

    pool_pre_ping: bool = True
    """Check a pooled connection is alive before handing it out; cheap insurance against
    a database that drops idle connections."""
    pool_recycle: int = 1800
    """Seconds after which a pooled connection is replaced."""


def _build_memory(url: str) -> SchemaRepository:
    _split_options(url, NoOptions)
    return MemorySchemaRepository()


def _build_filesystem(url: str) -> SchemaRepository:
    """`file://relative/path` or `file:///absolute/path`.

    Everything after the scheme is the directory, so a two-slash form is relative to the
    working directory and a three-slash form is absolute - the convention SQLite URLs use.
    """
    remainder, _ = _split_options(url, NoOptions)
    parts = urlsplit(remainder)
    return FilesystemSchemaRepository(directory=Path(f"{parts.netloc}{parts.path}"))


def _build_sqlalchemy(url: str) -> SchemaRepository:
    remainder, options = _split_options(url, SQLAlchemyOptions)
    return SQLAlchemySchemaRepository(_build_engine(_apply_async_driver(remainder), options))


def _build_engine(url: str, options: SQLAlchemyOptions) -> AsyncEngine:
    if ":memory:" in url:
        # A shared in-memory SQLite DB must reuse a single connection, so the tables
        # created on one connection are visible to the next.
        return create_async_engine(url, poolclass=StaticPool)
    return create_async_engine(
        url, pool_pre_ping=options.pool_pre_ping, pool_recycle=options.pool_recycle
    )


def _apply_async_driver(url: str) -> str:
    """Point a bare scheme at the async driver this application uses.

    Nobody configuring a registry should have to know that PostgreSQL means asyncpg here
    and SQLite means aiosqlite; it also lets a platform-provided `DATABASE_URL` be
    consumed verbatim. An explicit driver (`postgresql+psycopg://`) is left alone.
    """
    scheme, _, rest = url.partition("://")
    match scheme:
        case "postgres" | "postgresql":
            return f"postgresql+asyncpg://{rest}"
        case "sqlite":
            return f"sqlite+aiosqlite://{rest}"
        case _:
            return url


BUILT_IN_BUILDERS: dict[str, Builder] = {
    "memory": _build_memory,
    "file": _build_filesystem,
    "sqlite": _build_sqlalchemy,
    "sqlite+aiosqlite": _build_sqlalchemy,
    "postgres": _build_sqlalchemy,
    "postgresql": _build_sqlalchemy,
    "postgresql+asyncpg": _build_sqlalchemy,
}


ENTRY_POINT_GROUP = "schematalog.storage"
"""Where a third-party backend registers itself, one entry per scheme:

    [project.entry-points."schematalog.storage"]
    redis = "schematalog_redis:build_repository"

The name is the URL scheme; the value is a callable taking the URL and returning a
`SchemaRepository`.
"""

PLUGIN_SCHEME = "python"
"""The escape hatch's scheme: `python://<dotted.module.path>`."""

PLUGIN_FACTORY = "build_repository"
"""The function a module reached through `python://` must expose."""


@cache
def _discover_builders() -> dict[str, Builder]:
    """Schemes registered by installed packages, cached for the process.

    A plugin may not shadow a built-in scheme. Allowing it would mean an installed
    package could silently take over `postgresql` and send an instance's data somewhere
    else, which is too much authority for a dependency to acquire by accident; the
    conflict is logged and the built-in kept. A plugin that fails to load is skipped for
    the same reason - one broken package should not stop the application starting on a
    backend it was not being asked for.
    """
    discovered: dict[str, Builder] = {}
    for entry_point in entry_points(group=ENTRY_POINT_GROUP):
        if entry_point.name in BUILT_IN_BUILDERS:
            log.warning(
                "ignoring storage plugin: scheme is built in",
                scheme=entry_point.name,
                plugin=entry_point.value,
            )
            continue
        try:
            discovered[entry_point.name] = entry_point.load()
        except Exception:
            log.exception(
                "storage plugin failed to load",
                scheme=entry_point.name,
                plugin=entry_point.value,
            )
    return discovered


def _import_builder(url: str) -> Builder:
    """Resolve `python://<dotted.module.path>` to that module's `build_repository`.

    The escape hatch for a backend nobody wants to package. The module path is the
    *authority*, not the scheme, which matters more than it looks: a URL scheme may not
    contain an underscore, and Python module names routinely do - putting the path in
    the scheme would have failed on `my_backend` while working on `mybackend`.

    Raises:
        UnknownStorageSchemeError: If the module will not import or exposes no factory.
    """
    module_path = urlsplit(url).netloc
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise UnknownStorageSchemeError(
            f"{PLUGIN_SCHEME}://{module_path}", sorted(BUILT_IN_BUILDERS)
        ) from exc
    builder = getattr(module, PLUGIN_FACTORY, None)
    if builder is None:
        raise UnknownStorageSchemeError(  # noqa: TRY003
            f"{PLUGIN_SCHEME}://{module_path} (no {PLUGIN_FACTORY})", sorted(BUILT_IN_BUILDERS)
        )
    return builder


def resolve_builder(scheme: str) -> Builder:
    """Find the builder for a scheme: built in, or registered by an installed package.

    Raises:
        UnknownStorageSchemeError: If nothing answers to the scheme.
    """
    builder = BUILT_IN_BUILDERS.get(scheme) or _discover_builders().get(scheme)
    if builder is None:
        known = sorted(BUILT_IN_BUILDERS | _discover_builders())
        raise UnknownStorageSchemeError(scheme, known)
    return builder


def build_schema_repository(url: str) -> SchemaRepository:
    """Instantiate the schema repository the URL names.

    Args:
        url: The storage URL; its scheme selects the backend, except for
            `python://<module>`, which imports that module's factory directly.

    Returns:
        The matching `SchemaRepository`.

    Raises:
        UnknownStorageSchemeError: If no backend answers to the scheme.
        InvalidStorageUrlError: If the backend's own options do not validate.
    """
    scheme = urlsplit(url).scheme
    builder = _import_builder(url) if scheme == PLUGIN_SCHEME else resolve_builder(scheme)
    return builder(url)


def get_storage_summary(url: str) -> dict[str, Any]:
    """The URL's scheme and whether it resolves, for logging without leaking credentials."""
    scheme = urlsplit(url).scheme
    try:
        _ = _import_builder(url) if scheme == PLUGIN_SCHEME else resolve_builder(scheme)
    except UnknownStorageSchemeError:
        return {"scheme": scheme, "known": False}
    return {"scheme": scheme, "known": True}


async def check_storage(repository: SchemaRepository) -> None:
    """Prove the store is reachable, using nothing but the repository contract.

    Resolving a URL only proves that some backend answers to its scheme. A wrong host, a
    wrong password or an unwritable directory all build a repository quite happily,
    because every backend connects lazily - so a misconfigured instance starts clean and
    the operator learns the truth from a 500 on the first request. This does the read
    that settles it.

    `list_names` is the probe because it is one of the five required methods, so every
    backend has one, and because at most one name is pulled: an empty store is a healthy
    answer and a large one is not walked. On the SQL backends this is also a first use of
    the store, so it covers the lazy `create_all` as well as the connection itself.

    Whatever the backend raises when it cannot be reached propagates unchanged; the
    caller decides how much of it is safe to show.

    Args:
        repository: The store to probe.
    """
    names = aiter(repository.list_names())
    try:
        await anext(names, None)
    finally:
        # Declared as an `AsyncIterable`, so a backend may hand back a plain iterator
        # with nothing to close; the built-in ones are generators, and abandoning one
        # mid-yield leaves its cursor open until the collector gets to it.
        aclose = getattr(names, "aclose", None)
        if aclose is not None:
            await aclose()
