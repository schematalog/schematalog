"""Render a JSON Schema property's type as human-readable HTML for the detail table.

Presentation-only: this turns the shapes that appear in a stored document into the
short label the schema detail page shows in its property table. It is exposed to the
Jinja templates (via the `schemas_detail` context), which is why it is public.
"""

from markupsafe import Markup, escape

_COMBINATORS = ("oneOf", "anyOf", "allOf")
_FORMAT_LABELS = {
    "uuid": "UUID",
    "date": "ISO 8601 Date",
    "date-time": "ISO 8601 Timestamp",
}


def _render_ref_name(ref: str) -> Markup:
    """The trailing name of a `$ref` pointer (`#/$defs/Address` -> `Address`).

    "ref" rather than "reference" throughout: `$ref` is JSON Schema's own keyword.
    """
    return escape(str(ref).rstrip("/").rsplit("/", 1)[-1] or ref)


def _render_array_type(schema_property: dict) -> Markup:
    """Render an `array` property, recursing into `items` to name the element type."""
    items = schema_property.get("items")
    if isinstance(items, dict):
        return Markup("List of {}").format(render_property_type(items))
    if isinstance(items, list):  # tuple/positional validation: a schema per position
        return Markup("List of ({})").format(
            Markup(", ").join(render_property_type(item) for item in items)
        )
    return Markup("List")


def _render_typed_property(schema_property: dict, property_type: str | list[str]) -> Markup:
    """Render a property that declares a `type` (a string, or a list for a union)."""
    if property_type == "array":
        return _render_array_type(schema_property)
    if isinstance(property_type, list):
        return Markup(", ").join(escape(str(member).title()) for member in property_type)
    label = _FORMAT_LABELS.get(str(schema_property.get("format", "")).lower())
    return escape(label if label is not None else str(property_type).title())


def render_property_type(schema_property: dict) -> Markup:
    """Render a JSON Schema property's type as HTML for the detail table.

    Covers the shapes that turn up in stored schemas: primitives and their string
    `format`s, type unions (`["string", "null"]`), arrays (recursing into `items`),
    `$ref`s, enums and `oneOf`/`anyOf`/`allOf` combinators. Falls back to `"Any"`
    for an otherwise-untyped property rather than raising, so the page renders for
    any valid schema.

    Args:
        schema_property: A single JSON Schema property subschema.

    Returns:
        `Markup` - the only markup is the `<code>` wrapper this adds; **every**
        substring taken from the schema is escaped here. The escaping is deliberately
        self-contained rather than leaning on `preprocess_schema` having constrained
        `type` to the metaschema's enum: this is the one place the templates render
        unescaped, so it must not depend on validation happening elsewhere.
    """
    if "pattern" in schema_property:
        return Markup("pattern <code>{}</code>").format(schema_property["pattern"])
    if "$ref" in schema_property:
        return _render_ref_name(schema_property["$ref"])
    combinator = next((c for c in _COMBINATORS if c in schema_property), None)
    if combinator:
        members = Markup(", ").join(
            render_property_type(member) for member in schema_property[combinator]
        )
        return members or escape(combinator)
    property_type = schema_property.get("type")
    if property_type is None:
        return Markup("Enum") if "enum" in schema_property else Markup("Any")
    return _render_typed_property(schema_property, property_type)
