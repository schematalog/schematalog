from markupsafe import Markup
import pytest

from schematalog.app.presentation.helpers.property_type import render_property_type


@pytest.mark.parametrize(
    ("prop", "expected"),
    (
        ({"type": "string"}, "String"),
        ({"type": "integer"}, "Integer"),
        ({"type": "boolean"}, "Boolean"),
        ({"type": "object"}, "Object"),
        ({"type": ["string", "null"]}, "String, Null"),
        ({"type": "string", "format": "uuid"}, "UUID"),
        ({"type": "string", "format": "date"}, "ISO 8601 Date"),
        ({"type": "string", "format": "date-time"}, "ISO 8601 Timestamp"),
        ({"type": "string", "format": "email"}, "String"),  # unknown format → bare type
        ({"type": "string", "pattern": "^a$"}, "pattern <code>^a$</code>"),
    ),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_scalar_types(prop, expected):
    assert render_property_type(prop) == expected


@pytest.mark.parametrize(
    ("prop", "expected"),
    (
        ({"type": "array", "items": {"type": "string"}}, "List of String"),
        ({"type": "array", "items": {"type": "object"}}, "List of Object"),
        (  # nested arrays recurse
            {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "List of List of Integer",
        ),
        ({"type": "array"}, "List"),  # items omitted
        (  # tuple/positional validation: one schema per position
            {"type": "array", "items": [{"type": "string"}, {"type": "integer"}]},
            "List of (String, Integer)",
        ),
    ),
)
def test_array_types(prop, expected):
    assert render_property_type(prop) == expected


@pytest.mark.parametrize(
    ("prop", "expected"),
    (
        ({"$ref": "#/$defs/Address"}, "Address"),
        ({"$ref": "https://example.com/schemas/Person"}, "Person"),
        ({"enum": ["a", "b"]}, "Enum"),  # enum without a declared type
        ({"oneOf": [{"type": "string"}, {"type": "integer"}]}, "String, Integer"),
        ({"anyOf": [{"type": "boolean"}]}, "Boolean"),
        ({}, "Any"),  # nothing declared — must not raise
    ),
)
def test_untyped_shapes_do_not_crash(prop, expected):
    assert render_property_type(prop) == expected


@pytest.mark.parametrize(
    ("prop", "expected"),
    (
        ({"type": "string", "pattern": "<script>"}, "pattern <code>&lt;script&gt;</code>"),
        ({"$ref": "#/$defs/<b>evil"}, "&lt;b&gt;evil"),
    ),
)
def test_author_controlled_values_are_escaped(prop, expected):
    assert render_property_type(prop) == expected


def test_hostile_substrings_are_escaped_without_relying_on_validation():
    """`prop_type` output is rendered unescaped, so it must escape everything itself.

    These shapes cannot reach storage today (`normalise_for_publication` constrains `type` to
    the metaschema's enum), which is exactly why this is pinned here: the guarantee
    must not quietly become dependent on validation happening somewhere else.
    """
    payload = "<script>alert(1)</script>"
    for prop in (
        {"type": payload},
        {"type": [payload, "null"]},
        {"pattern": payload},
        {"$ref": f"#/$defs/{payload}"},
        {"type": "array", "items": {"type": payload}},
        {"oneOf": [{"type": payload}]},
    ):
        rendered = str(render_property_type(prop))
        # The security property: no executable tag survives, however it was mangled.
        assert "<script" not in rendered.lower(), prop
        # And the payload was escaped rather than silently dropped. Deliberately loose:
        # the `type` branches title-case their input, and `$ref` keeps only the segment
        # after the last "/", so neither the casing nor both brackets are guaranteed.
        assert "&lt;" in rendered or "&gt;" in rendered, prop


def test_markup_is_returned_so_the_template_need_not_use_safe():
    assert isinstance(render_property_type({"type": "string"}), Markup)
