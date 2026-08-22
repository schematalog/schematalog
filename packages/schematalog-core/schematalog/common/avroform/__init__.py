"""Convert between JSON Schema and Apache Avro schemas.

A small, dependency-free converter covering the common subset of JSON Schema:
objects/records, primitives, arrays, enums, nullable fields (unions), nested
records, string formats that map to Avro logical types, and internal ``$ref``
pointers (``#/$defs/...``, inlined before conversion). Constructs with no clean Avro
equivalent (``oneOf``/``anyOf``/``allOf``, external or recursive ``$ref``) raise
:class:`AvroConversionError` rather than emitting an invalid schema.
"""

from .exceptions import AvroConversionError
from .to_avro import to_avro
from .to_json_schema import to_json_schema

__all__ = ["AvroConversionError", "to_avro", "to_json_schema"]
