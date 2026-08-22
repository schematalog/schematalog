import pytest

from schematalog.common.avroform import AvroConversionError, to_avro


def test_primitive_types():
    assert to_avro({"type": "string"}) == "string"
    assert to_avro({"type": "integer"}) == "long"
    assert to_avro({"type": "number"}) == "double"
    assert to_avro({"type": "boolean"}) == "boolean"
    assert to_avro({"type": "null"}) == "null"


@pytest.mark.parametrize(
    "fmt, expected",
    [
        ("date", {"type": "int", "logicalType": "date"}),
        ("time", {"type": "int", "logicalType": "time-millis"}),
        ("date-time", {"type": "long", "logicalType": "timestamp-millis"}),
        ("uuid", {"type": "string", "logicalType": "uuid"}),
    ],
)
def test_string_formats_become_logical_types(fmt, expected):
    assert to_avro({"type": "string", "format": fmt}) == expected


def test_unknown_string_format_is_ignored():
    assert to_avro({"type": "string", "format": "email"}) == "string"


def test_record_with_required_and_optional_fields():
    schema = {
        "type": "object",
        "title": "Point",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        "required": ["x"],
    }
    avro = to_avro(schema)

    assert avro["type"] == "record"
    assert avro["name"] == "Point"
    fields = {field["name"]: field for field in avro["fields"]}
    assert fields["x"]["type"] == "long"  # required -> bare type
    assert "default" not in fields["x"]
    assert fields["y"]["type"] == ["null", "long"]  # optional -> nullable union
    assert fields["y"]["default"] is None


def test_title_and_description_map_to_name_and_doc():
    avro = to_avro({"type": "object", "title": "T", "description": "d", "properties": {}})
    assert avro["name"] == "T"
    assert avro["doc"] == "d"


def test_field_description_becomes_doc():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string", "description": "the a"}},
        "required": ["a"],
    }
    assert to_avro(schema)["fields"][0]["doc"] == "the a"


def test_namespace_is_applied():
    avro = to_avro({"type": "object", "title": "T", "properties": {}}, namespace="ns")
    assert avro["namespace"] == "ns"


def test_nested_object_becomes_nested_record():
    schema = {
        "type": "object",
        "title": "Outer",
        "properties": {
            "inner": {
                "type": "object",
                "title": "Inner",
                "properties": {"n": {"type": "integer"}},
                "required": ["n"],
            }
        },
        "required": ["inner"],
    }
    inner = to_avro(schema)["fields"][0]["type"]
    assert inner["type"] == "record"
    assert inner["name"] == "Inner"


def test_array_of_strings():
    assert to_avro({"type": "array", "items": {"type": "string"}}) == {
        "type": "array",
        "items": "string",
    }


def test_enum_becomes_avro_enum_named_after_the_field():
    assert to_avro({"type": "string", "enum": ["RED", "GREEN"]}, name="color") == {
        "type": "enum",
        "name": "Color",
        "symbols": ["RED", "GREEN"],
    }


def test_enum_with_non_identifier_values_degrades_to_string():
    assert to_avro({"type": "string", "enum": ["a-b", "c d"]}) == "string"


def test_object_with_additional_properties_becomes_map():
    assert to_avro({"type": "object", "additionalProperties": {"type": "integer"}}) == {
        "type": "map",
        "values": "long",
    }


def test_type_list_becomes_union_with_null_first():
    assert to_avro({"type": ["string", "null"]}) == ["null", "string"]


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "#/$defs/X"},  # ref to a $def that does not exist
        {"oneOf": [{"type": "string"}]},
        {"anyOf": [{"type": "string"}]},
        {"allOf": [{"type": "string"}]},
        {},  # missing type
        {"type": "frobnicate"},  # unknown type
    ],
)
def test_unsupported_constructs_raise(schema):
    with pytest.raises(AvroConversionError):
        to_avro(schema)


def test_internal_ref_is_resolved_against_defs():
    schema = {
        "type": "object",
        "$defs": {"country": {"type": "string", "pattern": "^[A-Z]{2}$"}},
        "properties": {"country": {"$ref": "#/$defs/country"}},
        "required": ["country"],
    }
    avro = to_avro(schema)
    assert avro["fields"] == [{"name": "country", "type": "string"}]


def test_ref_to_object_def_becomes_nested_record():
    schema = {
        "type": "object",
        "$defs": {"point": {"type": "object", "properties": {"x": {"type": "integer"}}}},
        "properties": {"origin": {"$ref": "#/$defs/point"}},
        "required": ["origin"],
    }
    origin = to_avro(schema)["fields"][0]["type"]
    assert origin["type"] == "record"
    assert origin["fields"] == [{"name": "x", "type": ["null", "long"], "default": None}]


def test_external_ref_raises():
    with pytest.raises(AvroConversionError, match="external"):
        to_avro({"type": "object", "properties": {"p": {"$ref": "https://x.test/s"}}})


def test_recursive_ref_raises():
    schema = {
        "type": "object",
        "$defs": {"node": {"$ref": "#/$defs/node"}},
        "properties": {"n": {"$ref": "#/$defs/node"}},
    }
    with pytest.raises(AvroConversionError, match="recursive"):
        to_avro(schema)
