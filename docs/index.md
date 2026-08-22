# Schematalog

Schematalog is a **registry and catalog for JSON Schema specifications**. It stores
versioned JSON Schema documents and serves them back for validation, `$ref`
resolution, and format conversion.

The name is a portmanteau of *schemata* (the original plural of "schema") and
*catalog(ue)*.

## The mental model

A stored schema is identified by a **`(name, version)`** pair:

- **`name`** groups every version of one logical schema (for example `address`).
- **`version`** is an opaque string you choose (`1.0.0`, `2025-06`, `v3`, …).
  Versions sort lexicographically, and the lexicographically-greatest version of a
  name is its *latest*.

Each version is **immutable** once published: its name, version, document, and
creation time never change. Only a small set of metadata is mutable after the fact
(see [Lifecycle](guides/lifecycle.md)).

When you read a version back, Schematalog stamps it with a canonical **`$id`** — the
permalink of that exact version — so served schemas are self-identifying and
`$ref`-resolvable. See [Retrieving schemas](guides/retrieving.md).

## Two surfaces, one app

| Surface | What it is | Auth |
| --- | --- | --- |
| **JSON API** (`/api`) | The primary, API-first interface. | None. |
| **HTML UI** (`/`) | A server-rendered, read-only browser view. | Anonymous. |

The interactive OpenAPI reference is always available at **`/docs`** (Swagger) and
**`/redoc`**, with the raw spec at **`/openapi.json`** and **`/openapi.yaml`**.

## 🧭 Where to next

- **[Getting started](getting-started.md)** — your first read and publish.
- **Guides** — [choosing a storage backend](guides/storage.md),
  [publishing](guides/publishing.md), [retrieving](guides/retrieving.md),
  [lifecycle](guides/lifecycle.md),
  [format conversion](guides/formats.md).
- **Reference** — [the API](reference/api.md),
  [configuration](reference/configuration.md).