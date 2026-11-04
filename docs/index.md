# Schematalog

Schematalog is a **registry and catalog for JSON Schema specifications**. It stores
versioned JSON Schema documents and serves them back for validation, `$ref`
resolution, and format conversion.

The name is a portmanteau of *schemata* (the original plural of "schema") and
*catalog(ue)*.

## The mental model

A stored schema is identified by a **`(name, version)`** pair:

- **`name`** groups every version of one logical schema (for example `address`). Names
  are flat and unique per instance; a dotted name like `billing.address` is a
  [convention](api/publishing.md#naming-and-the-dot-convention), not a hierarchy the
  registry knows about.
- **`version`** is an opaque string you choose (`1.0.0`, `2025-06`, `v3`, …).
  Schematalog never compares version strings: the *latest* version of a name is the
  most recently **published** one, which is why `10.0` does not sort below `9.0`.
  A version marked deprecated or given a successor drops out of the running, unless
  every version has, in which case the newest wins anyway.

Each version is **immutable** once published: its name, version, document, and
creation time never change. Only a small set of metadata is mutable after the fact
(see [Lifecycle](api/lifecycle.md)).

When you read a version back, Schematalog stamps it with a canonical **`$id`** — the
permalink of that exact version — so served schemas are self-identifying and
`$ref`-resolvable. See [Retrieving schemas](api/retrieving.md).

## Two surfaces, one app

| Surface | What it is | Auth |
| --- | --- | --- |
| **JSON API** (`/api`) | The primary, API-first interface. | None. |
| **HTML UI** (`/`) | A server-rendered browser view, with a publish form. | Anonymous. |

The interactive OpenAPI reference is always available at **`/docs`** (Swagger) and
**`/redoc`**, with the raw spec at **`/openapi.json`** and **`/openapi.yaml`**.

## 🧭 Where to next

Start with **[Getting started](getting-started.md)** for your first read and publish.
After that the documentation is organised by what you are here to do:

- **[Running an instance](operating/index.md)** — configuring it, choosing where
  schemas are stored, and writing your own backend if none of the built-in ones fit.
- **[Using the API](api/index.md)** — publishing, retrieving, the deprecation and
  successor metadata, and the endpoint reference.
- **[Using the web UI](webui/index.md)** — what the built-in browser view offers,
  including its format conversion tabs.
