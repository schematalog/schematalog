# Publishing schemas

Publishing creates a new, immutable schema **version**. It needs no credentials:
everything an instance can do is open to anyone who can reach it.

```
POST /api/schemas
```

## Request body

```json
{
  "name": "address",
  "version": "1.0.0",
  "description": "A postal address.",
  "schema": { "type": "object", "properties": { "street": {"type": "string"} } }
}
```

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | Logical schema name; groups all versions. |
| `version` | yes | Opaque version string you choose. |
| `schema` | yes | The JSON Schema document itself. |
| `description` | no | Free-text description (rendered as Markdown in the UI). |

!!! tip "`schema` vs `json_schema`"
    The wire field is `schema`. (Internally it maps to `json_schema`; both names are
    accepted on input, but prefer `schema`.)

## Naming, and the dot convention

A name may contain letters, digits, `-`, `_` and `.`, and must start with a letter or
a digit. Every name lives in **one flat namespace per instance**, so there is exactly
one `customer` in a registry.

The examples here write names like `billing.customer`, and it is worth being precise
about what that dot does: **nothing**. It is an ordinary character in the name.
`billing.customer` is a single name, not a `customer` inside a `billing` container.
There is no registry of prefixes, no endpoint that lists them, and no way to grant or
deny anything on one.

What the convention buys you is real but modest, and comes entirely from the name being
a string:

- names sort together, so `GET /api/schemas` groups them visually;
- `GET /api/schemas?q=billing.` finds them, since [search](retrieving.md#searching)
  matches a substring of the name.

**It is deliberately a convention rather than a mechanism.** Any grouping the registry
enforced would have to be part of a schema's address, and the address is the canonical
`$id` that must resolve forever - so moving a schema between groups would either be
forbidden or would break a permalink. Leaving grouping to the name costs nothing and
forces nobody: adopt dots, adopt some other separator, or use flat names.

If you want prefixes to *mean* something rather than merely read well, that is what
labels will be for; `DECISIONS.md` in the repository records why grouping stayed soft.

## Versioning

There is no enforced version *format* — any string works (`1.0.0`, `2025-06`, `v3`).
What matters is ordering: versions sort **lexicographically**, and the greatest
version of a name is its *latest* (what `GET /api/schemas` and the
name-only redirect resolve to).

!!! warning "Lexicographic, not semantic"
    Because ordering is lexicographic over the raw string, `10` sorts *before* `9`
    and `1.10.0` *before* `1.9.0`. If you want numeric-feeling ordering, zero-pad
    (`01`, `02`, … `10`) or use a date-based scheme.

Each `(name, version)` is unique. Re-publishing an existing pair is a conflict:

```
HTTP/1.1 409 Conflict
{ "detail": "..." }
```

To correct a published version you publish a **new** version — existing versions
never change (see [Lifecycle](lifecycle.md) for marking a version deprecated and
pointing at its successor).

## What the registry does to your document

On publish, Schematalog validates and normalises the document:

1. **Metaschema validation.** The document is checked against its declared
   `$schema`. Supported drafts: **draft-04, draft-06, draft-07, 2019-09, and
   2020-12**.
2. **`$schema` inference.** If you omit `$schema` (or it is invalid), the registry
   infers it by trying each supported draft newest-first and inserting the first
   that validates. A document that matches no supported draft is rejected with
   `422 Unprocessable Entity`.
3. **OpenAPI `nullable` conversion.** A pre-3.1 OpenAPI `"nullable": true` is
   rewritten to add `"null"` to the field's `type`, recursively through
   `properties`.
4. **`$id` stripping.** Any incoming `$id` is **removed**. The registry owns
   identity: it stamps its own canonical `$id` when the schema is read back (see
   [Retrieving](retrieving.md)). Do not rely on a `$id` you submit.

## Response

`201 Created`, with a `Location` header set to the new version's canonical URL and
the stored schema in the body (including the stamped `$id`, inferred `$schema`, and
a `title` defaulted to the schema name). See the
[Getting started](../getting-started.md#publishing) example.