import json

import pytest
import yaml

from schematalog.app.presentation.helpers import format as fmt
from schematalog.domain.schema import Schema


def test_schema_is_formatted_as_JSON(example_schema_dict):
    formatted = fmt.to_json(example_schema_dict)

    assert json.loads(formatted) == example_schema_dict


def test_schema_is_formatted_as_YAML(example_schema_dict):
    formatted = fmt.to_yaml(example_schema_dict)

    assert yaml.safe_load(formatted) == example_schema_dict


def test_model_instances_are_serialized(example_schema):
    model = Schema.model_validate(example_schema)
    expected = model.model_dump(mode="json", by_alias=True)

    assert json.loads(fmt.to_json(model)) == expected
    assert yaml.safe_load(fmt.to_yaml(model)) == expected


def test_schema_is_formatted_as_AVRO(example_schema_dict):
    avro_schema = json.loads(fmt.to_avro(example_schema_dict))

    assert avro_schema["type"] == "record"
    assert avro_schema["name"] == example_schema_dict["title"]
    assert avro_schema["doc"] == example_schema_dict["description"]
    assert len(avro_schema["fields"]) == len(example_schema_dict["properties"])


def test_schema_is_formatted_as_Pydantic(example_schema_dict):
    formatted = fmt.to_pydantic(example_schema_dict)

    # the output compiles as Python code
    assert compile(formatted, "<string>", "exec", dont_inherit=True)

    address_model_code = """
class Address(BaseModel):
    street: str
    city: str
    state: str | None = None
    postcode: str | None = None
"""
    assert address_model_code in formatted


def test_pydantic_output_is_written_for_current_python(example_schema_dict):
    formatted = fmt.to_pydantic(example_schema_dict)

    assert "from __future__" not in formatted
    assert "Optional[" not in formatted
    assert "List[" not in formatted


def test_pydantic_output_for_a_schema_that_refers_to_itself_can_be_used():
    """Nothing defers its annotations in the output, so this relies on Python 3.14's doing so."""
    document = {
        "title": "Node",
        "type": "object",
        "properties": {"child": {"$ref": "#"}, "name": {"type": "string"}},
    }
    namespace = {}

    exec(fmt.to_pydantic(document), namespace)  # noqa: S102

    node = namespace["Node"].model_validate({"name": "a", "child": {"name": "b"}})
    assert node.child.name == "b"


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef", "$recursiveRef"])
@pytest.mark.parametrize(
    "wrap",
    [
        lambda ref: ref,
        lambda ref: {"type": "object", "properties": {"a": ref}},
        lambda ref: {"allOf": [ref]},
        lambda ref: {"type": "array", "items": ref},
        lambda ref: {"$defs": {"a": ref}, "$ref": "#/$defs/a"},
    ],
)
def test_pydantic_never_opens_a_file_a_schema_refers_to(tmp_path, keyword, wrap):
    """A schema comes from an anonymous publisher, and the file is on the server."""
    secret = tmp_path / "secret.json"
    secret.write_text('{"type": "object", "properties": {"secret_field": {"type": "string"}}}')

    with pytest.raises(fmt.PydanticGenerationError, match="outside its own document"):
        fmt.to_pydantic(wrap({keyword: str(secret)}))


@pytest.mark.parametrize(
    "reference",
    ["https://example.org/a.json", "other.json#/x", "file:///etc/x.json", " #/spaced"],
)
def test_pydantic_refuses_a_reference_outside_the_document(reference):
    with pytest.raises(fmt.PydanticGenerationError, match="outside its own document"):
        fmt.to_pydantic({"$ref": reference})


def test_pydantic_still_follows_a_reference_inside_the_document():
    document = {
        "title": "Order",
        "type": "object",
        "properties": {"total": {"$ref": "#/$defs/money"}},
        "$defs": {"money": {"type": "number"}},
    }

    assert "total: Money | None = None" in fmt.to_pydantic(document)


def test_pydantic_allows_a_property_named_like_a_reference_keyword():
    document = {"title": "T", "type": "object", "properties": {"$ref": {"type": "string"}}}

    assert "class T(BaseModel)" in fmt.to_pydantic(document)


@pytest.mark.parametrize(
    "document",
    [
        {"title": "1st", "type": "object"},
        {"$ref": "#/$defs/a", "$defs": {"a": {"$ref": "#/$defs/a"}}},
        {
            "$defs": {"com.example.Foo": {"type": "object"}},
            "properties": {"a": {"$ref": "#/$defs/com.example.Foo"}},
        },
    ],
)
def test_pydantic_reports_a_schema_the_generator_cannot_handle(document):
    with pytest.raises(fmt.PydanticGenerationError):
        fmt.to_pydantic(document)


def test_pydantic_drops_canonical_id_and_resolves_refs_locally():
    # A stamped `$id` (absolute URL) plus an internal `$ref` must NOT make the generator
    # fetch the `$id` as a remote base - for our own canonical URL that re-enters and
    # deadlocks the dev server. The ref has to resolve locally instead.
    document = {
        "$id": "http://127.0.0.1:3000/api/schemas/example.address/versions/1.0",
        "title": "Address",
        "type": "object",
        "$defs": {"country_code": {"type": "string", "pattern": "^[A-Z]{2}$"}},
        "properties": {"country": {"$ref": "#/$defs/country_code"}},
        "$schema": "https://json-schema.org/draft/2020-12/schema",
    }
    formatted = fmt.to_pydantic(document)

    assert compile(formatted, "<string>", "exec", dont_inherit=True)
    assert "CountryCode" in formatted  # the internal $defs ref resolved locally


def test_highlight_wraps_each_line_for_css_numbering():
    """Line numbers are CSS counters over these spans, not markup - see `highlight`."""
    html = fmt.highlight('{\n  "a": 1\n}', "json", "json")
    assert 'class="hl"' in html
    assert 'id="json-line-1"' in html
    assert 'id="json-line-3"' in html


def test_highlight_anchors_keep_line_ids_unique_across_blocks():
    """Four format tabs render on one page; duplicate element ids would be invalid."""
    json_html = fmt.highlight("{}", "json", "json")
    avro_html = fmt.highlight("{}", "json", "avro")
    assert 'id="json-line-1"' in json_html
    assert 'id="avro-line-1"' in avro_html


def test_highlight_escapes_the_code_it_wraps():
    """The result is rendered unescaped, so Pygments must do the escaping itself."""
    html = fmt.highlight('{"x": "<script>alert(1)</script>"}', "json", "json")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_highlight_tolerates_the_avro_fallback_comment():
    """A failed Avro conversion yields a `#` note, which is not valid JSON."""
    assert fmt.highlight("# cannot be represented as Avro", "json", "avro")


def test_highlight_splits_multiline_tokens_across_line_spans():
    """A Python docstring is one token spanning lines; each line still needs its span."""
    html = fmt.highlight('x = """one\ntwo"""\n', "python", "py")
    assert 'id="py-line-1"' in html
    assert 'id="py-line-2"' in html
