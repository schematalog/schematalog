from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

# Accepted JSON Schema metaschemas, ordered oldest to newest. `infer_metaschema`
# tries them newest-first (i.e. reversed), so the order matters.
META_SCHEMAS: list[str] = [
    "https://json-schema.org/draft-04/schema",
    "https://json-schema.org/draft-06/schema",
    "https://json-schema.org/draft-07/schema",
    "https://json-schema.org/draft/2019-09/schema",
    "https://json-schema.org/draft/2020-12/schema",
]


class IncompatibleSchemaError(Exception):
    """Raised if a schema does not conform to any of the accepted meta schemas."""


def preprocess_schema(schema: dict) -> dict:
    schema = validate_metaschema(schema)
    schema = convert_openapi_nullable(schema)
    schema.pop("$id", None)
    return schema


def validate_metaschema(schema: dict) -> dict:
    """Validate schema against declared metaschema.

    If the schema does not declare the `$schema` keyword, infers the metaschema
    and inserts the keyword.
    """
    if "$schema" in schema:
        validator = validator_for(schema)
        try:
            validator.check_schema(schema)
        except SchemaError:
            return infer_metaschema(schema)
        else:
            return schema
    else:
        return infer_metaschema(schema)


def infer_metaschema(schema: dict) -> dict:
    """Infers and declares the correct metaschema for the schema.

    The metaschema is inferred by checking the schema against each
    of the supported metaschema URLs, starting with the latest.
    The first valid metaschema is inserted as the value of the
    `$schema` keyword.
    """
    for metaschema_url in reversed(META_SCHEMAS):
        schema["$schema"] = metaschema_url
        try:
            validator_for(schema).check_schema(schema)
        except SchemaError:
            pass
        else:
            return schema
    raise IncompatibleSchemaError


def convert_openapi_nullable(schema: dict) -> dict:
    """Converts the OpenAPI-style nullable to a null type.

    Prior to version 3.1, OpenAPI did not recognise the `null` type,
    instead using a separate keyword `nullable = true` to declare
    values that can be `null`. This functions removes this keyword
    and adds `"null"` to the list of declared types for that field.

    If the schema contains `properties`, it is applied recursively.
    """
    if schema.pop("nullable", ...) is True:
        if isinstance(schema["type"], str):
            schema["type"] = [schema["type"]]
        if "null" not in schema["type"]:
            schema["type"].append("null")
    for prop_name, prop in schema.get("properties", {}).items():
        schema["properties"][prop_name] = convert_openapi_nullable(prop)
    return schema
