# Schematalog

A registry and catalog for JSON Schema specifications.

The name is a portmanteau of *schemata* (the original plural of "schema") and
*catalog(ue)*: Schematalog stores versioned JSON Schema documents in one place and serves
them back for validation, `$ref` resolution and format conversion.

```shell
pip install schematalog
schematalog serve
```

With nothing configured it stores schemas in a SQLite file in the working directory — no
database to provision — and serves a JSON API and a server-rendered web UI on
<http://127.0.0.1:8000>. A live instance runs at <https://schematalog.com>.

## What it gives you

A published version is **immutable**: its name, version, document and publication time
never change. Only a small amount of lifecycle metadata is mutable afterwards. When a
version is served back it is stamped with a canonical `$id` — the permalink of that exact
version — so a link to a schema keeps working and keeps meaning the same thing, which is
what makes a registry more useful than a shared folder.

Beyond that: every submitted document is validated against the JSON Schema standards
(draft-04 through 2020-12, inferred if undeclared); every version of a name is kept and
listed; a version can be marked deprecated or pointed at its successor, with predecessors
derived automatically; and a stored schema can be viewed as JSON, YAML, an Avro record
definition, or ready-to-use Python.

**Versions are free-form strings and the registry never interprets them.** Ordering is a
registry fact rather than a reading of the string, so `10.0` does not sort before `9.0`,
and "latest" means the most recently published version that is neither deprecated nor
superseded.

## Storage

One setting selects and configures the store, its scheme choosing the backend:

```shell
SCHEMATALOG_STORAGE_URL=sqlite:///./schematalog.db          # the default
SCHEMATALOG_STORAGE_URL=postgresql://user:pw@host/db
SCHEMATALOG_STORAGE_URL=file:///data/schemas                # plain files you can grep and commit
```

Backends install themselves: [`schematalog-s3`](https://pypi.org/project/schematalog-s3/)
adds the `s3` scheme by being installed. Writing your own means implementing five methods
against `schematalog-core` and inheriting a published conformance suite that tells you
whether you got it right — see [Choosing a storage backend](docs/guides/storage.md).

## The packages

| Distribution | What it is |
| --- | --- |
| `schematalog` | A meta-package: installs the registry. |
| `schematalog-app` | The registry — JSON API, web UI, storage wiring. |
| `schematalog-core` | The domain contract and its conformance suite. |
| `schematalog-s3` | An S3 storage backend, living outside the registry. |

They share the `schematalog.*` import namespace and version independently. The
`schematalog-*` prefix is deliberately **not** reserved on PyPI, so third-party backends
are free to use it.

## Status

**Early.** Version 0.1.0 is the first release after a substantial change of direction:
Schematalog was built as a multi-tenant hosted service and has been rebuilt as software
an organisation installs and runs for itself. Authentication, tenancy and per-schema
visibility were removed rather than reduced; the API is the product.

The reasoning behind that and every other significant choice — including the options
turned down — is in [`DECISIONS.md`](DECISIONS.md). What is planned next is in
[`ROADMAP.md`](ROADMAP.md).

## Development

[`just`](https://just.systems) over [`uv`](https://docs.astral.sh/uv/); run `just` for
the full list.

```shell
just serve            # dev server with reload on port 3000
just test             # unit tests, per package
just test-integration # integration tests against real PostgreSQL (needs Docker)
just check            # lint, dependency, safety and type checks
just ready            # check + test, before considering work done
just build            # build every distribution into dist/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how the repository is laid out and where a
given kind of change belongs.

## Documentation

[`docs/`](docs/index.md) builds into a MkDocs site (`just docs`, served on port 7000) and
covers getting started, choosing a storage backend, publishing, retrieval and `$id`
resolution, the deprecation/successor lifecycle, format conversion, and configuration.
The generated API reference is served by the app itself at `/docs`, `/redoc` and
`/openapi.yaml`.

## Licence

MIT — see [LICENSE](LICENSE).
