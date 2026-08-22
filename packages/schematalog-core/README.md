# schematalog-core

The domain contract for [Schematalog](https://schematalog.com), a registry and catalog
for JSON Schema specifications — and the conformance suite that goes with it.

**This is what a storage backend codes against.** It deliberately does not depend on the
registry application, so implementing a backend does not oblige you to install a web
framework.

```shell
pip install schematalog-core[testing]
```

## Writing a storage backend

A backend implements five methods — `add`, `get`, `set_metadata`, `list_versions` and
`list_names`. Three more (`get_latest`, `list_latest`, `list_predecessors`) are derived
for you by `SchemaRepository`, including the rule for which version counts as *latest*,
so you inherit that rather than reimplementing it. Override them only if your store can
answer them better.

The contract is written as tests. Subclass it, supply one fixture yielding an empty
repository, and it tells you whether your backend is correct:

```python
import pytest
from schematalog.testing import SchemaRepositoryConformance

class TestMyBackend(SchemaRepositoryConformance):
    @pytest.fixture
    def repository(self):
        return MyRepository(...)
```

Registration is a `schematalog.storage` entry point naming the URL scheme you answer to;
nothing in the registry needs changing. See
[`schematalog-s3`](https://pypi.org/project/schematalog-s3/) for a complete worked
example.

## What it contains

- `schematalog.domain` — `Schema`, `SchemaRepository`, the value objects and errors.
- `schematalog.testing` — the conformance suite and a sample schema to test with.
- `schematalog.common` — layer-neutral helpers, including a dependency-free JSON Schema
  ↔ Avro converter.
