"""Direct unit tests for the value objects and Schema wire-format gymnastics."""

import re

from pydantic import ValidationError
import pytest

from schematalog.domain.schema import (
    MAX_LABELS_PER_SCHEMA,
    NAME_PATTERN,
    QUERY_PATTERN,
    JsonSchemaDocument,
    Schema,
    SchemaDescription,
    SchemaIdentity,
    SchemaLabels,
    SearchQuery,
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


# ---- SchemaLabels ------------------------------------------------------------------


def test_schema_labels_fold_to_lowercase_on_the_way_in():
    labels = SchemaLabels(labels=("Payments", "BILLING"))
    assert list(labels) == ["billing", "payments"]


def test_schema_labels_deduplicate_after_folding():
    """`Payments` and `payments` are one label spelled twice, not two."""
    labels = SchemaLabels(labels=("Payments", "payments", "PAYMENTS"))
    assert list(labels) == ["payments"]


def test_schema_labels_sort_canonically():
    """Sorted on write, so the same set serialises to the same bytes every time."""
    labels = SchemaLabels(labels=("zebra", "apple", "mango"))
    assert list(labels) == ["apple", "mango", "zebra"]


def test_schema_labels_compare_by_value_regardless_of_input_order():
    assert SchemaLabels(labels=("b", "a")) == SchemaLabels(labels=("a", "b"))


def test_schema_labels_reject_a_character_outside_the_name_alphabet():
    with pytest.raises(ValidationError):
        SchemaLabels(labels=("customer data",))


def test_schema_labels_refuse_more_than_the_cap():
    too_many = tuple(f"label-{i}" for i in range(MAX_LABELS_PER_SCHEMA + 1))
    with pytest.raises(ValidationError):
        SchemaLabels(labels=too_many)


def test_schema_labels_count_duplicates_once_against_the_cap():
    """The cap guards what is stored; the same label spelled forty ways stores one."""
    labels = SchemaLabels(labels=tuple(f"LABEL-{i % 3}" for i in range(40)))
    assert len(labels) == 3


def test_schema_labels_accept_a_bare_string_as_one_label():
    assert list(SchemaLabels.model_validate("payments")) == ["payments"]


def test_schema_labels_read_a_string_field_value_as_one_label():
    labels = SchemaLabels(labels="payments")

    assert list(labels) == ["payments"]


@pytest.mark.parametrize("raw", [[1], None, 1])
def test_schema_labels_refuse_input_that_is_not_strings(raw):
    """A malformed stored record fails validation rather than crashing it."""
    with pytest.raises(ValidationError):
        SchemaLabels(labels=raw)


def test_schema_labels_serialise_flat_to_a_list():
    assert SchemaLabels(labels=("b", "a")).model_dump() == ["a", "b"]


def test_schema_labels_cover_a_subset_and_not_a_superset():
    held = SchemaLabels(labels=("billing", "customer"))
    assert held.covers(SchemaLabels(labels=("billing",)))
    assert held.covers(SchemaLabels(labels=()))
    assert not held.covers(SchemaLabels(labels=("billing", "shipping")))


# ---- Schema wire behaviour ---------------------------------------------------------


def _sample_payload() -> dict:
    return {
        "name": "smoke",
        "version": "1",
        "description": "A smoke test schema",
        "schema": {"$schema": "https://example.com/draft", "type": "object"},
        "publication_id": "01a02000-0000-7000-8000-000000000001",
    }


def test_schema_defaults_an_absent_description_to_empty_text():
    payload = {k: v for k, v in _sample_payload().items() if k != "description"}
    assert str(Schema.deserialize(payload).description) == ""


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


def test_schema_defaults_absent_labels_to_an_empty_set():
    """Stores written before labels existed read fine - the missing key defaults."""
    schema = Schema.deserialize(_sample_payload())
    assert list(schema.labels) == []


def test_schema_round_trip_preserves_labels():
    schema = Schema.model_validate({**_sample_payload(), "labels": ["Payments", "billing"]})
    assert schema.serialize()["labels"] == ["billing", "payments"]
    assert list(Schema.deserialize(schema.serialize()).labels) == ["billing", "payments"]


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


@pytest.mark.parametrize(
    "character", [chr(c) for c in range(32, 127)] + ["é", "\x00", "\ud800"]
)
def test_query_pattern_admits_exactly_what_a_name_admits(character):
    """The two patterns must not drift apart.

    A query is matched against names, so any character a name can hold must be
    searchable and any character it cannot must be rejected. They are written
    separately - one has an anchored first character, the other allows surrounding
    whitespace - so nothing but this keeps them in step.
    """
    in_a_name = re.fullmatch(NAME_PATTERN, f"a{character}") is not None
    in_a_query = re.fullmatch(QUERY_PATTERN, character) is not None
    assert in_a_name == in_a_query or character.isspace()


def test_search_query_splits_on_whitespace_into_terms():
    assert SearchQuery(text="billing invoice").terms == ("billing", "invoice")


def test_search_query_normalises_so_equality_agrees_with_matching():
    """Two queries that always return the same rows are the same query.

    Trimming and casefolding on the way in is what makes that true, and it is why a
    query is a value: nothing distinguishes two searches for the same thing.
    """
    assert SearchQuery(text="  Order  ") == SearchQuery(text="order")
    # Repeats and runs of whitespace change nothing about which schemas match.
    assert SearchQuery(text="a  b") == SearchQuery(text="a b") == SearchQuery(text="a b a")


def test_search_query_parse_reads_every_blank_spelling_as_no_query():
    """The absence of a query has one spelling, so a backend checks one thing."""
    for blank in (None, "", "   ", "\t"):
        assert SearchQuery.parse(blank) is None


def test_search_query_parse_builds_a_query_from_real_text():
    parsed = SearchQuery.parse("Billing")
    assert parsed is not None
    assert parsed.text == "billing"


def test_search_query_is_never_empty():
    """`parse` maps blank onto `None`, so an empty query must not be constructible."""
    with pytest.raises(ValidationError):
        SearchQuery(text="")


def test_search_query_does_not_bound_its_own_length():
    """Length is a transport limit, applied where the request is accepted.

    The domain constrains what a query *means* - its alphabet, and that it is never
    empty. How much someone may type is a judgement about requests, not about matching.
    """
    assert SearchQuery(text="x" * 5000).text == "x" * 5000


@pytest.mark.parametrize("query", ["order!", "ordér", "\x00", "\ud800"])
def test_search_query_refuses_what_it_cannot_search_for(query):
    """Rejected rather than answered with an empty result.

    An empty result would read as "nothing found" for what is really "that cannot be
    searched for", and a character no database can bind would otherwise raise on one
    backend and quietly return nothing on another. Non-ASCII is refused because no two
    stores fold its case alike, not because it is meaningless.
    """
    with pytest.raises(ValidationError):
        SearchQuery(text=query)


def test_search_query_matches_a_substring_of_the_name_ignoring_case():
    schema = Schema.model_validate({**_sample_payload(), "name": "Billing"})
    assert SearchQuery(text="illi").matches(schema)
    assert not SearchQuery(text="shipping").matches(schema)
