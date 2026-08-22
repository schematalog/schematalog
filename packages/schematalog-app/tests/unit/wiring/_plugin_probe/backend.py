"""A storage backend defined entirely outside `schematalog`, to prove the seam holds.

It implements the five required methods and nothing else, inheriting `get_latest`,
`list_latest` and `list_predecessors` - so it is also the smallest demonstration that a
third party gets those for free and correct.
"""

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


class ProbeRepository(SchemaRepository):
    """Stores schemas in a list, in publication order, and nothing more."""

    def __init__(self, label: str = "") -> None:
        self.label = label
        self.rows: list[Schema] = []

    async def add(self, schema: Schema) -> Schema:
        if any(row.name == schema.name and row.version == schema.version for row in self.rows):
            raise SchemaConflictError(schema)
        self.rows.append(schema)
        return schema

    async def get(self, identity: SchemaIdentity) -> Schema:
        for row in self.rows:
            if row.name == identity.name and row.version == identity.version:
                return row
        raise UnknownSchemaError(identity.name, identity.version)

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

    async def list_versions(self, schema_name: SchemaName) -> AsyncIterable[Schema]:
        versions = [row for row in self.rows if row.name == schema_name]
        if not versions:
            raise UnknownSchemaError(schema_name)
        for schema in sorted(versions, key=lambda s: s.publication_id, reverse=True):
            yield schema

    async def list_names(self) -> AsyncIterable[SchemaName]:
        for name in sorted({row.name for row in self.rows}):
            yield name


def build_repository(url: str) -> ProbeRepository:
    """The conventional factory name a dotted scheme looks for."""
    return ProbeRepository(label=url)
