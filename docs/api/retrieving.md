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

`GET /api/schemas` accepts a `q` parameter that narrows the listing to schemas matching
it, ignoring case:

```shell
curl "https://schematalog.com/api/schemas?q=billing"
```

The rule in one sentence: **every whitespace-separated word in the query must appear as
a substring of the schema's name or of its description.**

Two consequences worth spelling out. Adding a word *narrows* the result rather than
widening it, so a search can be refined by typing more:

```shell
curl "https://schematalog.com/api/schemas?q=billing%20invoice"
```

And the words need not all be found in the same field - a schema named `payment` whose
description mentions invoices answers `?q=payment%20invoice`. You typed one box, so
where each word was found is not something you should have to know.

Being explicit about what it does *not* do, because these are the things a search box
usually implies:

- it does not stem, so `orders` does not find `order`;
- it does not correct spelling or match approximately;
- it does not rank. Results keep the same name-ascending order they have without a
  query, so a result's position tells you nothing about how well it matched;
- it has no syntax. No quoting, no `AND`/`OR`, no negation, no wildcards - every
  character in a query is matched literally. This is a deliberate limit rather than an
  unfinished feature; see [decisions](https://github.com/schematalog/schematalog/blob/main/DECISIONS.md);
- because there is no quoting, there is no way to require two words be adjacent:
  `?q=order%20line` finds a schema mentioning both words anywhere, not the phrase;
- it does not yet search the schema document itself.

A blank or missing `q` selects everything, so an empty search box behaves as no search
rather than as a search for nothing. Whitespace around a query is trimmed, so
`?q=%20order%20` searches for `order`, and repeated words change nothing.

### What a query may contain

A query may hold letters, digits, `.`, `-` and `_`, with whitespace between words, up
to 128 characters. Anything else is answered with `422 Unprocessable Entity` rather than
with an empty list:

```shell
curl -i "https://schematalog.com/api/schemas?q=cafe%CC%81"   # 422
```

That is deliberate. An empty result would be indistinguishable from a search that
simply found nothing, leaving you to work out which had happened. It also keeps the
rule uniform across backends: some strings a URL can carry cannot be stored in a
database at all - a NUL byte is not valid in PostgreSQL text - and left unchecked the
same request answered `200 []` on one backend and failed on another.

**Accented and other non-ASCII characters are refused for a different reason.** They are
perfectly meaningful against a description, but no two stores lower-case them the same
way - SQLite handles only ASCII, PostgreSQL follows its collation - so allowing them
would mean the same search returning different results on different instances. That is
the one thing search here promises never to do, so the alphabet stays ASCII until the
backends are given a folded form to match against rather than folding as they query.

The 128-character cap is a resource guard rather than a meaningful boundary: no real
search comes close, and an unbounded query would otherwise reach the database as a
pattern to scan with.

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