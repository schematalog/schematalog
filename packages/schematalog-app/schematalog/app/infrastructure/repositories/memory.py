from collections import defaultdict
from collections.abc import AsyncIterable

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

# name -> version -> Schema
StorageType = dict[str, dict[str, Schema]]


class MemorySchemaRepository(SchemaRepository):
    """Manages schemas as JSON objects in memory, keyed by (name, version)."""

    def __init__(self) -> None:
        self.storage: StorageType = defaultdict(dict)

    async def add(self, schema: Schema) -> Schema:
        name, version = schema.identity.name, schema.identity.version
        if self.storage.get(name, {}).get(version):
            raise SchemaConflictError(schema)
        self.storage[name][version] = schema
        return schema

    async def get(self, identity: SchemaIdentity) -> Schema:
        schema = self.storage.get(identity.name, {}).get(identity.version)
        if schema is None:
            raise UnknownSchemaError(identity.name, identity.version)
        return schema

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
        return schema

    async def list_names(self) -> AsyncIterable[SchemaName]:
        for schema_name in sorted(self.storage):
            yield schema_name

    async def list_versions(self, schema_name: SchemaName) -> AsyncIterable[Schema]:
        versions = self.storage.get(schema_name)
        if not versions:
            raise UnknownSchemaError(schema_name)
        for schema in sorted(versions.values(), key=lambda s: s.publication_id, reverse=True):
            yield schema
