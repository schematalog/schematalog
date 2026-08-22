# schematalog-app

[Schematalog](https://schematalog.com) is a registry and catalog for JSON Schema
specifications: it stores versioned schema documents and serves them back for
validation, `$ref` resolution and format conversion.

```shell
pip install schematalog-app
schematalog serve
```

With nothing configured it stores schemas in a SQLite file in the working directory — no
database to provision — and serves a JSON API and a server-rendered web UI on
<http://127.0.0.1:8000>. `schematalog info` reports the version and which storage backend
your configuration resolved to.

## Storage

One setting selects and configures the store, its scheme choosing the backend:

```shell
SCHEMATALOG_STORAGE_URL=sqlite:///./schematalog.db          # the default
SCHEMATALOG_STORAGE_URL=postgresql://user:pw@host/db
SCHEMATALOG_STORAGE_URL=file:///data/schemas                # plain files you can grep and commit
```

Other backends install themselves: [`schematalog-s3`](https://pypi.org/project/schematalog-s3/)
adds the `s3` scheme. Writing your own needs
[`schematalog-core`](https://pypi.org/project/schematalog-core/) alone.

## What it gives you

A published version is **immutable** — its name, version, document and publication time
never change — and is served back stamped with a canonical `$id`, so a link to a schema
keeps working and keeps meaning the same thing. Versions are free-form strings ordered by
publication rather than by string comparison, and a version can be marked deprecated or
pointed at its successor without disturbing any of that.

Documents can be viewed as JSON, YAML, Avro or ready-to-use Python.
