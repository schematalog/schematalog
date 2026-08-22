# schematalog

A registry and catalog for JSON Schema specifications: it stores versioned schema
documents and serves them back for validation, `$ref` resolution and format conversion.

```shell
pip install schematalog
schematalog serve
```

## What this package is

**This distribution contains no code.** It depends on
[`schematalog-app`](https://pypi.org/project/schematalog-app/), which is the registry.
It exists for two reasons:

- `pip install schematalog` should install the registry, because that is what someone
  typing the name intends.
- The project's Python modules live in a `schematalog.*` namespace shared across several
  distributions (`schematalog-core`, `schematalog-app`, `schematalog-s3`). A namespace
  like that accepts modules from *any* installed distribution, so leaving the matching
  name unclaimed would let an unrelated package place importable modules inside it.

## The pieces

| Distribution | What it is |
| --- | --- |
| `schematalog-app` | The registry: JSON API, web UI, storage wiring. |
| `schematalog-core` | The domain contract and its conformance suite - what a storage backend codes against. |
| `schematalog-s3` | An S3 storage backend, and the worked example of one living outside the registry. |

Writing a storage backend needs `schematalog-core` alone; it does not oblige you to
install a web framework.

The `schematalog-*` prefix is deliberately **not** reserved on PyPI, so third-party
backends are free to use it.
