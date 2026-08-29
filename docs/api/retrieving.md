# Retrieving schemas

There are three read shapes, plus a name-only convenience redirect.

| Request | Returns |
| --- | --- |
| `GET /api/schemas` | Latest version of every readable schema, name-ascending. |
| `GET /api/schemas/{name}/versions` | All versions of one name, newest first. |
| `GET /api/schemas/{name}/versions/{version}` | The JSON Schema document for one version (its canonical URL). |
| `GET /api/schemas/{name}` | `302` redirect to the latest version's canonical URL. |

The list endpoints return the wire DTO (`name`, `version`, `canonical_url`,
`description`, `schema`, `publication_id`, `published_on`, `deprecated`, `successor`).
The single-version endpoint returns the **JSON Schema document itself** — so the
URL is directly usable as a `$ref` target.

Reads are open: everything in an instance is readable, by anyone.

## Searching

`GET /api/schemas` accepts a `q` parameter that narrows the listing to schemas whose
**name** contains it, ignoring case:

```shell
curl "https://schematalog.com/api/schemas?q=billing"
```

It is a plain substring match on the name. Being explicit about what it does *not* do,
because these are the things a search box usually implies:

- it does not stem, so `orders` does not find `order`;
- it does not correct spelling or match approximately;
- it does not rank. Results keep the same name-ascending order they have without a
  query, so a result's position tells you nothing about how well it matched;
- it does not yet search descriptions or the schema document itself.

A blank or missing `q` selects everything, so an empty search box behaves as no search
rather than as a search for nothing.

That narrowness is deliberate. The same query runs against whichever storage backend an
instance is configured with, and each is free to answer it however it can answer it
fastest - so the promise is kept small enough that every backend can keep it *exactly*.
A backend may be quicker; it may not be different. The published conformance suite
tests this, which is why a backend cannot quietly turn on stemming.

## Canonical `$id`

When a version is served, Schematalog stamps the document with a canonical `$id`
equal to its permalink:

```
https://schematalog.com/api/schemas/address/versions/1.0.0
```

It also fills in a `title` (defaulting to the schema name) and a `description` (from
the stored description, if the document does not already carry one). This makes
every served schema **self-identifying**: the `$id` is a real, fetchable URL.

!!! note "The canonical `$id` is authoritative"
    The registry strips any `$id` you publish and re-stamps this one on every read,
    so the served `$id` always reflects where the schema actually lives — even if it
    is later served from a different host. The stored definition is never mutated by
    this; stamping happens at the response boundary.

## `$ref` resolution

Because each version's canonical URL serves the bare JSON Schema document and
advertises it as `$id`, you can reference one stored schema from another by URL:

```json
{
  "type": "object",
  "properties": {
    "billing_address": {
      "$ref": "https://schematalog.com/api/schemas/address/versions/1.0.0"
    }
  }
}
```

A standard JSON Schema validator that follows `$ref`s by retrieval will fetch the
referenced version directly from the registry.

## Lifecycle links

The single-version endpoint also surfaces lifecycle relationships as
[RFC 5829](https://www.rfc-editor.org/rfc/rfc5829) `Link` headers
(`successor-version`, `predecessor-version`) and reflects deprecation in the
document. See [Lifecycle](lifecycle.md).