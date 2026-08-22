"""A realistic sample schema, published so every test tree draws on the same one.

The conformance suite and both packages' fixtures use this rather than each inventing a
document. It has nesting, arrays and mixed value types on purpose: a trivial
`{"type": "object"}` round-trips through almost any store, so it proves far less than it
appears to - the JSONB case on PostgreSQL is where that showed.
"""

import json
from pathlib import Path
from typing import Any

_SAMPLE = Path(__file__).parent / "example_schema.json"


def example_document() -> dict[str, Any]:
    """A JSON Schema document with structure worth round-tripping. Fresh copy each call."""
    return json.loads(_SAMPLE.read_text())


def example_payload() -> dict[str, Any]:
    """The wire form of a publishable schema, built around `example_document`."""
    return {
        "name": "person-schema",
        "version": "1.2",
        "description": "Schema representing Person.",
        "schema": example_document(),
    }
