"""Populate the configured storage with sample schemas - a dev/local fixture loader.

Idempotent - schemas that already exist are skipped, so it is safe to re-run.
Targets whatever backend `.env` / `Settings` points at (SQLite by default, or the
compose Postgres). Publishing goes through `SchemaService`, so the samples are
metaschema-validated exactly like real input. Kept
out of the operator CLI (`schematalog.app.presentation.cli`) as it loads dev fixtures, not
a production operation.

    just seed
    # or: uv run python -m scripts.seed
"""

import asyncio
from typing import Any

from schematalog.app.application.exceptions import DuplicateSchemaError
from schematalog.app.application.schema import (
    MetadataUpdateCommand,
    PublishCommand,
    SchemaService,
)
from schematalog.app.wiring.config import settings
from schematalog.app.wiring.storage import build_schema_repository
from schematalog.domain.schema import SchemaIdentity, SuccessorReference

# (name, version, document).
SAMPLE_SCHEMAS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "example.user",
        "1.0",
        {
            "type": "object",
            "required": ["id", "email"],
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "email": {"type": "string", "description": "Primary contact email."},
                "name": {"type": "string"},
            },
        },
    ),
    (
        "example.order",
        "1.0",
        {
            "type": "object",
            "required": ["order_id", "total"],
            "properties": {
                "order_id": {"type": "string", "format": "uuid"},
                "total": {"type": "number", "minimum": 0},
                "created_at": {"type": "string", "format": "date-time"},
            },
        },
    ),
    (
        "example.order",
        "1.1",
        {
            "type": "object",
            "required": ["order_id", "total"],
            "properties": {
                "order_id": {"type": "string", "format": "uuid"},
                "total": {"type": "number", "minimum": 0},
                "currency": {"type": "string", "description": "ISO 4217 currency code."},
                "created_at": {"type": "string", "format": "date-time"},
            },
        },
    ),
    (
        "example.order",
        "2.0",
        {
            "type": "object",
            "required": ["order_id", "total", "currency"],
            "properties": {
                "order_id": {"type": "string", "format": "uuid"},
                "total": {"type": "number", "minimum": 0},
                "currency": {"type": "string", "description": "ISO 4217 currency code."},
                "lines": {"type": "array", "items": {"type": "object"}},
                "created_at": {"type": "string", "format": "date-time"},
            },
        },
    ),
    (
        "example.product",
        "1.0",
        {
            "type": "object",
            "required": ["sku"],
            "properties": {
                "sku": {"type": "string"},
                "price": {"type": "number", "minimum": 0},
                "in_stock": {"type": "boolean", "default": True},
            },
        },
    ),
    # Showcase varied field types: enum, string formats, integer, array, nested object.
    (
        "example.event",
        "1.0",
        {
            "type": "object",
            "required": ["id", "type", "occurred_at"],
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "type": {
                    "type": "string",
                    "enum": ["created", "updated", "deleted"],
                    "description": "The kind of event.",
                },
                "occurred_at": {"type": "string", "format": "date-time"},
                "priority": {"type": "integer", "minimum": 0, "maximum": 9},
                "tags": {"type": "array", "items": {"type": "string"}},
                "actor": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "name": {"type": "string"},
                    },
                },
            },
        },
    ),
    # Showcase a $ref into $defs, a nullable union, and a regex pattern.
    (
        "example.address",
        "1.0",
        {
            "type": "object",
            "$defs": {"country_code": {"type": "string", "pattern": "^[A-Z]{2}$"}},
            "required": ["street", "city", "country"],
            "properties": {
                "street": {"type": "string"},
                "city": {"type": "string"},
                "postcode": {"type": ["string", "null"]},
                "country": {"$ref": "#/$defs/country_code"},
                "kind": {"type": "string", "enum": ["billing", "shipping"]},
            },
        },
    ),
    # Showcase a oneOf combinator and an array of objects.
    (
        "example.payment",
        "1.0",
        {
            "type": "object",
            "required": ["amount", "method"],
            "properties": {
                "amount": {"type": "number", "minimum": 0},
                "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
                "method": {
                    "oneOf": [
                        {"type": "string", "enum": ["card", "cash"]},
                        {"type": "object", "properties": {"wallet": {"type": "string"}}},
                    ]
                },
                "refunded": {"type": "boolean", "default": False},
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"sku": {"type": "string"}},
                    },
                },
            },
        },
    ),
]

# Local canonical-URL base for *internal* successor references in the seed - the host
# the dev server is browsed on (`just serve` listens on :3000). The "Superseded by" link
# renders whatever URL is stored regardless; the derived "Supersedes" predecessor link
# only resolves when the app is browsed via this same base (else the canonical URLs differ).
LOCAL_BASE = "http://localhost:3000"


def _local_url(name: str, version: str) -> str:
    return f"{LOCAL_BASE}/api/schemas/{name}/versions/{version}"


# Mutable lifecycle metadata applied *after* publishing, to exercise the new fields.
# Each row: schema name, version, the deprecated flag, the successor URL, and the internal
# successor target to existence-check - or a None target for an external successor URL.
SAMPLE_METADATA: list[tuple[str, str, bool, str | None, SchemaIdentity | None]] = [
    # example.order 1.1 is deprecated, superseded by 2.0 (an internal reference).
    (
        "example.order",
        "1.1",
        True,
        _local_url("example.order", "2.0"),
        SchemaIdentity(name="example.order", version="2.0"),
    ),
    # example.product 1.0 is deprecated, superseded by a schema in an external registry.
    ("example.product", "1.0", True, "https://schemas.example.com/product/v2.json", None),
]


async def _publish_samples(service: SchemaService) -> tuple[int, int]:
    """Publish each sample schema, skipping duplicates; return (created, skipped) counts."""
    created = skipped = 0
    for name, version, document in SAMPLE_SCHEMAS:
        try:
            await service.publish_schema(
                PublishCommand(name=name, version=version, json_schema=document)
            )
        except DuplicateSchemaError:
            skipped += 1
            print(f"  skip  {name} {version} (already present)")
            continue
        created += 1
        print(f"  add   {name} {version}")
    return created, skipped


async def _apply_metadata(service: SchemaService) -> None:
    """Apply the deprecated/successor metadata to the relevant samples (idempotent)."""
    for name, version, deprecated, successor_url, target in SAMPLE_METADATA:
        args: dict[str, Any] = {"name": name, "version": version, "deprecated": deprecated}
        if successor_url is not None:
            args["successor"] = SuccessorReference(url=successor_url)
            if target is not None:
                args["successor_target"] = target
        await service.update_schema_metadata(MetadataUpdateCommand(**args))
        print(f"  meta  {name} {version} (deprecated={deprecated}, successor={successor_url})")


async def seed() -> None:
    """Publish every sample schema into the configured storage, then stamp lifecycle metadata."""
    repo = build_schema_repository(settings.STORAGE_URL)
    service = SchemaService(repo)
    try:
        created, skipped = await _publish_samples(service)
        await _apply_metadata(service)
    finally:
        # The SQLAlchemy backend holds an engine; release its connections cleanly.
        engine = getattr(repo, "engine", None)
        if engine is not None:
            await engine.dispose()
    print(f"Seeded {created} schema version(s); {skipped} already present.")


if __name__ == "__main__":
    asyncio.run(seed())
