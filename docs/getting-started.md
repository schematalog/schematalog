# 🚀 Getting started

## Running an instance

```shell
pip install schematalog-app
schematalog serve
```

That is the whole of it. With nothing configured, the registry stores schemas in a
SQLite file in the working directory - no database to provision, nothing to set - and
serves the JSON API and the web UI on <http://127.0.0.1:8000>.

`schematalog info` reports the version and which storage backend the configuration
resolved to, which is the quickest way to check an instance is set up the way you think.
It stops short of the store itself, and it never prints the storage URL - that routinely
carries a password, and `info` output is exactly what gets pasted into an issue.

`schematalog check` goes the rest of the way and opens the store. This matters more than
it sounds: every backend connects lazily, so a wrong host, a wrong password or an
unwritable directory all start perfectly well and fail on the first request instead.

```shell
$ schematalog check
schematalog 0.1.0
storage scheme: sqlite (recognised)
store:          reachable
```

It exits non-zero when the store is not usable, so a deploy script can gate on it, and
it separates the three ways that happens - an unrecognised scheme, options that do not
validate, and a store that will not answer - because each has a different fix.

The same question over HTTP is **`GET /health`**: `200` when the store answered, `503`
when it did not, so a load balancer, a container health check or an uptime monitor can
act on the status code alone. The body carries no detail - the endpoint is public, and a
driver's connection error names hosts and user names - so the reason goes to the log,
where only the operator can read it.

When you outgrow the default, [Choosing a storage backend](guides/storage.md) covers
what to move to and why.

The rest of this page walks through reading and publishing a schema. The examples use
`https://schematalog.com`; substitute the address of your own instance.

## Reading is open

Listing and fetching schemas needs no credentials:

```shell
# Latest version of every schema
curl https://schematalog.com/api/schemas

# All versions of one schema, newest first
curl https://schematalog.com/api/schemas/address/versions

# One specific version (its canonical URL)
curl https://schematalog.com/api/schemas/address/versions/1.0.0
```

## Publishing

Writes need no credential: an instance is trusted to whoever can reach it. The
decision record explains why authentication was removed, and what would have to
change for that to be revisited.

Publish a version with `POST /api/schemas`:

```shell
curl -X POST https://schematalog.com/api/schemas \
  -H "Content-Type: application/json" \
  -d '{
        "name": "address",
        "version": "1.0.0",
        "description": "A postal address.",
        "schema": {
          "type": "object",
          "properties": {
            "street": {"type": "string"},
            "city": {"type": "string"}
          },
          "required": ["street", "city"]
        }
      }'
```

On success you get `201 Created`, a `Location` header pointing at the new version's
canonical URL, and the stored schema in the body — including the canonical `$id`
stamped into the document:

```json
{
  "name": "address",
  "version": "1.0.0",
  "canonical_url": "https://schematalog.com/api/schemas/address/versions/1.0.0",
  "description": "A postal address.",
  "schema": {
    "$id": "https://schematalog.com/api/schemas/address/versions/1.0.0",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "address",
    "type": "object",
    "properties": {"street": {"type": "string"}, "city": {"type": "string"}},
    "required": ["street", "city"]
  },
  "publication_id": "01a02b03-6e2b-706c-8800-7b15c130a24b",
  "published_on": "2026-06-19T10:00:00Z",
  "deprecated": false
}
```

!!! note "Note the registry's `$id` and `$schema` handling"
    You did not send `$id` or `$schema`. Schematalog **strips any incoming `$id`**
    on publish and **stamps its own canonical one** on read, and it **infers
    `$schema`** if you omit it. See [Publishing](guides/publishing.md) and
    [Retrieving](guides/retrieving.md).

## Next steps

- [Publishing](guides/publishing.md) — versioning rules and validation.
- [Retrieving](guides/retrieving.md) — canonical URLs and `$ref` resolution.