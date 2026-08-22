# Deprecation and successors

A published version is immutable, but its **lifecycle metadata** is mutable. Two
related signals let you retire a version without deleting it:

- **`deprecated`** — a boolean flag marking the version as no longer recommended.
- **`successor`** — a URI pointing at the version that supersedes this one.

Both are set with `PATCH` (owner only) and both are reflected when the schema is
read back.

## Marking a version deprecated

```shell
curl -X PATCH https://schematalog.com/api/schemas/address/versions/1.0.0 \
  -H "Content-Type: application/json" \
  -d '{"deprecated": true}'
```

When a version is deprecated, its served document carries the standard JSON Schema
`"deprecated": true` keyword. The registry is the source of truth here: it sets the
keyword when deprecated and removes it otherwise, so an author-written `deprecated`
in the stored document can never contradict the registry.

## Pointing at a successor

```shell
curl -X PATCH https://schematalog.com/api/schemas/address/versions/1.0.0 \
  -H "Content-Type: application/json" \
  -d '{"successor": "https://schematalog.com/api/schemas/address/versions/2.0.0"}'
```

A successor URL that points back at this registry is **internal**: it is validated
(the target version must exist) and canonicalised. Any other absolute URL is kept
as an **external** reference as-is. A self-referential or missing internal successor
is rejected with `422 Unprocessable Entity`.

The `successor` field is **tri-state** on `PATCH`:

| Body | Effect |
| --- | --- |
| field omitted | leave the successor unchanged |
| `"successor": null` | clear the successor |
| `"successor": "<url>"` | set/replace the successor |

## How relationships are served

`GET /api/schemas/{name}/versions/{version}` advertises lifecycle relationships as
[RFC 5829](https://www.rfc-editor.org/rfc/rfc5829) `Link` headers:

```
Link: <https://schematalog.com/api/schemas/address/versions/2.0.0>; rel="successor-version",
      <https://schematalog.com/api/schemas/address/versions/0.9.0>; rel="predecessor-version"
```

- **`successor-version`** comes straight from the version's stored `successor`.
- **`predecessor-version`** is **derived**: any version whose successor points at
  this one is reported as a predecessor. You never set predecessors directly.

!!! note "Single-hop, closed-world"
    The API answers one hop at a time within this registry. Walking a whole
    successor chain ("is X eventually superseded by Y?") and enforcing graph
    acyclicity across registries are deliberately left to the future client SDK, not
    the API.