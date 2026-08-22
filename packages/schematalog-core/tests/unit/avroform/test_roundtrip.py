"""Bidirectional conversion tests."""

from schematalog.common.avroform import to_avro, to_json_schema
from schematalog.testing import example_document

EXAMPLE_SCHEMA = example_document()

# A JSON Schema using only the round-trippable subset: a titled object, primitives,
# string formats, an array, an enum, a titled nested object, and one optional field.
CURATED_JSON_SCHEMA = {
    "type": "object",
    "title": "Order",
    "description": "An order.",
    "properties": {
        "id": {"type": "string"},
        "quantity": {"type": "integer"},
        "price": {"type": "number"},
        "paid": {"type": "boolean"},
        "created": {"type": "string", "format": "date-time"},
        "ref": {"type": "string", "format": "uuid"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": ["NEW", "SHIPPED"]},
        "customer": {
            "type": "object",
            "title": "Customer",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "note": {"type": "string"},
    },
    "required": [
        "id",
        "quantity",
        "price",
        "paid",
        "created",
        "ref",
        "tags",
        "status",
        "customer",
    ],
}

CURATED_AVRO = {
    "type": "record",
    "name": "Order",
    "doc": "An order.",
    "fields": [
        {"name": "id", "type": "string"},
        {
            "name": "customer",
            "type": {
                "type": "record",
                "name": "Customer",
                "fields": [{"name": "name", "type": "string"}],
            },
        },
        {"name": "note", "type": ["null", "string"], "default": None},
    ],
}


def test_json_schema_to_avro_and_back_is_identity():
    assert to_json_schema(to_avro(CURATED_JSON_SCHEMA)) == CURATED_JSON_SCHEMA


def test_avro_to_json_schema_and_back_is_identity():
    assert to_avro(to_json_schema(CURATED_AVRO)) == CURATED_AVRO


def test_example_schema_round_trip_is_idempotent():
    # Real-world schemas may not be identity (Avro requires names JSON Schema lacks),
    # but a second pass must be stable.
    once = to_json_schema(to_avro(EXAMPLE_SCHEMA))
    twice = to_json_schema(to_avro(once))
    assert once == twice
