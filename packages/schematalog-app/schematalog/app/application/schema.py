"""Schema catalogue use cases.

Thin orchestration over the domain and the schema repository, so both presentations
(API and Web UI) share one implementation of each use case.
"""

from collections.abc import AsyncIterable
from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ValidationError

from schematalog.app.application.exceptions import (
    DuplicateSchemaError,
    InvalidSchemaError,
    InvalidSuccessorError,
    SchemaNotFoundError,
)
from schematalog.common.logging import get_logger
from schematalog.common.models import FrozenModel
from schematalog.common.validation import IncompatibleSchemaError, preprocess_schema
from schematalog.domain.exceptions import SchemaConflictError, UnknownSchemaError

# Re-exported for presentation, which must not import from `domain`.
from schematalog.domain.schema import QUERY_PATTERN as QUERY_PATTERN
from schematalog.domain.schema import (
    UNSET,
    JsonSchemaDocument,
    Schema,
    SchemaDescription,
    SchemaIdentity,
    SchemaName,
    SchemaRepository,
    SchemaVersion,
    SuccessorReference,
)

log = get_logger(__name__)


class PublishCommand(BaseModel):
    """Input for `SchemaService.publish`.

    Kept flat (rather than nesting a `SchemaIdentity`) because this is the bridge
    from external input (API body, form fields) into the domain - the conversion
    to `SchemaIdentity` happens inside `publish`.
    """

    name: SchemaName
    version: SchemaVersion
    json_schema: dict[str, Any]
    description: str | None = None


class GetSchemaCommand(BaseModel):
    """Input for `SchemaService.get`."""

    name: SchemaName
    version: SchemaVersion | None = None
    """Omit (or `None`) to retrieve the latest version."""


class ListVersionsCommand(BaseModel):
    """Input for `SchemaService.list_versions`."""

    name: SchemaName


class ListLatestCommand(BaseModel):
    """Input for `SchemaService.list_latest_schemas`."""

    query: str | None = None
    """Narrows the listing to schemas whose name contains this, ignoring case. `None` or
    blank selects everything, so an empty search box behaves as no search rather than as
    a search for nothing. The repository owns the matching rule; see `matches_query`."""


class ListPredecessorsCommand(BaseModel):
    """Input for `SchemaService.list_schema_predecessors`."""

    successor_url: str
    """The canonical URL whose predecessors (the versions declaring it as their successor)
    to list. Built by presentation, which owns routing."""


class MetadataUpdateCommand(BaseModel):
    """Input for `SchemaService.update_metadata` - a partial (PATCH) update.

    Flat like `PublishCommand`: it identifies the target version (`name`, `version`)
    and carries the *mutable* metadata to change. Only fields set to a non-None value
    are applied; `None` leaves them untouched. Immutable identity/document fields are
    never carried here.
    """

    name: SchemaName
    version: SchemaVersion
    deprecated: bool | None = None
    successor: SuccessorReference | None = None
    """The new successor reference (or `None` to clear it). Tri-state: whether to touch
    the successor at all is read from `model_fields_set`, so 'not provided' (leave as-is)
    is distinct from an explicit `None` (clear)."""
    successor_target: SchemaIdentity | None = None
    """The internal `(name, version)` the successor URL resolves to, if it points at this
    registry (else `None`). Resolved by presentation (it owns routing); the service
    existence-checks it. Not set when clearing or for an external successor."""


class SchemaView(FrozenModel):
    """Read model returned by `SchemaService` query/command methods.

    A flat, transport-agnostic projection of the domain `Schema`, so presentation
    depends only on the application's contract and never touches the domain entity.
    `document` is the raw stored JSON Schema; stamping the canonical `$id` into it is
    a presentation concern (it needs HTTP routing), applied when the response is built.
    """

    name: SchemaName
    version: SchemaVersion
    description: str | None
    document: dict[str, Any]
    publication_id: uuid.UUID
    published_on: datetime
    deprecated: bool
    successor: SuccessorReference | None

    @classmethod
    def from_schema(cls, schema: Schema) -> SchemaView:
        return cls(
            name=schema.name,
            version=schema.version,
            description=str(schema.description) if schema.description else None,
            document=schema.json_schema.document,
            publication_id=schema.publication_id,
            published_on=schema.published_on,
            deprecated=schema.deprecated,
            successor=schema.successor,
        )


class SchemaService:
    """Use-case facade over a storage repository."""

    def __init__(self, repo: SchemaRepository) -> None:
        self._repo = repo

    async def publish_schema(self, command: PublishCommand) -> SchemaView:
        """Validate and store a new schema version.

        Args:
            command: The version to publish (identity, document, optional
                description).

        Returns:
            A view of the stored schema, carrying its publication identifier.

        Raises:
            InvalidSchemaError: If the document conforms to no supported metaschema, or
                the name, version or description breaks a domain constraint.
            DuplicateSchemaError: If this name/version already exists.
        """
        try:
            document = preprocess_schema(command.json_schema)
        except IncompatibleSchemaError as exc:
            raise InvalidSchemaError from exc
        try:
            schema = Schema(
                identity=SchemaIdentity(name=command.name, version=command.version),
                description=(
                    SchemaDescription(text=command.description) if command.description else None
                ),
                json_schema=JsonSchemaDocument(document=document),
                # Ownership of an existing name is checked before the entity is built.
            )
        except ValidationError as exc:
            # The domain's own constraints (the description length cap, the name and
            # version patterns) are enforced when the entity is built. They are input
            # errors like any other, so they must not surface as a raw pydantic error:
            # a caller sees an ApplicationError, per the error-layering rule.
            raise InvalidSchemaError(str(exc)) from exc
        try:
            stored = await self._repo.add(schema)
        except SchemaConflictError as exc:
            raise DuplicateSchemaError(str(exc)) from exc
        log.info("published schema", name=str(stored.name), version=str(stored.version))
        return SchemaView.from_schema(stored)

    async def get_schema(self, command: GetSchemaCommand) -> SchemaView:
        """Retrieve a schema version - the latest if `command.version` is omitted.

        Centralises the "empty version -> latest" decision so both presentations
        stay thin adapters rather than each choosing `get` vs `get_latest`.

        Args:
            command: The target schema name and optional version.

        Returns:
            A view of the requested version, or the latest when no version is given.

        Raises:
            SchemaNotFoundError: If the name (or the specific version) does not exist.
        """
        try:
            if command.version:
                schema = await self._repo.get(
                    SchemaIdentity(name=command.name, version=command.version)
                )
            else:
                schema = await self._repo.get_latest(command.name)
        except UnknownSchemaError as exc:
            raise SchemaNotFoundError(str(exc)) from exc
        return SchemaView.from_schema(schema)

    async def update_schema_metadata(self, command: MetadataUpdateCommand) -> SchemaView:
        """Update an existing version's mutable metadata.

        Args:
            command: The target version and the mutable fields to change (None = leave
                unchanged).

        Returns:
            A view of the updated schema (unchanged when the command carries no changes).

        Raises:
            SchemaNotFoundError: If the version does not exist.
            InvalidSuccessorError: If an internal successor is self-referential or missing.
        """
        identity = SchemaIdentity(name=command.name, version=command.version)
        try:
            schema = await self._repo.get(identity)
        except UnknownSchemaError as exc:
            raise SchemaNotFoundError(str(exc)) from exc
        touch_successor = "successor" in command.model_fields_set
        if command.deprecated is None and not touch_successor:
            return SchemaView.from_schema(schema)
        if touch_successor and command.successor_target is not None:
            await self._validate_successor(identity, command.successor_target)
        updated = schema.with_metadata(
            deprecated=command.deprecated,
            successor=command.successor if touch_successor else UNSET,
        )
        metadata: dict[str, Any] = {"deprecated": updated.deprecated}
        if touch_successor:
            metadata["successor"] = updated.successor
        stored = await self._repo.set_metadata(updated.identity, **metadata)
        return SchemaView.from_schema(stored)

    async def _validate_successor(
        self, identity: SchemaIdentity, target: SchemaIdentity
    ) -> None:
        """Reject an internal successor that is self-referential or does not exist.

        Only internal targets reach here (presentation resolves external URLs to a `None`
        target); external references are taken on faith - no network/existence check.
        """
        if target == identity:
            raise InvalidSuccessorError("A schema cannot supersede itself.")  # noqa: TRY003
        try:
            await self._repo.get(target)
        except UnknownSchemaError as exc:
            raise InvalidSuccessorError(  # noqa: TRY003
                f"Successor target does not exist: `{target.name} v{target.version}`."
            ) from exc

    async def list_latest_schemas(
        self, command: ListLatestCommand | None = None
    ) -> AsyncIterable[SchemaView]:
        """The latest version of every schema, optionally narrowed by a search.

        Args:
            command: the listing's parameters; omitted means an unfiltered listing.

        Yields:
            A view of each latest version, in ascending name order. Filtered rather than
            ranked, so the order is the same with a query as without one.
        """
        command = command or ListLatestCommand()
        async for schema in self._repo.list_latest(query=command.query):
            yield SchemaView.from_schema(schema)

    async def list_schema_versions(
        self, command: ListVersionsCommand
    ) -> AsyncIterable[SchemaView]:
        """All versions of a schema.

        Args:
            command: The schema name whose versions to list.

        Yields:
            A view of each version, newest first.

        Raises:
            SchemaNotFoundError: If the name does not exist.
        """
        try:
            async for schema in self._repo.list_versions(command.name):
                yield SchemaView.from_schema(schema)
        except UnknownSchemaError as exc:
            raise SchemaNotFoundError(str(exc)) from exc

    async def list_schema_predecessors(
        self, command: ListPredecessorsCommand
    ) -> AsyncIterable[SchemaView]:
        """Versions that declare `command.successor_url` as their successor.

        The derived inverse of the successor reference (predecessors are not stored).

        Args:
            command: The canonical URL whose predecessors to list.

        Yields:
            A view of each predecessor, in (name, version) order.
        """
        async for schema in self._repo.list_predecessors(command.successor_url):
            yield SchemaView.from_schema(schema)
