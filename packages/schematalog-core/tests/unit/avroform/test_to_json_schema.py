import pytest

from schematalog.common.avroform import AvroConversionError, to_json_schema


@pytest.mark.parametrize(
    "avro, expected",
    [
        ("string", {"type": "string"}),
        ("bytes", {"type": "string"}),
        ("int", {"type": "integer"}),
        ("long", {"type": "integer"}),
        ("float", {"type": "number"}),
        ("double", {"type": "number"}),
        ("boolean", {"type": "boolean"}),
        ("null", {"type": "null"}),
    ],
)
def test_primitive_types(avro, expected):
    assert to_json_schema(avro) == expected


@pytest.mark.parametrize(
    "avro, expected",
    [
        ({"type": "int", "logicalType": "date"}, {"type": "string", "format": "date"}),
        ({"type": "int", "logicalType": "time-millis"}, {"type": "string", "format": "time"}),
        (
            {"type": "long", "logicalType": "timestamp-millis"},
            {"type": "string", "format": "date-time"},
        ),
        ({"type": "string", "logicalType": "uuid"}, {"type": "string", "format": "uuid"}),
    ],
)
def test_logical_types(avro, expected):
    assert to_json_schema(avro) == expected


def test_record_becomes_object_with_required():
    avro = {
        "type": "record",
        "name": "Point",
        "doc": "a point",
        "fields": [
            {"name": "x", "type": "long"},
            {"name": "y", "type": ["null", "long"], "default": None},
        ],
    }
    assert to_json_schema(avro) == {
        "type": "object",
        "title": "Point",
        "description": "a point",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        "required": ["x"],
    }


def test_field_doc_becomes_description():
    avro = {
        "type": "record",
        "name": "R",
        "fields": [{"name": "a", "type": "string", "doc": "d"}],
    }
    assert to_json_schema(avro)["properties"]["a"] == {"type": "string", "description": "d"}


def test_enum_becomes_string_enum():
    avro = {"type": "enum", "name": "Color", "symbols": ["RED", "GREEN"]}
    assert to_json_schema(avro) == {"type": "string", "enum": ["RED", "GREEN"]}


def test_array():
    assert to_json_schema({"type": "array", "items": "string"}) == {
        "type": "array",
        "items": {"type": "string"},
    }


def test_map_becomes_additional_properties():
    assert to_json_schema({"type": "map", "values": "long"}) == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }


def test_union_without_null_becomes_anyof():
    assert to_json_schema(["string", "long"]) == {
        "anyOf": [{"type": "string"}, {"type": "integer"}]
    }


def test_unknown_type_raises():
    with pytest.raises(AvroConversionError):
        to_json_schema("frobnicate")
