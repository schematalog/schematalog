# Using the API

The JSON API is the product; everything the registry can do is reachable over HTTP,
and the built-in web UI is a client of the same behaviour rather than a privileged
one. There are no credentials - an instance is trusted to whoever can reach it.

- **[Publishing schemas](publishing.md)** - `POST /api/schemas`, the versioning
  rules, and what the registry does to your document on the way in.
- **[Retrieving schemas](retrieving.md)** - reading versions back, the canonical
  `$id` stamped into every served document, and `$ref` resolution.
- **[Deprecation and successors](lifecycle.md)** - the only metadata that is mutable
  after publication, and how a superseded version points at its replacement.
- **[API reference](reference.md)** - the endpoint table and error responses, plus
  where to find the generated OpenAPI spec.

If you are reading in order, publishing and retrieving are the whole core; the other
two pages are for when a schema has been superseded and when you want the exact
shape of a response.
