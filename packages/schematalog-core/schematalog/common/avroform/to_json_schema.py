"""Avro schema -> JSON Schema."""

from typing import Any

from .exceptions import AvroConversionError

JsonSchema = dict[str, Any]

# Avro primitive type -> JSON Schema.
_PRIMITIVES = {
    "string": {"type": "string"},
    "bytes": {"type": "string"},
    "int": {"type": "integer"},
    "long": {"type": "integer"},
    "float": {"type": "number"},
    "double": {"type": "number"},
    "boolean": {"type": "boolean"},
    "null": {"type": "null"},
}

# Avro logicalType -> JSON Schema.
_LOGICAL_TYPES = {
    "date": {"type": "string", "format": "date"},
    "time-millis": {"type": "string", "format": "time"},
    "timestamp-millis": {"type": "string", "format": "date-time"},
    "uuid": {"type": "string", "format": "uuid"},
}


def to_json_schema(avro_schema: Any) -> JsonSchema:
    """Convert an Avro schema into a JSON Schema."""
    return _to_json_schema_type(avro_schema)


def _to_json_schema_type(avro: Any) -> JsonSchema:
    if isinstance(avro, str):
        return _primitive(avro)
    if isinstance(avro, list):
        return _union(avro)
    if isinstance(avro, dict):
        return _named(avro)
    raise AvroConversionError(f"Unexpected Avro schema node: {avro!r}.")


def _primitive(name: str) -> JsonSchema:
    try:
        return dict(_PRIMITIVES[name])
    except KeyError:
        raise AvroConversionError(f"Unknown Avro type: {name!r}.") from None


def _named(avro: dict) -> JsonSchema:
    logical = avro.get("logicalType")
    if logical in _LOGICAL_TYPES:
        return dict(_LOGICAL_TYPES[logical])

    avro_type = avro.get("type")
    if avro_type == "record":
        return _record(avro)
    if avro_type == "enum":
        return {"type": "string", "enum": list(avro["symbols"])}
    if avro_type == "array":
        return {"type": "array", "items": _to_json_schema_type(avro["items"])}
    if avro_type == "map":
        return {"type": "object", "additionalProperties": _to_json_schema_type(avro["values"])}
    if avro_type == "fixed":
        return {"type": "string"}
    if isinstance(avro_type, str):
        return _primitive(avro_type)
    if isinstance(avro_type, (list, dict)):
        return _to_json_schema_type(avro_type)
    raise AvroConversionError(f"Unsupported Avro schema: {avro!r}.")


def _record(avro: dict) -> JsonSchema:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field in avro.get("fields", []):
        field_type = field["type"]
        optional = _is_nullable(field_type) or "default" in field
        prop = _to_json_schema_type(_remove_null_branch(field_type))
        if field.get("doc"):
            prop = {**prop, "description": field["doc"]}
        properties[field["name"]] = prop
        if not optional:
            required.append(field["name"])

    result: JsonSchema = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    if avro.get("name"):
        result["title"] = avro["name"]
    if avro.get("doc"):
        result["description"] = avro["doc"]
    return result


def _union(members: list) -> JsonSchema:
    non_null = [member for member in members if member != "null"]
    nullable = "null" in members
    if len(non_null) == 1:
        schema = _to_json_schema_type(non_null[0])
        return _allow_null(schema) if nullable else schema
    options = [_to_json_schema_type(member) for member in non_null]
    if nullable:
        options.append({"type": "null"})
    return {"anyOf": options}


def _allow_null(schema: JsonSchema) -> JsonSchema:
    if set(schema) == {"type"} and isinstance(schema["type"], str):
        return {"type": [schema["type"], "null"]}
    return {"anyOf": [schema, {"type": "null"}]}


def _is_nullable(field_type: Any) -> bool:
    return isinstance(field_type, list) and "null" in field_type


def _remove_null_branch(field_type: Any) -> Any:
    if not isinstance(field_type, list):
        return field_type
    non_null = [member for member in field_type if member != "null"]
    return non_null[0] if len(non_null) == 1 else non_null
