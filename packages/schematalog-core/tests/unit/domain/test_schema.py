"""Direct unit tests for the value objects and Schema wire-format gymnastics."""

from pydantic import ValidationError
import pytest

from schematalog.domain.schema import (
    JsonSchemaDocument,
    Schema,
    SchemaDescription,
    SchemaIdentity,
    SuccessorReference,
    ValueObject,
)

# ---- ValueObject + SchemaIdentity --------------------------------------------------


def test_value_object_subclasses_are_frozen():
    identity = SchemaIdentity(name="foo", version="1.0")
    with pytest.raises(ValidationError):
        identity.name = "bar"  # ty: ignore[possibly-unbound-attribute]


def test_schema_identity_is_hashable_and_compares_by_value():
    a = SchemaIdentity(name="foo", version="1.0")
    b = SchemaIdentity(name="foo", version="1.0")
    c = SchemaIdentity(name="foo", version="1.1")
    assert a == b
    assert a != c
    assert {a, b, c} == {a, c}  # b folds into a


def test_schema_identity_rejects_invalid_name():
    with pytest.raises(ValidationError):
        SchemaIdentity(name="has spaces", version="1.0")


def test_value_object_base_is_a_frozen_basemodel():
    # Smoke: a bare ValueObject subclass with no fields is constructible and frozen.
    class Empty(ValueObject):
        pass

    instance = Empty()
    assert Empty.model_config["frozen"] is True
    with pytest.raises(ValidationError):
        instance.some_attr = 1  # ty: ignore[unresolved-attribute]


# ---- SchemaDescription -------------------------------------------------------------


def test_schema_description_accepts_raw_string():
    desc = SchemaDescription.model_validate("hello")
    assert desc.text == "hello"


def test_schema_description_accepts_nested_dict():
    desc = SchemaDescription.model_validate({"text": "hello"})
    assert desc.text == "hello"


def test_schema_description_str_returns_text():
    desc = SchemaDescription(text="hello")
    assert str(desc) == "hello"


def test_schema_description_serializes_flat_to_string():
    desc = SchemaDescription(text="hello")
    assert desc.model_dump() == "hello"


def test_schema_description_rejects_oversize_text():
    with pytest.raises(ValidationError):
        SchemaDescription(text="x" * 65537)


# ---- JsonSchemaDocument ------------------------------------------------------------


def test_json_schema_document_exposes_metaschema():
    doc = JsonSchemaDocument(
        document={"$schema": "https://example.com/draft", "type": "object"}
    )
    assert doc.metaschema == "https://example.com/draft"


def test_json_schema_document_metaschema_defaults_to_empty_string():
    doc = JsonSchemaDocument(document={"type": "object"})
    assert doc.metaschema == ""


def test_json_schema_document_exposes_schema_id_when_present():
    doc = JsonSchemaDocument(document={"$id": "https://example.com/foo", "type": "object"})
    assert doc.schema_id == "https://example.com/foo"


def test_json_schema_document_schema_id_defaults_to_none():
    doc = JsonSchemaDocument(document={"type": "object"})
    assert doc.schema_id is None


def test_json_schema_document_serializes_flat_to_dict():
    payload = {"$schema": "https://example.com/draft", "type": "object"}
    doc = JsonSchemaDocument(document=payload)
    assert doc.model_dump() == payload


# ---- Schema wire behaviour ---------------------------------------------------------


def _sample_payload() -> dict:
    return {
        "name": "smoke",
        "version": "1",
        "description": "A smoke test schema",
        "schema": {"$schema": "https://example.com/draft", "type": "object"},
        "publication_id": "01a02000-0000-7000-8000-000000000001",
    }


def test_schema_accepts_legacy_flat_wire_input():
    schema = Schema.model_validate(_sample_payload())
    assert schema.identity == SchemaIdentity(name="smoke", version="1")
    assert isinstance(schema.description, SchemaDescription)
    assert str(schema.description) == "A smoke test schema"
    assert isinstance(schema.json_schema, JsonSchemaDocument)
    assert schema.json_schema.metaschema == "https://example.com/draft"


def test_schema_accepts_nested_identity_input():
    payload = _sample_payload()
    payload["identity"] = {
        "name": payload.pop("name"),
        "version": payload.pop("version"),
    }
    schema = Schema.model_validate(payload)
    assert schema.name == "smoke"
    assert schema.version == "1"


def test_schema_accepts_json_schema_document_instance():
    doc = JsonSchemaDocument(document={"type": "object"})
    schema = Schema(
        identity=SchemaIdentity(name="x", version="1"),
        json_schema=doc,
    )
    assert schema.json_schema is doc


def test_schema_computed_fields_delegate_to_identity():
    schema = Schema.model_validate(_sample_payload())
    assert schema.name == schema.identity.name == "smoke"
    assert schema.version == schema.identity.version == "1"


def test_schema_serialises_to_flat_wire_form():
    schema = Schema.model_validate(_sample_payload())
    wire = schema.serialize()
    assert wire["name"] == "smoke"
    assert wire["version"] == "1"
    assert wire["description"] == "A smoke test schema"
    assert wire["schema"] == {"$schema": "https://example.com/draft", "type": "object"}
    assert "identity" not in wire


def test_schema_round_trip_through_dict_preserves_data():
    schema = Schema.model_validate(_sample_payload())
    redeserialized = Schema.deserialize(schema.serialize())
    assert redeserialized.identity == schema.identity
    assert str(redeserialized.description) == str(schema.description)
    assert redeserialized.json_schema.document == schema.json_schema.document
    assert redeserialized.publication_id == schema.publication_id
    assert redeserialized.published_on == schema.published_on


def test_schema_deserialise_accepts_json_string():
    import json

    payload = _sample_payload()
    schema = Schema.deserialize(json.dumps(payload))
    assert schema.identity.name == "smoke"


def test_schema_round_trip_preserves_deprecated():
    schema = Schema.model_validate({**_sample_payload(), "deprecated": True})
    assert schema.serialize()["deprecated"] is True
    assert Schema.deserialize(schema.serialize()).deprecated is True


def test_schema_deserialise_defaults_deprecated_to_false_when_absent():
    # Legacy stored forms predate the field; they must load without it.
    schema = Schema.model_validate(_sample_payload())
    assert schema.deprecated is False


def test_with_metadata_sets_and_reverses_deprecated():
    schema = Schema.model_validate(_sample_payload())
    deprecated = schema.with_metadata(deprecated=True)
    assert deprecated.deprecated is True
    assert deprecated.with_metadata(deprecated=False).deprecated is False


def test_with_metadata_leaves_unset_fields_untouched():
    schema = Schema.model_validate({**_sample_payload(), "deprecated": True})
    updated = schema.with_metadata(deprecated=True)
    assert updated.deprecated is True
    assert updated.deprecated is True  # unchanged


_SUCCESSOR_URL = "https://example.com/api/schemas/other/versions/2"


def test_successor_reference_wraps_raw_string_and_serialises_flat():
    ref = SuccessorReference.model_validate(_SUCCESSOR_URL)
    assert str(ref) == _SUCCESSOR_URL
    assert ref.model_dump() == _SUCCESSOR_URL


def test_successor_reference_rejects_relative_uri():
    with pytest.raises(ValidationError):
        SuccessorReference(url="/not/absolute")


def test_schema_round_trip_preserves_successor():
    schema = Schema.model_validate({**_sample_payload(), "successor": _SUCCESSOR_URL})
    assert schema.serialize()["successor"] == _SUCCESSOR_URL
    assert str(Schema.deserialize(schema.serialize()).successor) == _SUCCESSOR_URL


def test_schema_defaults_successor_to_none_when_absent():
    schema = Schema.model_validate(_sample_payload())
    assert schema.successor is None


def test_with_metadata_sets_clears_and_leaves_successor():
    schema = Schema.model_validate(_sample_payload())
    ref = SuccessorReference(url=_SUCCESSOR_URL)
    with_succ = schema.with_metadata(successor=ref)
    assert with_succ.successor == ref
    assert with_succ.with_metadata(successor=None).successor is None  # explicit clear
    assert with_succ.with_metadata(deprecated=True).successor == ref  # UNSET leaves it
