"""JSON Schema -> Avro schema."""

import re
from typing import Any

from .exceptions import AvroConversionError

AvroType = str | dict[str, Any] | list[Any]

# JSON Schema primitive `type` -> Avro primitive type.
_PRIMITIVES = {
    "boolean": "boolean",
    "integer": "long",
    "number": "double",
    "null": "null",
}

# JSON Schema string `format` -> (Avro base type, Avro logicalType).
_STRING_FORMATS = {
    "date": ("int", "date"),
    "time": ("int", "time-millis"),
    "date-time": ("long", "timestamp-millis"),
    "uuid": ("string", "uuid"),
}

# JSON Schema keywords we cannot faithfully express in Avro. (`$ref` is handled
# separately: internal pointers are inlined before conversion, see `_resolve_refs`.)
_UNSUPPORTED = ("oneOf", "anyOf", "allOf", "not")


def to_avro(
    json_schema: dict[str, Any], *, name: str = "Record", namespace: str = ""
) -> AvroType:
    """Convert a JSON Schema into an Avro schema.

    Args:
        json_schema: The JSON Schema to convert.
        name: Name for the root Avro record/enum (a schema ``title`` overrides it).
        namespace: Optional Avro namespace for named types.

    Returns:
        The Avro schema as a JSON-compatible structure.

    Raises:
        AvroConversionError: If the schema uses unsupported constructs.
    """
    return _convert(_resolve_refs(json_schema, json_schema, ()), name, namespace, set())


def _resolve_refs(schema: Any, root: dict, stack: tuple[str, ...]) -> Any:
    """Inline internal ``$ref`` pointers (``#/...``) against the document root.

    Avro has no reference mechanism, so a fragment ref is expanded in place before
    conversion - e.g. ``{"$ref": "#/$defs/country"}`` becomes the ``country`` subschema.
    External refs (anything not ``#/...``) and cyclic refs cannot be expressed and raise.
    """
    if isinstance(schema, list):
        return [_resolve_refs(item, root, stack) for item in schema]
    if not isinstance(schema, dict):
        return schema
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return _resolve_ref(schema, ref, root, stack)
    return {key: _resolve_refs(value, root, stack) for key, value in schema.items()}


def _resolve_ref(schema: dict, ref: str, root: dict, stack: tuple[str, ...]) -> Any:
    """Expand a single ``$ref`` node, overlaying any sibling keys onto the target."""
    if not ref.startswith("#/"):
        raise AvroConversionError(f"Cannot resolve external $ref: {ref!r}.")
    if ref in stack:
        raise AvroConversionError(f"Cannot express recursive $ref in Avro: {ref!r}.")
    target = _resolve_refs(_deref(ref, root), root, (*stack, ref))
    # JSON Schema allows keys beside `$ref`; overlay them onto the resolved object.
    siblings = {key: value for key, value in schema.items() if key != "$ref"}
    if siblings and isinstance(target, dict):
        return {**target, **_resolve_refs(siblings, root, stack)}
    return target


def _deref(ref: str, root: dict) -> Any:
    """Resolve a ``#/a/b`` JSON Pointer against ``root`` (with ~0/~1 unescaping)."""
    node: Any = root
    for raw in ref[2:].split("/"):  # drop the leading '#/'
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or token not in node:
            raise AvroConversionError(f"Cannot resolve $ref: {ref!r}.")
        node = node[token]
    return node


def _convert(schema: Any, name: str, namespace: str, seen: set[str]) -> AvroType:
    if not isinstance(schema, dict):
        raise AvroConversionError(f"Expected a schema object, got {type(schema).__name__}.")
    for keyword in _UNSUPPORTED:
        if keyword in schema:
            raise AvroConversionError(f"Unsupported JSON Schema keyword: {keyword!r}.")

    if "enum" in schema:
        return _enum(schema, name, namespace, seen)

    json_type = schema.get("type")
    if isinstance(json_type, list):
        return _union(json_type, schema, name, namespace, seen)
    if json_type == "object":
        return _object(schema, name, namespace, seen)
    if json_type == "array":
        return _array(schema, name, namespace, seen)
    if json_type == "string":
        return _string(schema)
    if json_type in _PRIMITIVES:
        return _PRIMITIVES[json_type]
    raise AvroConversionError(f"Unsupported or missing JSON Schema type: {json_type!r}.")


def _object(schema: dict, name: str, namespace: str, seen: set[str]) -> AvroType:
    additional = schema.get("additionalProperties")
    if not schema.get("properties") and isinstance(additional, dict):
        return {"type": "map", "values": _convert(additional, name, namespace, seen)}

    record_name = _unique(_pascal(schema.get("title") or name), seen)
    required = set(schema.get("required", []))
    fields = []
    for prop_name, prop_schema in schema.get("properties", {}).items():
        field_type = _convert(prop_schema, prop_name, namespace, seen)
        field: dict[str, Any] = {"name": prop_name, "type": field_type}
        if isinstance(prop_schema, dict) and prop_schema.get("description"):
            field["doc"] = prop_schema["description"]
        if prop_name not in required:
            field["type"] = _nullable(field_type)
            field["default"] = None
        fields.append(field)

    record: dict[str, Any] = {"type": "record", "name": record_name, "fields": fields}
    if namespace:
        record["namespace"] = namespace
    if schema.get("description"):
        record["doc"] = schema["description"]
    return record


def _array(schema: dict, name: str, namespace: str, seen: set[str]) -> AvroType:
    items = schema.get("items")
    if not isinstance(items, dict):
        raise AvroConversionError("Array schema must declare an 'items' object.")
    return {"type": "array", "items": _convert(items, f"{_pascal(name)}Item", namespace, seen)}


def _string(schema: dict) -> AvroType:
    fmt = schema.get("format")
    if isinstance(fmt, str) and fmt in _STRING_FORMATS:
        base, logical = _STRING_FORMATS[fmt]
        return {"type": base, "logicalType": logical}
    return "string"


def _enum(schema: dict, name: str, namespace: str, seen: set[str]) -> AvroType:
    symbols = schema["enum"]
    valid = all(isinstance(s, str) and _is_avro_name(s) for s in symbols)
    if valid and len(set(symbols)) == len(symbols):
        enum: dict[str, Any] = {
            "type": "enum",
            "name": _unique(_pascal(name), seen),
            "symbols": list(symbols),
        }
        if namespace:
            enum["namespace"] = namespace
        return enum
    # Enums Avro can't represent (non-string or non-identifier values) degrade to string.
    return "string"


def _union(types: list, schema: dict, name: str, namespace: str, seen: set[str]) -> AvroType:
    base = {key: value for key, value in schema.items() if key not in ("type", "enum")}
    parts: list[AvroType] = []
    for json_type in types:
        member = _convert({**base, "type": json_type}, name, namespace, seen)
        if member not in parts:
            parts.append(member)
    # Avro convention: null first so a `null` default is valid.
    if "null" in parts:
        parts = ["null", *(part for part in parts if part != "null")]
    return parts


def _nullable(avro_type: AvroType) -> AvroType:
    if isinstance(avro_type, list):
        return avro_type if "null" in avro_type else ["null", *avro_type]
    return ["null", avro_type]


def _pascal(value: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", value)
    name = "".join(part[:1].upper() + part[1:] for part in parts if part)
    return name or "Record"


def _unique(name: str, seen: set[str]) -> str:
    candidate, index = name, 1
    while candidate in seen:
        index += 1
        candidate = f"{name}{index}"
    seen.add(candidate)
    return candidate


def _is_avro_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value))
