# Deploying

Schematalog runs anywhere that can run a Python 3.14 process or a container, and it does not depend on any particular host. An instance needs three things: a way to start it, a store that outlives it, and a network that is safe to expose it to.

This page describes version 0.2 and later. `schematalog --version` tells you which you have.

## Starting it

The application is one process, listening on one port. From a Python install:

```shell
pip install schematalog-app
schematalog serve --host 0.0.0.0 --port 8000
```

`serve` binds to `127.0.0.1` by default, so without `--host` nothing outside the machine can reach it. If `pip` gives you a version older than 0.2, `schematalog check` and `GET /health` below will not exist yet, so build the container instead.

To build the container, use a checkout of the repository. The build has to run from the repository root, because the application shares the workspace with the packages it depends on:

```shell
docker build -f packages/schematalog-app/Dockerfile -t schematalog .
docker run -p 8000:8000 \
  -e SCHEMATALOG_STORAGE_URL=sqlite:////data/schematalog.db \
  -v schematalog-data:/data \
  schematalog
```

No image is published yet, so this is the way to get one. A few things to know about it:

- It listens on `0.0.0.0` port 8000 and does not read `$PORT`. On a host that assigns a port, tell the host to use 8000, or override the command with `schematalog serve --host 0.0.0.0 --port <port>`.
- It runs as root, and does not currently start as another user or on a read-only filesystem. A host that requires either needs its own image.
- It includes the `s3` backend.
- Passing the build arguments `GIT_COMMIT` and `GIT_COMMIT_DATE` makes `GET /version` report the commit and date, and the page footer the date. Without them, the commit reads `unknown`.

## Choosing where the data lives

Set `SCHEMATALOG_STORAGE_URL`, the one setting an instance has to get right. The default is a SQLite file in the working directory, which many hosts discard on every deployment, so check this first. [Choosing a storage backend](storage.md) goes through the options by type of deployment.

For PostgreSQL, the URL your provider gives you probably needs editing, because the driver used here takes only its own parameters:

- Rename `sslmode=X` to `ssl=X`, keeping the value. `require` encrypts the connection without checking the server's certificate, while `verify-full` also checks it, reading the certificate authority's file from the `PGSSLROOTCERT` environment variable.
- Remove any other connection parameters, such as `channel_binding`, `sslrootcert` or `connect_timeout`, which the driver refuses.

```shell
SCHEMATALOG_STORAGE_URL="postgresql://user:password@host/dbname?ssl=require"
```

If the provider offers both a direct address and a connection pooler, use the direct one. The driver prepares its statements on a particular connection, and a pooler that hands each transaction a different connection can lose them unless it tracks them itself. The symptom is occasional `500` responses while `/health` stays `200`. The application keeps its own pool of connections in any case.

## Checking it works

Every backend connects on first use, so a wrong host or password starts cleanly and only fails on the first request. `schematalog check` opens the store and exits non-zero if it cannot, which makes it a useful step before going live:

```shell
schematalog check
```

For the container, use `docker run` with the same `-e` and `-v` options, without `-p`, followed by `schematalog schematalog check`.

For your host's health check, use `GET /health`. It answers `200` if the store can be reached and `503` if not, and it deliberately gives no detail, since it is public; the reason goes to the log.

`/health` only proves the store answers. It does not prove the tables match this version of the application: after an upgrade that changes the table layout, it can answer `200` while reads fail.

## Exposing it

**An instance has no authentication.** Anyone who can reach it can read and publish, so keep it somewhere that reflects this, such as a private network or behind a proxy that does its own access control.

TLS is left to whatever sits in front of the application. That proxy needs to do three things:

- **Send the public address in the `Host` header**, including any non-standard port. The application builds its URLs, including each schema's `$id`, from that header, and it ignores `X-Forwarded-Host` and `Forwarded`. With nginx, for example, that means `proxy_set_header Host $http_host`.
- **Set `X-Forwarded-Proto`**, or the URLs will start with `http://`. The application trusts this header from any client, which is one more reason nothing should reach it except through the proxy.
- **Serve it at the root of the address.** Running it under a sub-path is not supported.

Use the instance's permanent address from the start. Each `$id` follows the address of the request, so it changes with the address. And when a version names its replacement at this address, that link is stored as a full URL, so the link back from the replacement stops working if the address changes.

**The application sends no CORS headers**, which browsers require before letting a page on another site read a response. If pages on other sites need to fetch your schemas, for example to follow a `$ref`, add the headers at your proxy.

## Upgrading

Until 1.0 there are no database migrations. Tables are created if missing and never altered, so a release can change the table layout, and moving to it then means recreating the store. Nothing announces this yet. The sign is that after an upgrade, `GET /api/schemas` answers `500` while `/health` answers `200`.

Recreating the store loses everything in it, so for an existing SQL database:

1. **While the old version is still running, save your data.** Back up the database, or read every version's document and metadata from `GET /api/schemas/{name}/versions`. Reads may fail from the next step on.
2. **Deploy the new version.** If that fails, nothing has been lost.
3. **Drop the old table:** `DROP TABLE "schema";`
4. **Restart the instance**, or every instance if you run several. A running instance does not notice the table has gone, so until it restarts, `/health` answers `503` and publishing fails.
5. **Publish your schemas again, each one's versions oldest first**, because the order of publication decides which version is the latest. Then set labels, deprecation and successors again. Publication dates and identifiers will be new.

Dropping the table before deploying leaves a gap in which the old version, if it restarts, recreates the old table.

## Settings that only label an instance

`SCHEMATALOG_ENVIRONMENT` and `SCHEMATALOG_PLATFORM` change nothing about how the instance behaves. Both are reported by `GET /version`, and `schematalog info` also shows the environment. `SCHEMATALOG_PLATFORM` accepts only `local`, `compose` or `fly`, and anything else stops the application from starting, so on another host leave it unset. It then reads `local`, which says nothing about where the instance actually runs.

## The Fly configuration in this repository

`packages/schematalog-app/fly.toml` and the `just deploy` recipe run the demo at [schematalog.com](https://schematalog.com) on [Fly.io](https://fly.io). They are that instance's setup rather than part of the product, and they are left out of the published packages, so treat them as one worked example.

The application itself does not depend on them. Two things the demo gets from `fly.toml` are easy to miss, though: its CORS headers, and the proxy that handles TLS. Any other host needs its own way of providing both. It also checks the port rather than calling `/health`, so it is not an example to follow on that point.
