import pytest

from schematalog.common.validation import (
    META_SCHEMAS,
    IncompatibleSchemaError,
    convert_openapi_nullable,
    validate_metaschema,
)


@pytest.mark.parametrize(
    "old_type, new_type",
    (
        ("string", ["string", "null"]),
        ("integer", ["integer", "null"]),
    ),
)
def test_openapi_nullable_is_replaced_with_null_type(old_type, new_type):
    schema = {"type": old_type, "nullable": True}
    new_schema = convert_openapi_nullable(schema)

    assert "nullable" not in new_schema
    assert new_schema["type"] == new_type


@pytest.mark.parametrize(
    "old_type, new_type",
    (
        ("string", ["string", "null"]),
        ("integer", ["integer", "null"]),
    ),
)
def test_openapi_nullable_is_replaced_with_null_type_recursively(old_type, new_type):
    schema = {"type": "object", "properties": {"foo": {"type": old_type, "nullable": True}}}
    new_schema = convert_openapi_nullable(schema)

    assert "nullable" not in new_schema["properties"]["foo"]
    assert new_schema["properties"]["foo"]["type"] == new_type


def test_metaschema_reference_is_inserted_to_schema(example_schema_dict):
    validated_schema = validate_metaschema(example_schema_dict)
    assert validated_schema["$schema"] in META_SCHEMAS


@pytest.mark.parametrize("metaschema", META_SCHEMAS)
def test_declared_metaschema_is_validated(metaschema, example_schema_dict):
    example_schema_dict["$schema"] = metaschema
    validated_schema = validate_metaschema(example_schema_dict)
    assert validated_schema["$schema"] == metaschema


@pytest.mark.parametrize("metaschema", META_SCHEMAS)
def test_incorrect_schema_raises_exception(metaschema, example_schema_dict):
    example_schema_dict["$schema"] = metaschema
    example_schema_dict["type"] = "definitely-not-a-jeson-schema-type"
    with pytest.raises(IncompatibleSchemaError):
        validate_metaschema(example_schema_dict)
