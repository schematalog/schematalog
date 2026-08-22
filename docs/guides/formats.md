# Format conversion

Schematalog can render a stored schema in several formats beyond raw JSON Schema.
This is currently a feature of the **HTML UI**: a schema version's page offers
format tabs that present the same document as:

| Format | Notes |
| --- | --- |
| **JSON** | The JSON Schema document (with the canonical `$id`). |
| **YAML** | The same document, serialised as YAML. |
| **Python** | Pydantic v2 model source generated from the schema (via `datamodel-code-generator`). |
| **Avro** | An Avro schema, when the document is expressible in Avro. |

!!! note "UI feature, not a JSON API endpoint"
    There is no `?format=` parameter on the JSON API today; the API serves JSON
    Schema. Conversion lives in the browser UI. The underlying converters are
    in-process and could be exposed via the API later.

## Avro conversion and its limits

The JSON Schema to Avro conversion is handled by an in-house, dependency-free
converter (`avroform`). It covers the common subset:

- objects to records, and the JSON primitives;
- arrays, enums, and nested records;
- nullable types to Avro unions;
- string `format`s to Avro logical types.

It cannot express some JSON Schema constructs in Avro and will report that rather
than emit something wrong. Unsupported constructs include **`$ref`** and the
combinators **`oneOf` / `anyOf` / `allOf`**. When a document uses one of these, the
Avro tab shows an explanatory note instead of a conversion.

## Python (Pydantic) generation

The Python tab generates Pydantic v2 models from the schema. The canonical `$id` is
dropped before generation: it is an absolute URL pointing back at this registry, and
leaving it in would make the code generator try to fetch it as a remote base. The
generated code does not need it.

!!! tip "Full class generation is the SDK's job"
    The Python tab is a convenience preview. Turning stored schemas into rich,
    self-validating Python classes at scale is the planned, separate client SDK -
    this preview is not a substitute for it.