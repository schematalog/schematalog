# Contributing

Thanks for looking. This document covers how the repository is laid out, how to run
things, and where a given kind of change belongs.

## Getting set up

[`just`](https://just.systems) over [`uv`](https://docs.astral.sh/uv/); `just` on its own
lists every recipe.

```shell
uv sync --all-groups   # Python, all packages and dev groups
just install-fe        # frontend dependencies (pnpm), once per checkout
just ready             # checks + tests: run this before considering work done
```

Integration tests need Docker (`just test-integration` starts PostgreSQL itself). Python
is always run through `uv run`, never a bare `python`.

## The packages

Four distributions share the `schematalog.*` import namespace, in a `uv` workspace whose
root is not itself a distribution.

| Path | Provides | Depends on |
| --- | --- | --- |
| `packages/schematalog-core` | `schematalog.domain`, `.common`, `.testing` | pydantic, jsonschema |
| `packages/schematalog-app` | `schematalog.app.*` | core, FastAPI, SQLAlchemy |
| `packages/schematalog-s3` | `schematalog.s3` | core, boto3 |
| `packages/schematalog` | nothing — a meta-package | app |

**A storage backend depends on `core` alone.** That is the reason for the split:
implementing five methods should not oblige anyone to install a web framework. Keep core
small, and be suspicious of anything that wants to add a dependency to it.

There is deliberately **no `schematalog/__init__.py`** at the namespace level. Adding one
would make a single distribution own the namespace and shadow the others.

Each package declares its own dependencies in its own `pyproject.toml`; the root declares
only the packages. Each versions independently, and versions start at 0.1.0.

## Inside the application

Layered, dependencies pointing inward:

```
domain/          what a schema is; the storage contract   (core)
application/     use cases; commands in, views out        (app)
infrastructure/  storage implementations                  (app)
presentation/    FastAPI: api/ (JSON) and webapp/ (HTML)  (app)
```

Two rules the codebase enforces on itself:

- **Presentation never imports `domain`.** The application layer is presentation's
  complete contract. `grep -r "from schematalog.domain" packages/schematalog-app/schematalog/app/presentation/`
  must come back empty.
- **Domain errors never reach presentation.** Services catch them and re-raise
  application errors, which presentation maps to HTTP centrally. Route handlers carry no
  `try`/`except`.

## Tests

Split by *external dependencies*, not speed. Each package carries its own tests, and each
lane is a directory rather than a flag:

```
packages/*/tests/unit/          no external services; this is what `just test` runs
packages/*/tests/integration/   real composed services; `just test-integration`
```

**Storage behaviour goes in the conformance suite, not in a per-backend test.** Anything
every backend must satisfy belongs in `schematalog.testing.SchemaRepositoryConformance`,
so all of them are held to it; only behaviour true of *one* backend belongs in that
backend's own file. Writing a general requirement as a one-backend test is how a
requirement quietly loses coverage.

Name tests so the name reads as a sentence: `test_get_latest_skips_a_deprecated_version`.

## Writing a storage backend

You need `schematalog-core` and nothing else. Implement five methods — `add`, `get`,
`set_metadata`, `list_versions`, `list_names` — and inherit `get_latest`, `list_latest`
and `list_predecessors`, including the rule for which version counts as latest. Subclass
`SchemaRepositoryConformance`, supply one fixture yielding an empty repository, and the
suite tells you whether you are correct.

Register with a `schematalog.storage` entry point named for the URL scheme you answer to.
Nothing in the registry needs to change. `packages/schematalog-s3` is a complete worked
example, and it lives outside the registry precisely to prove that works.

## Before opening a pull request

```shell
just ready              # lint, dependency, safety and type checks, plus unit tests
just test-integration   # if you touched storage
```

Small, focused commits; a lowercase imperative subject, and a body explaining *why*
rather than restating the diff.

## Where decisions live

- **`DECISIONS.md`** — what was chosen, when, and what was turned down. Entries are never
  revised; a reversal gets a new entry that supersedes the old one. Add one when a change
  is something a reasonable person might later propose the opposite of.
- **`ROADMAP.md`** — what is next and what is still open.
- **`README.md`** — what this is.

If a change contradicts a recorded decision, that is fine — but say so in a new entry
rather than editing the old one, so the trail stays readable.
