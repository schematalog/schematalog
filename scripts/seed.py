"""Populate the configured storage with sample schemas, locally or on a demo instance.

Idempotent for one base URL - schemas that already exist are skipped and their labels
and lifecycle metadata set again, so it is safe to re-run with the same one. A different
one rewrites the internal successor, so it matters on a demo instance too, where leaving it
out stores a successor under localhost.
Targets whatever backend `.env` / `Settings` points at (SQLite by default, or the
compose Postgres). Publishing goes through `SchemaService`, so the samples are
metaschema-validated exactly like real input.

    just seed
    just seed --base-url https://schematalog.com
    # or: uv run python -m scripts.seed
"""

import argparse
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

# By name, so every version of a sample carries the same labels.
_SAMPLE_LABELS: dict[str, list[str]] = {
    "example.user": ["customer", "identity"],
    "example.order": ["billing", "commerce"],
    "example.product": ["catalog", "commerce"],
    "example.event": ["analytics"],
    "example.address": ["customer"],
    "example.payment": ["billing", "commerce"],
}

# Where `just serve` is browsed.
_DEFAULT_BASE_URL = "http://localhost:3000"


def _build_sample_metadata(
    base_url: str,
) -> list[tuple[str, str, bool, str | None, SchemaIdentity | None]]:
    """Build the lifecycle metadata to apply after publishing.

    Args:
        base_url: Where the instance is browsed. An internal successor is stored under it,
            and the derived predecessor link only resolves when the instance is browsed
            there, since that is what the canonical URLs are built from.

    Returns:
        A row per version: name, version, the deprecated flag, the successor URL, and the
        internal successor target to existence-check, which is `None` for an external URL.
    """
    root = base_url.rstrip("/")
    return [
        # Deprecated and superseded by a later version of itself.
        (
            "example.order",
            "1.1",
            True,
            f"{root}/api/schemas/example.order/versions/2.0",
            SchemaIdentity(name="example.order", version="2.0"),
        ),
        # Deprecated and superseded by a schema in an external registry.
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


async def _apply_labels(service: SchemaService) -> None:
    """Set each sample's labels, which also reaches versions an earlier run published.

    Args:
        service: The service to apply them through.
    """
    for name, version, _ in SAMPLE_SCHEMAS:
        labels = _SAMPLE_LABELS[name]
        await service.update_schema_metadata(
            MetadataUpdateCommand(name=name, version=version, labels=labels)
        )
        print(f"  label {name} {version} ({', '.join(labels)})")


async def _apply_metadata(service: SchemaService, base_url: str) -> None:
    """Apply the deprecated/successor metadata to the relevant samples (idempotent).

    Args:
        service: The service to apply it through.
        base_url: Where the instance is browsed.
    """
    for name, version, deprecated, successor_url, target in _build_sample_metadata(base_url):
        args: dict[str, Any] = {"name": name, "version": version, "deprecated": deprecated}
        if successor_url is not None:
            args["successor"] = SuccessorReference(url=successor_url)
            if target is not None:
                args["successor_target"] = target
        await service.update_schema_metadata(MetadataUpdateCommand(**args))
        print(f"  meta  {name} {version} (deprecated={deprecated}, successor={successor_url})")


async def seed(storage_url: str, base_url: str) -> None:
    """Publish every sample schema into a store, then stamp lifecycle metadata.

    Args:
        storage_url: The store to populate.
        base_url: Where the instance is browsed.
    """
    repo = build_schema_repository(storage_url)
    service = SchemaService(repo)
    try:
        created, skipped = await _publish_samples(service)
        await _apply_labels(service)
        await _apply_metadata(service, base_url)
    finally:
        # The SQLAlchemy backend holds an engine; release its connections cleanly.
        engine = getattr(repo, "engine", None)
        if engine is not None:
            await engine.dispose()
    print(f"Seeded {created} schema version(s); {skipped} already present.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate the storage with sample schemas.")
    parser.add_argument(
        "--base-url",
        default=_DEFAULT_BASE_URL,
        help="where the instance is browsed, for its internal successor links",
    )
    asyncio.run(seed(settings.STORAGE_URL, parser.parse_args().base_url))
