import json

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
    state: Optional[str] = None
    postcode: Optional[str] = None
"""
    assert address_model_code in formatted


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
