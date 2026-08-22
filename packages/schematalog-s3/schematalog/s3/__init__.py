"""An S3 storage backend for Schematalog.

Written against the public contract only - `schematalog.domain.schema` for the protocol
and its value objects, and nothing else. If this package ever needs to reach into the
registry's internals, that is a hole in the contract rather than a licence to reach.

Object layout, one JSON document per version:

    <prefix>/<name>/<version>.json

The prefix means one bucket can hold several registries, and the name segment makes
`list_names` a delimited listing rather than a scan.
"""

import asyncio
from collections.abc import AsyncIterable, Iterator
import json
from urllib.parse import parse_qsl, urlsplit

import boto3
from botocore.exceptions import ClientError

from schematalog.domain.exceptions import SchemaConflictError, UnknownSchemaError
from schematalog.domain.schema import (
    UNSET,
    Schema,
    SchemaIdentity,
    SchemaName,
    SchemaRepository,
    SuccessorReference,
    Unset,
)

__all__ = ["S3SchemaRepository", "build_repository"]

__version__ = "0.1.0"
"""This backend's own version, independent of the registry's and of the contract's."""


class S3SchemaRepository(SchemaRepository):
    """Stores each schema version as an object in an S3 bucket.

    Every call is a blocking boto3 call wrapped in `asyncio.to_thread`, the same shape
    the filesystem backend uses. It keeps the dependency to the client most people
    already have rather than adding an async one.
    """

    def __init__(self, bucket: str, prefix: str = "", **client_options: str) -> None:
        self.bucket_name = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3", **client_options)

    # ---- key mapping ----------------------------------------------------------------

    def _prefix_for(self, name: str = "") -> str:
        parts = [part for part in (self.prefix, name) if part]
        return "/".join(parts) + "/" if parts else ""

    def _key_for(self, identity: SchemaIdentity) -> str:
        return f"{self._prefix_for(identity.name)}{identity.version}.json"

    # ---- required methods -----------------------------------------------------------

    async def add(self, schema: Schema) -> Schema:
        await asyncio.to_thread(self._put_new, schema)
        return schema

    async def get(self, identity: SchemaIdentity) -> Schema:
        return await asyncio.to_thread(self._get_object, identity)

    async def set_metadata(
        self,
        identity: SchemaIdentity,
        *,
        deprecated: bool | None = None,
        successor: SuccessorReference | None | Unset = UNSET,
    ) -> Schema:
        schema = await self.get(identity)
        if deprecated is not None:
            schema.deprecated = deprecated
        if successor is not UNSET:
            schema.successor = successor
        await asyncio.to_thread(self._put_over, schema)
        return schema

    async def list_versions(self, schema_name: SchemaName) -> AsyncIterable[Schema]:
        versions = await asyncio.to_thread(self._all_versions, schema_name)
        if not versions:
            raise UnknownSchemaError(schema_name)
        for schema in sorted(versions, key=lambda s: s.publication_id, reverse=True):
            yield schema

    async def list_names(self) -> AsyncIterable[SchemaName]:
        for name in await asyncio.to_thread(self._all_names):
            yield name

    # ---- blocking implementations ---------------------------------------------------

    def _put_new(self, schema: Schema) -> None:
        """Write a version only if the key is absent.

        `IfNoneMatch` makes S3 itself refuse the second writer, so the fail-on-conflict
        promise does not depend on a read that another writer could race. A HEAD-then-PUT
        would leave exactly that window.

        Raises:
            SchemaConflictError: If the version already exists.
        """
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=self._key_for(schema.identity),
                Body=json.dumps(schema.serialize()).encode(),
                ContentType="application/json",
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {
                "PreconditionFailed",
                "ConditionalRequestConflict",
            }:
                raise SchemaConflictError(schema) from exc
            raise

    def _put_over(self, schema: Schema) -> None:
        """Replace an existing version's object; metadata updates are the only writer here."""
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=self._key_for(schema.identity),
            Body=json.dumps(schema.serialize()).encode(),
            ContentType="application/json",
        )

    def _get_object(self, identity: SchemaIdentity) -> Schema:
        try:
            response = self.client.get_object(
                Bucket=self.bucket_name, Key=self._key_for(identity)
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                raise UnknownSchemaError(identity.name, identity.version) from exc
            raise
        return Schema.deserialize(json.loads(response["Body"].read()))

    def _all_versions(self, schema_name: str) -> list[Schema]:
        return [
            Schema.deserialize(
                json.loads(
                    self.client.get_object(Bucket=self.bucket_name, Key=key)["Body"].read()
                )
            )
            for key in self._keys_under(self._prefix_for(schema_name))
        ]

    def _all_names(self) -> list[str]:
        """Schema names, from the common prefixes one level down.

        A delimited listing asks S3 for the "directories" rather than every object, so
        this costs one request per thousand names instead of one per thousand versions.
        """
        prefix = self._prefix_for()
        names = [
            entry["Prefix"].removeprefix(prefix).rstrip("/")
            for page in self._paginate(Prefix=prefix, Delimiter="/")
            for entry in page.get("CommonPrefixes", [])
        ]
        return sorted(names)

    def _keys_under(self, prefix: str) -> Iterator[str]:
        for page in self._paginate(Prefix=prefix):
            for entry in page.get("Contents", []):
                if entry["Key"].endswith(".json"):
                    yield entry["Key"]

    def _paginate(self, **kwargs: str) -> Iterator[dict]:
        return self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket_name, **kwargs
        )


def build_repository(url: str) -> S3SchemaRepository:
    """Build the repository from `s3://bucket/prefix?region=...&endpoint_url=...`.

    Credentials are deliberately not read from the URL. They belong to the ordinary AWS
    chain - environment, shared config, instance role - and a URL is the last place a
    secret should live, given where URLs end up.
    """
    parts = urlsplit(url)
    options = dict(parse_qsl(parts.query))
    client_options = {
        key: options[key] for key in ("region_name", "endpoint_url") if key in options
    }
    if "region" in options:
        client_options["region_name"] = options["region"]
    return S3SchemaRepository(
        bucket=parts.netloc, prefix=parts.path.strip("/"), **client_options
    )
