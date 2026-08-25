# Writing a storage backend

Schematalog keeps its schemas in whatever store you point it at, and the set of stores is
open: a backend is an installable package that nothing in this repository knows about.
This page is how to write one. For *whether* you should - the built-in backends cover
more ground than people expect - see [Choosing a storage backend](storage.md).

## What you depend on

Only the contract:

```shell
pip install "schematalog-core[testing]"
```

`schematalog-core` carries the domain model and the repository protocol; the `testing`
extra adds the conformance suite and pytest. It deliberately does **not** pull in the
registry application, so implementing five methods does not oblige you to install a web
framework, a server and a template engine. If your backend ever needs something from
`schematalog.app`, that is a hole in the contract - please report it rather than reaching
through.

## The five methods

Subclass `SchemaRepository` and implement these. Subclassing is not a formality: three
further methods are *derived* from yours in the base class, and inheriting them is how
you get them right.

```python
from collections.abc import AsyncIterable

from schematalog.domain.exceptions import SchemaConflictError, UnknownSchemaError
from schematalog.domain.schema import (
    UNSET,
    Schema,
    SchemaIdentity,
    SchemaName,
    SchemaRepository,
    SuccessorReference,
    Unset,
)


class MySchemaRepository(SchemaRepository):
    async def add(self, schema: Schema) -> Schema:
        """Store the version and return it.

        Raises SchemaConflictError if (name, version) is already present.
        """

    async def get(self, identity: SchemaIdentity) -> Schema:
        """Retrieve one version.

        Raises UnknownSchemaError if it does not exist.
        """

    async def set_metadata(
        self,
        identity: SchemaIdentity,
        *,
        deprecated: bool | None = None,
        successor: SuccessorReference | None | Unset = UNSET,
    ) -> Schema:
        """Update the mutable metadata and return the updated version.

        `deprecated` changes only when non-None; `successor` changes only when it is not
        `UNSET`, where `None` clears it. Raises UnknownSchemaError if the version does
        not exist.
        """

    def list_versions(self, schema_name: SchemaName) -> AsyncIterable[Schema]:
        """Every version of one schema, newest first.

        Raises UnknownSchemaError if the name has no versions.
        """

    def list_names(self) -> AsyncIterable[SchemaName]:
        """Every name in the store, ascending."""
```

Note the last two are declared as plain `def` returning an `AsyncIterable`, which is what
an `async def ... yield` generator is.

`get_latest`, `list_latest` and `list_predecessors` come free. Override them only if your
store can answer them in fewer round trips than the default loop - the SQL backend does,
with one query each. **Resist reimplementing the `latest` rule while you are there.** Two
of the derived methods encode it, and it is policy rather than storage: the newest version
that is still current - neither deprecated nor superseded - falling back to the newest
outright when every version is disqualified, so that a schema always has a latest.
Inheriting it means you are correct about it before you have read this paragraph.

## What the contract expects that the signatures do not say

**The publication identifier is not yours to mint.** `publication_id` is a UUIDv7 created
above the repository layer, and it is the ordering of everything: `get_latest`,
`list_latest` and `list_versions` all derive from it, and the version string is never
compared. Store the value you are handed. A backend that minted its own would order
correctly in isolation and wrongly against anything that had already read the value. Store
it in a form that preserves byte order, because that is what makes it sortable.

**`published_on` is derived, never stored.** It is computed from the identifier's high
bits, so there is no second value to drift.

**Immutability is per field, not per row.** `set_metadata` touches `deprecated` and
`successor` and nothing else; identity, document and publication identifier are fixed once
written. The domain is the arbiter here, so you do not need to enforce it with database
grants or a second table - but you must not break it.

**Ordering is part of the contract, in three places.** `list_versions` yields newest
first, by publication identifier. `list_latest` yields name-ascending. `list_names` yields
ascending **by byte value** - see the collation trap below. Two instances reading the same
catalog have to list it identically, so "ascending" has to mean exactly one thing.

**There is no reset.** How your store gets emptied is your business, because the running
application never needs it - only your tests do. Emptying a catalog is a real operation,
but it belongs to a client over the API, not to a storage backend.

**Everything is async.** If your client library is blocking, do what the filesystem and S3
backends do: keep synchronous private helpers and wrap each in `asyncio.to_thread`.

## Proving it works

The contract is published as a test suite. Subclass it and supply one fixture yielding an
**empty** repository:

```python
import pytest

from schematalog.testing import SchemaRepositoryConformance

from my_backend import MySchemaRepository


class TestMyBackendConformance(SchemaRepositoryConformance):
    @pytest.fixture
    async def repository(self):
        repo = MySchemaRepository(...)
        yield repo
        await repo.teardown()          # or a temp directory, or a fresh database
```

Every case in the suite is `async def`, so **pytest-asyncio must be in automatic mode**
or none of them will run - in its default strict mode you get 27 errors about an async
fixture nothing handled, rather than 27 results. The plugin arrives with the `testing`
extra; the mode is one line you have to add:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

That is 27 cases covering all eight methods, run against a sample document with nesting,
arrays and mixed types - a trivial `{"type": "object"}` round-trips through almost
anything and so proves almost nothing. Every backend in the registry signs this suite, and
so does the S3 one, which lives outside it entirely.

The suite is the specification. If a case looks wrong to you, that is worth raising: it
means either the contract or its documentation is unclear.

## Registering the scheme

A storage URL's scheme selects the backend. Declare an entry point in the
`schematalog.storage` group, named for the scheme you answer to:

```toml
[project.entry-points."schematalog.storage"]
redis = "my_backend:build_repository"
```

That is the whole of registration. Installing your package adds the scheme; nothing in
Schematalog is edited, and nothing there knows your package exists.

The value is a **builder**: a callable taking the storage URL as a string and returning
your repository. It parses its own URL - the registry hands it over whole rather than
picking it apart, because only your backend knows which parts are addressing and which are
options.

```python
from urllib.parse import parse_qsl, urlsplit


def build_repository(url: str) -> MySchemaRepository:
    parts = urlsplit(url)
    options = dict(parse_qsl(parts.query))
    return MySchemaRepository(host=parts.netloc, prefix=parts.path.strip("/"), **options)
```

Two rules govern what happens next, both of them protective:

- **You cannot shadow a built-in scheme.** An installed package quietly taking over
  `postgresql` could redirect an instance's data, which is far too much authority to
  acquire by accident. The conflict is logged and the built-in kept.
- **A backend that fails to load is logged and skipped.** One broken package must not stop
  an instance starting on a store it was never asked for.

### If you would rather not package it

For a backend that is internal enough that publishing it makes no sense, there is
`python://<dotted.module.path>`, which imports that module and calls its
`build_repository`. Same builder, no packaging.

```shell
SCHEMATALOG_STORAGE_URL=python://mycompany.schematalog_backend
```

### On naming

Do not name your distribution `schematalog-something`. That prefix is reserved on PyPI,
and you do not need it: discovery is by entry point, not by name, so a package called
anything at all registers a scheme just the same. Name it for what it is.

## What went wrong when we walked this path

Every seam here has had something wrong with it that only appeared on contact. The S3
backend was the first one built entirely from outside, and this is what it and the
integration lane turned up. You are likely to meet at least one of them.

**A URL scheme may not contain an underscore.** RFC 3986 allows letters, digits, `+`, `-`
and `.`, and `urlsplit` does not object to a scheme with an underscore - it silently
reports *no scheme at all*. So `my_backend://x` fails while `mybackend://x` works, in a
way that looks like your entry point is broken. This is why the escape hatch above puts
the module path in the *authority* rather than the scheme: Python module names use
underscores constantly.

**Databases disagree about ordering, and the default is usually not byte order.** The
suite pins name listing to byte value, and a store that sorts in Python passes without
trying. SQLite passes too, since its default `BINARY` collation agrees with Python. A
store that delegates sorting to a database with opinions does not: PostgreSQL uses the
database's locale collation, which is why the identifier columns here pin `COLLATE "C"`,
and MySQL's default is case- and accent-insensitive, so a MySQL backend would fail until
it said otherwise. If your store has a collation setting, that test tells you which one to
pick.

**PostgreSQL has no `max()` aggregate over `uuid`.** SQLite obliges, so a query that works
in development can fail in production. `ORDER BY ... LIMIT 1` works everywhere.

**Do not read a v7 timestamp with `UUID.time`.** A driver may hand you a `uuid.UUID`
*subclass* of its own - the PostgreSQL async driver does - and on such an instance `.time`
takes the version-1 branch and returns a different number for the very same bits. Derive
it from the layout instead: `identifier.int >> 80`. Every failure mode here is silent,
which is why the domain rejects a non-v7 identifier outright.

**Lazy connections make a broken configuration look healthy.** Most clients connect on
first use, so a wrong host or password builds a repository quite happily and fails on the
first request instead. Make sure `list_names` works against an empty store without special
handling - that is the probe `schematalog check` and `GET /health` use, and it is how an
operator finds out your backend is misconfigured before their users do.

## Three worked examples

- **The filesystem backend**, in `schematalog/app/infrastructure/repositories/filesystem.py`
  - small enough to read in a sitting, and the model for wrapping blocking calls.
- **`schematalog-s3`**, in `packages/schematalog-s3/` - a real backend living entirely
  outside the registry, with its own distribution, entry point and tests. The closest
  thing to a template for what you are about to write.
- **The probe backend**, in `tests/unit/wiring/_plugin_probe/backend.py` - the five methods
  and nothing else, stored in a list. It is the smallest possible demonstration that the
  derived three come out correct for free.
