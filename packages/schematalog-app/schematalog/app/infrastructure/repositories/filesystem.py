import asyncio
from collections.abc import AsyncIterable
import json
from pathlib import Path
import uuid

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


class FilesystemSchemaRepository(SchemaRepository):
    """Manages schemas as JSON files on the filesystem.

    Public async methods delegate the blocking I/O to a thread pool via
    `asyncio.to_thread`; `_*_sync` siblings hold the actual logic. The list
    methods materialise (and sort) the full result in a thread, then yield
    from it as async generators - at Schematalog's data scale this trades
    no perceptible cost for a uniform AsyncIterable contract across backends.
    """

    def __init__(self, directory: Path | str):
        self.directory: Path = Path(directory)
        if not self.directory.exists():
            self.directory.mkdir()
        if not self.directory.is_dir():
            raise ValueError("Storage path has to point to a directory.")  # noqa: TRY003

    async def add(self, schema: Schema) -> Schema:
        return await asyncio.to_thread(self._add_sync, schema)

    async def get(self, identity: SchemaIdentity) -> Schema:
        return await asyncio.to_thread(self._get_sync, identity.name, identity.version)

    async def set_metadata(
        self,
        identity: SchemaIdentity,
        *,
        deprecated: bool | None = None,
        successor: SuccessorReference | None | Unset = UNSET,
    ) -> Schema:
        return await asyncio.to_thread(
            self._set_metadata_sync,
            identity.name,
            identity.version,
            deprecated,
            successor,
        )

    async def list_names(self) -> AsyncIterable[SchemaName]:
        for schema_name in await asyncio.to_thread(self._list_names_sync):
            yield schema_name

    async def list_versions(self, schema_name: SchemaName) -> AsyncIterable[Schema]:
        items = await asyncio.to_thread(self._list_versions_sync, schema_name)
        for schema in items:
            yield schema

    # ---- blocking implementations (called only via to_thread above) ----

    def _add_sync(self, schema: Schema) -> Schema:
        self._save_to_file(schema, create=True)
        return schema

    def _get_sync(self, schema_name: str, version: str) -> Schema:
        versions = self._get_versions(schema_name)
        schema = versions.get(version)
        if not schema:
            raise UnknownSchemaError(schema_name, version)
        return schema

    def _set_metadata_sync(
        self,
        schema_name: str,
        version: str,
        deprecated: bool | None,
        successor: SuccessorReference | None | Unset,
    ) -> Schema:
        schema = self._get_sync(schema_name, version)
        if deprecated is not None:
            schema.deprecated = deprecated
        if successor is not UNSET:
            schema.successor = successor
        # Overwrite in place (create=False): identity and publication_id are untouched.
        self._save_to_file(schema, create=False)
        return schema

    def _list_names_sync(self) -> list[str]:
        """Directory names that actually hold versions, ascending.

        The emptiness check is not paranoia: a name whose directory holds no version
        files does not exist as far as the registry is concerned, and yielding it would
        make the derived `list_latest` raise on a schema nobody published.
        """
        return sorted(
            entry.name
            for entry in self.directory.iterdir()
            if entry.is_dir() and self._get_versions(entry.name)
        )

    def _list_versions_sync(self, schema_name: str) -> list[Schema]:
        versions = self._get_versions(schema_name)
        if not versions:
            raise UnknownSchemaError(schema_name)
        return sorted(versions.values(), key=lambda s: s.publication_id, reverse=True)

    # ---- helpers ----

    def _get_schema_dir(self, schema_name: str) -> Path:
        return self.directory / schema_name

    def _save_to_file(self, schema: Schema, create: bool = False) -> None:
        """Write a version, either claiming it or replacing it, without a window in between.

        A new version is created with mode `x`, which fails if the file already exists -
        the exclusivity is the filesystem's, so two writers racing on the same
        `(name, version)` cannot both believe they won. Checking `exists()` first and then
        opening for writing would leave exactly that gap, and the loser's document would
        be silently overwritten rather than refused.

        A metadata update writes a sibling temporary file and renames it over the target.
        Rename is atomic, so a reader sees either the old document or the new one, never
        a half-written file - which a direct truncate-and-write would produce for any
        process that crashed mid-write.

        Raises:
            SchemaConflictError: If `create` is set and the version already exists.
        """
        schema_dir = self._get_schema_dir(schema.identity.name)
        schema_dir.mkdir(parents=True, exist_ok=True)
        file = schema_dir / f"{schema.identity.version}.json"
        payload = json.dumps(schema.serialize())
        if create:
            try:
                with file.open("x") as version_file:
                    version_file.write(payload)
            except FileExistsError as exc:
                raise SchemaConflictError(schema) from exc
            return
        temporary = file.with_name(f".{file.name}.{uuid.uuid4().hex}")
        temporary.write_text(payload)
        temporary.replace(file)

    def _get_versions(self, schema_name: str) -> dict[str, Schema]:
        schema_dir = self._get_schema_dir(schema_name)
        if not schema_dir.is_dir():
            raise UnknownSchemaError(schema_name)
        return {
            file.stem: Schema.deserialize(file.read_text()) for file in schema_dir.iterdir()
        }
