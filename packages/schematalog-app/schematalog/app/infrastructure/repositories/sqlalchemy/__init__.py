"""Async SQLAlchemy Core implementation of `SchemaRepository`.

JSONB on PostgreSQL, JSON on SQLite (see `common.sqla`). Sort order is pushed
into the SQL (`ORDER BY`) so the repository protocol's ordering contract is
satisfied at the database level. Tables are created lazily on first use; with no
migration tool in the project, this is the only mechanism that builds the schema.
"""

import asyncio
from collections.abc import AsyncIterable

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from schematalog.domain.exceptions import SchemaConflictError, UnknownSchemaError
from schematalog.domain.schema import (
    UNSET,
    JsonSchemaDocument,
    Schema,
    SchemaDescription,
    SchemaIdentity,
    SchemaName,
    SchemaRepository,
    SearchQuery,
    SuccessorReference,
    Unset,
)

from . import tables


def _latest_order(source: sa.FromClause) -> tuple[sa.ColumnElement, ...]:
    """The ORDER BY implementing the `get_latest` contract, newest-current-first.

    Takes the table or alias to read from, so the same expression serves both the direct
    query and the correlated subquery. A CASE expression rather than a WHERE clause, so
    one query answers both halves of the rule: current versions sort above disqualified ones, and within each group the
    newest publication wins. When every version is disqualified the second group is all
    there is, which is exactly the required fallback - no second round trip.
    """
    current = sa.case(
        (sa.and_(source.c.deprecated.is_(False), source.c.successor_url.is_(None)), 1),
        else_=0,
    )
    return (current.desc(), source.c.publication_id.desc())


_LIKE_ESCAPE = "\\"


def _term_clauses(query: SearchQuery) -> list[sa.ColumnElement[bool]]:
    """One clause per term, each requiring it in the name or the description.

    ANDed by `where`, so every term must be found but not all in the same field. The
    whole query is one scan with a predicate per row, not a statement per term.

    `lower()` not `ILIKE`: the latter is PostgreSQL-only, and both backends must answer
    identically. `coalesce` because an older row's description may still be NULL, and
    `NULL LIKE ...` is NULL, which would drop the row from an OR that should have
    matched on the name.
    """
    return [
        sa.or_(
            sa.func.lower(tables.schema.c.name).like(pattern, escape=_LIKE_ESCAPE),
            sa.func.lower(sa.func.coalesce(tables.schema.c.description, "")).like(
                pattern, escape=_LIKE_ESCAPE
            ),
        )
        for pattern in (_like_contains(term) for term in query.terms)
    ]


def _like_contains(query: str) -> str:
    """A `LIKE` pattern matching `query` anywhere in a value, wildcards defanged.

    `%` and `_` are wildcards to `LIKE`, and both are legal in a schema name - so a
    query interpolated straight into a pattern quietly means something else, and `a_b`
    would match `axb`. The conformance suite pins that case precisely because the bug is
    invisible until someone searches for a name with an underscore in it.
    """
    escaped = (
        query.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


class SQLAlchemySchemaRepository(SchemaRepository):
    """Stores schemas in a relational database via an injected `AsyncEngine`."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def _ensure_tables(self) -> None:
        """Create the tables on first use (idempotent, concurrency-safe)."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            async with self.engine.begin() as conn:
                await conn.run_sync(tables.db_metadata.create_all)
            self._initialized = True

    async def add(self, schema: Schema) -> Schema:
        await self._ensure_tables()
        values = {
            "name": schema.identity.name,
            "version": schema.identity.version,
            "description": str(schema.description),
            "json_schema": schema.json_schema.document,
            "publication_id": schema.publication_id,
            "deprecated": schema.deprecated,
            "successor_url": str(schema.successor) if schema.successor is not None else None,
        }
        try:
            async with self.engine.begin() as conn:
                await conn.execute(sa.insert(tables.schema).values(values))
        except IntegrityError as exc:
            raise SchemaConflictError(schema) from exc
        return schema

    async def get(self, identity: SchemaIdentity) -> Schema:
        await self._ensure_tables()
        stmt = sa.select(tables.schema).where(
            tables.schema.c.name == identity.name,
            tables.schema.c.version == identity.version,
        )
        async with self.engine.connect() as conn:
            row = (await conn.execute(stmt)).one_or_none()
        if row is None:
            raise UnknownSchemaError(identity.name, identity.version)
        return self._row_to_schema(row)

    async def set_metadata(
        self,
        identity: SchemaIdentity,
        *,
        deprecated: bool | None = None,
        successor: SuccessorReference | None | Unset = UNSET,
    ) -> Schema:
        await self._ensure_tables()
        values: dict[str, object] = {}
        if deprecated is not None:
            values["deprecated"] = deprecated
        if successor is not UNSET:
            values["successor_url"] = str(successor) if successor is not None else None
        if values:
            async with self.engine.begin() as conn:
                result = await conn.execute(
                    sa.update(tables.schema)
                    .where(
                        tables.schema.c.name == identity.name,
                        tables.schema.c.version == identity.version,
                    )
                    .values(**values)
                )
                if result.rowcount == 0:
                    raise UnknownSchemaError(identity.name, identity.version)
        return await self.get(identity)

    # `get_latest`, `list_latest` and `list_predecessors` are all derived correctly by
    # `SchemaRepository`, and are overridden below only because this backend can answer
    # them in one query each rather than by fetching rows and filtering in Python.
    async def get_latest(self, schema_name: SchemaName) -> Schema:
        await self._ensure_tables()
        # "Latest" is the newest *current* publication, falling back to the newest
        # outright. The version string is never compared - the registry does not
        # interpret it (see DECISIONS.md).
        stmt = (
            sa.select(tables.schema)
            .where(tables.schema.c.name == schema_name)
            .order_by(*_latest_order(tables.schema))
            .limit(1)
        )
        async with self.engine.connect() as conn:
            row = (await conn.execute(stmt)).one_or_none()
        if row is None:
            raise UnknownSchemaError(schema_name)
        return self._row_to_schema(row)

    async def list_names(self) -> AsyncIterable[SchemaName]:
        await self._ensure_tables()
        stmt = sa.select(tables.schema.c.name).distinct().order_by(tables.schema.c.name.asc())
        async with self.engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        for row in rows:
            yield row.name

    async def list_latest(self, *, query: SearchQuery | None = None) -> AsyncIterable[Schema]:
        await self._ensure_tables()
        # Correlated subquery: keep each name's latest by the same rule as `get_latest`.
        # ORDER BY ... LIMIT 1 rather than max(): PostgreSQL has no max() aggregate over
        # uuid, though SQLite obliges - the kind of divergence the integration lane exists
        # to catch.
        inner = tables.schema.alias()
        latest_publication = (
            sa.select(inner.c.publication_id)
            .where(inner.c.name == tables.schema.c.name)
            .order_by(*_latest_order(inner))
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            sa.select(tables.schema)
            .where(tables.schema.c.publication_id == latest_publication)
            .order_by(tables.schema.c.name.asc())
        )
        if query is not None:
            stmt = stmt.where(*_term_clauses(query))
        async with self.engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        for row in rows:
            yield self._row_to_schema(row)

    async def list_versions(self, schema_name: SchemaName) -> AsyncIterable[Schema]:
        await self._ensure_tables()
        stmt = (
            sa.select(tables.schema)
            .where(tables.schema.c.name == schema_name)
            .order_by(tables.schema.c.publication_id.desc())
        )
        async with self.engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        if not rows:
            raise UnknownSchemaError(schema_name)
        for row in rows:
            yield self._row_to_schema(row)

    async def list_predecessors(self, successor_url: str) -> AsyncIterable[Schema]:
        await self._ensure_tables()
        stmt = (
            sa.select(tables.schema)
            .where(tables.schema.c.successor_url == successor_url)
            .order_by(tables.schema.c.name.asc(), tables.schema.c.version.asc())
        )
        async with self.engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        for row in rows:
            yield self._row_to_schema(row)

    @staticmethod
    def _row_to_schema(row: sa.Row) -> Schema:
        return Schema(
            identity=SchemaIdentity(name=row.name, version=row.version),
            # `SchemaDescription` reads a NULL left by an older row as the empty description.
            description=SchemaDescription(text=row.description),
            json_schema=JsonSchemaDocument(document=row.json_schema),
            publication_id=row.publication_id,
            deprecated=row.deprecated,
            successor=(
                SuccessorReference(url=row.successor_url)
                if row.successor_url is not None
                else None
            ),
        )
