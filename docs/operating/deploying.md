# Deploying

Schematalog runs anywhere that can run a Python 3.14 process or a container, and it does not depend on any particular host. An instance needs three things: a way to start it, a store that outlives it, and a network that is safe to expose it to.

## Starting it

The application is one process, listening on one port. From a Python install:

```shell
pip install schematalog-app
schematalog serve --host 0.0.0.0 --port 8000
```

`serve` binds to `127.0.0.1` by default, so without `--host` nothing outside the machine can reach it.

Or build the container from a checkout of the repository. The build has to run from the repository root, because the application shares the workspace with the packages it depends on:

```shell
docker build -f packages/schematalog-app/Dockerfile -t schematalog .
docker run -p 8000:8000 \
  -e SCHEMATALOG_STORAGE_URL=sqlite:////data/schematalog.db \
  -v schematalog-data:/data \
  schematalog
```

No image is published yet, so this is the way to get one. The container already binds to `0.0.0.0` on port 8000, and it includes the `s3` backend. Passing the build arguments `GIT_COMMIT` and `GIT_COMMIT_DATE` makes `GET /version` and the page footer report the build; without them, the commit reads `unknown`.

## Choosing where the data lives

Set `SCHEMATALOG_STORAGE_URL`, the one setting an instance has to get right. The default is a SQLite file in the working directory, which many hosts discard on every deployment, so check this first. [Choosing a storage backend](storage.md) goes through the options by type of deployment.

For PostgreSQL, the URL most providers give you needs one change. They usually end it in `?sslmode=require`, which the driver used here does not accept, so write `?ssl=require` and leave out any `channel_binding` parameter:

```shell
SCHEMATALOG_STORAGE_URL="postgresql://user:password@host/dbname?ssl=require"
```

If the provider offers both a direct address and a connection pooler, use the direct one. A pooler in transaction mode breaks the prepared statements the driver relies on, and the application keeps its own pool anyway.

## Checking it works

Every backend connects on first use, so a wrong host or password starts cleanly and only fails on the first request. `schematalog check` opens the store and exits non-zero if it cannot, which makes it a useful step before going live:

```shell
schematalog check
```

In the container, that is `docker run <the same options> schematalog schematalog check`.

For your host's health check, use `GET /health`. It answers `200` if the store can be reached and `503` if not, and it deliberately gives no detail, since it is public; the reason goes to the log.

`/health` only proves the store answers. It does not prove the tables match this version of the application: after an upgrade that changes the storage schema, it can answer `200` while reads fail.

## Exposing it

**An instance has no authentication.** Anyone who can reach it can read and publish, so keep it somewhere that reflects this, such as a private network or behind a proxy that does its own access control.

TLS is left to whatever sits in front of the application. It builds its URLs, including each schema's `$id`, from the host of the incoming request and from `X-Forwarded-Proto`, so your proxy has to pass both along. It trusts those headers from any client, which is one more reason nothing should reach the application except through the proxy. Serve the instance from its permanent address from the start: an internal successor is stored as a full URL, and a predecessor is only found while that URL still matches.

## Upgrading

Until 1.0 there are no database migrations. Tables are created if missing and never altered, so a release that changes the storage schema means recreating the store. The safe order for an existing SQL database:

1. Deploy the new version. If that fails, nothing has been lost. Until the next step is done, reads may fail.
2. Drop the old table: `DROP TABLE "schema";`
3. Publish your schemas again, which creates the new table.

Doing it the other way round leaves a gap in which the old version, if it restarts, recreates the old table.

## Settings that only label an instance

`SCHEMATALOG_ENVIRONMENT` and `SCHEMATALOG_PLATFORM` change nothing about how the instance behaves; they are only reported by `GET /version` and `schematalog info`. `SCHEMATALOG_PLATFORM` accepts only `local`, `compose` or `fly`, and anything else stops the application from starting, so on another host leave it unset. It then reads `local`, which says nothing about where the instance actually runs.

## The Fly configuration in this repository

`packages/schematalog-app/fly.toml` and the `just deploy` recipe run the demo at [schematalog.com](https://schematalog.com) on [Fly.io](https://fly.io). They are that instance's setup rather than part of the product. Nothing in the application depends on them, and they are left out of the published packages, so treat them as one worked example.
