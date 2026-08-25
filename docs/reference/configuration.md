# Configuration

Schematalog is configured through environment variables (or a `.env` file), all
prefixed with **`SCHEMATALOG_`**.

```shell
SCHEMATALOG_STORAGE_URL=file:///data/schemas
```

With nothing set at all it runs on SQLite in the working directory, which needs no
external service.

After changing any of this, `schematalog check` opens the configured store and reports
whether it answered. Worth the habit: a backend connects lazily, so a setting that is
wrong in a way the application cannot see at start-up surfaces as a failed request
rather than a failed launch.

## Top-level settings

| Variable | Default | Description |
| --- | --- | --- |
| `SCHEMATALOG_DEBUG` | `false` | Enables debug mode and verbose logging. |
| `SCHEMATALOG_ENVIRONMENT` | `development` | Deployment *stage*: `development`, `staging`, or `production`. |
| `SCHEMATALOG_PLATFORM` | `local` | Deployment *target*: `local`, `compose`, or `fly`. |
| `SCHEMATALOG_STORAGE_URL` | `sqlite:///./schematalog.db` | The store: scheme selects the backend. |

`ENVIRONMENT` and `PLATFORM` are orthogonal axes: one platform can host several
stages.

## Storage backends

The backend is selected by the **scheme** of `SCHEMATALOG_STORAGE_URL`, and that
backend's own options travel as query parameters. One variable configures the store
completely; there is no second place to look. For *which* backend to choose, see
[Choosing a storage backend](../guides/storage.md).

| Scheme | Backend | Example |
| --- | --- | --- |
| `sqlite` | SQLAlchemy over SQLite | `sqlite:///./schematalog.db` |
| `postgresql`, `postgres` | SQLAlchemy over PostgreSQL | `postgresql://user:pass@host/dbname` |
| `file` | Plain files on disk | `file:///data/schemas`, or `file://storage_` for a relative path |
| `memory` | Ephemeral, in-process | `memory://` |
| `s3` | Objects in an S3 bucket | `s3://bucket/prefix?region=eu-west-2` (needs `schematalog-s3`) |

The async driver is filled in for you: `sqlite:` becomes `sqlite+aiosqlite:` and
`postgresql:` becomes `postgresql+asyncpg:`, so a platform-provided `DATABASE_URL` can
be used verbatim. Naming a driver explicitly leaves it alone.

### Options

The SQLAlchemy backends take two, as query parameters:

| Parameter | Default | Description |
| --- | --- | --- |
| `pool_pre_ping` | `true` | Check a pooled connection is alive before using it. |
| `pool_recycle` | `1800` | Replace a pooled connection after N seconds. |

```shell
SCHEMATALOG_STORAGE_URL="postgresql://user:pass@host/dbname?pool_recycle=900"
```

Any parameter the backend does not claim is left on the URL for the driver, so
`?sslmode=require` reaches PostgreSQL untouched.

Schemes from installed backends work the same way: `s3` above comes from the separate
`schematalog-s3` package, and installing it is the whole of the configuration.

!!! warning "Tables are created, never altered"
    The schema is built by a lazy `create_all` on first use, which can only create
    missing tables. A change to an existing table therefore needs the database
    recreated - there is no migration tool in the project (see `DECISIONS.md`).
