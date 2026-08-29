# Using the web UI

Every instance serves a server-rendered browser view at `/`, alongside the JSON API.
It is deliberately small. It exists to make an instance explorable without a client -
so that a colleague sent a link can see what a schema is - and it is a demonstration
of the API rather than the main way to use one. The richer interface is a separate
project.

What it offers:

- **The catalog** (`/schemas/`) - every schema name with its latest version, with a
  search box that narrows it by name. It is an ordinary form: the query goes into the
  URL, so a search can be linked or bookmarked, and it works with JavaScript turned off.
  It matches exactly what [the API's `q` parameter](../api/retrieving.md#searching)
  matches, being the same call.
- **A schema's page** (`/schemas/{name}`) - the document, its description, its
  properties, and a version picker. Deprecated versions are badged, and a version
  with a successor links to it. Code blocks are highlighted server-side and have a
  copy button.
- **[Format conversion](formats.md)** - the same document rendered as JSON, YAML,
  Avro, or generated Pydantic models. This is the one capability that exists only
  here and has no API equivalent.
- **A publish form** (`/publish`) - the same operation as `POST /api/schemas`, with
  a schema editor, for a one-off publication you would otherwise write `curl` for.

Nothing here requires JavaScript to work; the editor and the copy buttons enhance
pages that already function without them.
