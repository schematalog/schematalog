from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Mapping
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Annotated, Any, Final, Literal
from urllib.parse import urlparse
import uuid

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_serializer,
    model_validator,
)

from schematalog.common.models import FrozenModel
from schematalog.domain.exceptions import UnknownSchemaError

# `publication_id` must be this UUID version: its high 48 bits are a big-endian
# millisecond timestamp, which is what makes the value sort in publication order.
PUBLICATION_UUID_VERSION = 7
# Those 48 bits sit above the remaining 80, so shifting right by 80 yields the
# milliseconds since the epoch.
_PUBLICATION_TIMESTAMP_SHIFT = 80

# Names and versions: an alphanumeric followed by alphanumerics, dashes, dots, underscores.
NAME_PATTERN = r"^[0-9a-zA-Z][0-9a-zA-Z-_\.]*$"

SchemaName = Annotated[str, Field(pattern=NAME_PATTERN)]
SchemaVersion = Annotated[str, Field(pattern=NAME_PATTERN)]


class _UnsetType(Enum):
    """Sentinel enum: its sole member `UNSET` distinguishes 'leave a nullable field
    unchanged' from 'set it to None'.

    `None` is a meaningful value for a clearable reference (it *clears* it), so PATCH-style
    updates need a third state for 'not provided'. An enum member is a singleton by
    construction, so `x is UNSET` is bulletproof and type checkers narrow on it. The enum
    class stays private; consumers use the public `UNSET` value and `Unset` type alias (the
    sentinel appears in the repository protocol's `set_metadata` signature).

    TODO(py3.15): replace this hand-rolled sentinel with the stdlib `typing.Sentinel`
    (PEP 661) once we require Python 3.15.
    """

    UNSET = auto()

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = _UnsetType.UNSET
type Unset = Literal[_UnsetType.UNSET]


class ValueObject(FrozenModel):
    """Domain-layer base for immutable value objects.

    Just `FrozenModel` under a domain-semantic name - kept here so the domain
    code says what it means. Anything richer (identity helpers, events) belongs
    in a more specific base.
    """


class SchemaIdentity(ValueObject):
    """The identity of one specific schema version.

    Designed to grow: `category` would join here.
    """

    name: Annotated[SchemaName, Field(description="Unique name of the schema.")]
    version: Annotated[SchemaVersion, Field(description="Version of the schema.")]


class SchemaDescription(ValueObject):
    """Free-form description of a schema. Intended to render as Markdown.

    No formal Markdown validation today - CommonMark accepts virtually any text.
    The wrapper exists so future rules (formatting constraints, rendering,
    search indexing) have a home. The model serialises flat to the wire and
    accepts a raw string on the way in, so call sites stay terse.
    """

    text: Annotated[str, Field(max_length=65536)]

    def __str__(self) -> str:
        return self.text

    @model_serializer(mode="plain")
    def _serialize(self) -> str:
        return self.text

    @model_validator(mode="before")
    @classmethod
    def _wrap_raw(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"text": value}
        return value


class SuccessorReference(ValueObject):
    """Reference to the version that supersedes a schema - an absolute URI.

    Open-world: an internal schema's canonical `$id` or a schema in any external
    registry. Stored and serialised flat as the URL string, and accepts a raw string
    on the way in (like `SchemaDescription`), so call sites stay terse.
    """

    url: Annotated[str, Field(description="Absolute URI of the superseding version.")]

    def __str__(self) -> str:
        return self.url

    @field_validator("url")
    @classmethod
    def _must_be_absolute(cls, value: str) -> str:
        parsed = urlparse(value)
        if not (parsed.scheme and parsed.netloc):
            raise ValueError("successor must be an absolute URI")  # noqa: TRY003
        return value

    @model_serializer(mode="plain")
    def _serialize(self) -> str:
        return self.url

    @model_validator(mode="before")
    @classmethod
    def _wrap_raw(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"url": value}
        return value


class JsonSchemaDocument(ValueObject):
    """A JSON Schema document.

    The document is expected to have been normalised + metaschema-validated via
    `common.validation.preprocess_schema` before construction (so `$schema` is
    set, OpenAPI `nullable` is converted, and any incoming `$id` is stripped).
    Forthcoming `$ref` resolution and instance-validation methods belong here.

    Unlike `SchemaDescription`, this object does NOT auto-wrap raw dict input -
    the raw and the wrapped forms are both dicts and can't be told apart. The
    wrapping happens at the `Schema.json_schema` field validator instead.
    """

    document: dict[str, Any]

    @property
    def metaschema(self) -> str:
        """The metaschema URI this document conforms to (the `$schema` value)."""
        return self.document.get("$schema", "")

    @property
    def schema_id(self) -> str | None:
        """The document's own `$id`, if it declares one."""
        return self.document.get("$id")

    @model_serializer(mode="plain")
    def _serialize(self) -> dict[str, Any]:
        return self.document


class Schema(BaseModel):
    """A catalogued JSON Schema specification: the stored schema plus its metadata.

    Identity is composite (`name`, `version`) and lives in a dedicated `identity`
    value object; `description` and `json_schema` are also value objects
    (`SchemaDescription`, `JsonSchemaDocument`). `schema.name` and `schema.version`
    are convenience `@computed_field`s that delegate to `identity`. The wire stays
    flat (description as string, schema as dict) because each value object owns
    its `@model_serializer(mode="plain")`.
    """

    # validate_by_name/validate_by_alias let us build a Schema from either `schema` or `json_schema`.
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    identity: Annotated[SchemaIdentity, Field(exclude=True, repr=False)]
    """The domain identity field; excluded from serialization in favour of the
    `name` / `version` computed fields below, so the wire stays flat."""
    description: Annotated[
        SchemaDescription | None, Field(description="Description of the schema.")
    ] = None
    json_schema: Annotated[
        JsonSchemaDocument, Field(alias="schema", description="The JSON Schema document.")
    ]
    """The stored document is an arbitrary JSON Schema. `schema` shadows a BaseModel
    attribute, so the field is `json_schema` and serialises under the `schema` key."""
    publication_id: Annotated[
        uuid.UUID,
        Field(
            default_factory=uuid.uuid7,
            description="Opaque identifier of this publication; the registry's sort key.",
        ),
    ]
    """The ordering of every version, and immutable like the identity itself.

    It **must** be a UUID version 7, which is why the version is validated rather than
    assumed. Three things depend on the layout specifically, and all three fail quietly
    rather than loudly under any other version: the high 48 bits are a big-endian
    millisecond timestamp, so the value sorts in publication order (a v4 is uniformly
    random and would randomise every listing while remaining a valid UUID); `published_on`
    is read straight out of those same bits, so a non-v7 yields a nonsense date rather
    than an error; and a storage backend must persist it so its natural ordering survives
    - a native uuid column, fixed-width lowercase hex, or 16 big-endian bytes in an
    object key.

    Minted where the entity is built, which is above the repository layer: a backend that
    minted its own would silently order wrong, and there would be one more clause in the
    contract a third-party backend has to get right.
    """
    deprecated: Annotated[bool, Field(description="Whether this version is deprecated.")] = (
        False
    )
    """Mutable lifecycle metadata: a deprecated version is not answered as the schema's
    latest unless every version is deprecated (see `is_current`). Freely reversible -
    deprecating a version makes no promise to anyone that undeprecating it would break."""
    successor: Annotated[
        SuccessorReference | None,
        Field(description="URI of the version that supersedes this one, if any."),
    ] = None
    """Mutable lifecycle metadata - an absolute URI (internal `$id` or external). Set,
    changed, or cleared via metadata update; `None` means no declared successor."""

    @computed_field
    @property
    def published_on(self) -> datetime:
        """When this version was published, derived from `publication_id`.

        Stored nowhere: a UUIDv7 carries 48 bits of epoch milliseconds in its high bits,
        so the timestamp is read back out of the identifier. That removes a column from
        every backend and makes drift between the two impossible - there is no second
        value to disagree. Resolution is milliseconds.

        The shift is deliberate in preference to `UUID.time`, which is *not* reliable
        here: a database driver may hand back a `uuid.UUID` **subclass** of its own (the
        PostgreSQL driver does), and on such an instance `UUID.time` takes the version-1
        branch and returns a different number for the very same bits. The shift is the
        v7 layout itself and depends on no class behaviour.
        """
        return datetime.fromtimestamp(
            (self.publication_id.int >> _PUBLICATION_TIMESTAMP_SHIFT) / 1000, tz=UTC
        )

    @computed_field
    @property
    def name(self) -> str:
        return self.identity.name

    @computed_field
    @property
    def version(self) -> str:
        return self.identity.version

    @field_validator("publication_id")
    @classmethod
    def _require_uuid7(cls, value: uuid.UUID) -> uuid.UUID:
        """Reject any UUID that is not version 7.

        Raises:
            ValueError: If the identifier is not a version 7 UUID.
        """
        if value.version != PUBLICATION_UUID_VERSION:
            raise ValueError(  # noqa: TRY003
                f"publication_id must be a UUID version {PUBLICATION_UUID_VERSION}, "
                f"got v{value.version}"
            )
        return value

    @field_validator("json_schema", mode="before")
    @classmethod
    def _wrap_json_schema(cls, value: Any) -> Any:
        """Wrap a raw JSON Schema dict into `{"document": dict}` for construction.

        Skipped when the value is already a `JsonSchemaDocument` (Python
        construction path) - the wrapper is only needed when deserialising from
        wire / disk where the field arrives as a raw dict.
        """
        if isinstance(value, JsonSchemaDocument):
            return value
        return {"document": value}

    @model_validator(mode="before")
    @classmethod
    def _gather_flat_identity(cls, data: Any) -> Any:
        """Accept the flat stored form `{name, version, ...}` as well as the nested
        `{identity: {name, version}, ...}`.

        The flat form is what `serialize()` produces (identity is excluded in favour of
        the `name`/`version` computed fields), so this is the read half of the storage
        roundtrip, not a legacy shim."""
        if isinstance(data, dict) and "identity" not in data:
            name = data.get("name")
            version = data.get("version")
            if name is not None and version is not None:
                rest = {k: v for k, v in data.items() if k not in {"name", "version"}}
                return {"identity": {"name": name, "version": version}, **rest}
        return data

    def with_metadata(
        self,
        *,
        deprecated: bool | None = None,
        successor: SuccessorReference | None | Unset = UNSET,
    ) -> Schema:
        """Return a copy with the given mutable metadata changed.

        For `deprecated`, `None` leaves the field as-is (it is never cleared).
        `successor` is clearable, so it uses the `UNSET` sentinel: `UNSET` leaves it
        unchanged, `None` clears it, a reference sets it. Both are freely reversible.
        """
        updates: dict[str, Any] = {}
        if deprecated is not None:
            updates["deprecated"] = deprecated
        if successor is not UNSET:
            updates["successor"] = successor
        return self.model_copy(update=updates)

    @property
    def is_current(self) -> bool:
        """Whether this version may be answered as the schema's latest.

        A version disqualifies itself two ways: `deprecated` says "do not use this", and
        a declared `successor` says "the replacement is over there". Returning either as
        "latest" would answer "use this" for something that has said otherwise.

        Only the version's own fields are read - the successor link is never followed.
        That keeps the rule single-hop and total: a cycle of successors simply leaves no
        current version, which the caller's fallback already handles.
        """
        return not self.deprecated and self.successor is None

    def has_successor(self, url: str) -> bool:
        """Whether this version declares `url` as its successor.

        The predicate behind predecessor lookups: a version is a predecessor of `url`
        when it points its successor at it.
        """
        return self.successor is not None and str(self.successor) == url

    def serialize(self) -> dict[str, Any]:
        """The JSON-compatible wire form, using public field names (`schema`, not `json_schema`)."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    @classmethod
    def deserialize(cls, raw: Mapping[str, Any] | str) -> Schema:
        """Reconstruct a Schema from its stored form, a JSON string or a mapping."""
        if isinstance(raw, str):
            return cls.model_validate_json(raw)
        return cls.model_validate(raw)


def normalise_query(query: str | None) -> str | None:
    """A search query as matching sees it, or `None` when it selects everything.

    Blank and whitespace-only queries are absent queries. `?q=` is what an empty search
    box submits, and answering it with nothing would be a worse answer than answering it
    with everything.
    """
    if query is None:
        return None
    normalised = query.strip().casefold()
    return normalised or None


def matches_query(schema: Schema, query: str | None) -> bool:
    """Whether `schema` satisfies the search guarantee for `query`.

    The guarantee is deliberately narrow - a case-insensitive substring of the name -
    because the same interface sits over a Python scan, a SQL `LIKE`, and one day
    something with an index, and a caller has to be able to rely on the answer being the
    same wherever it runs. A faster implementation is allowed; a different one is not.
    Stemming, fuzzy matching and relevance ordering are all *differences*, which is why
    none of them are promised (see `DECISIONS.md`).

    `casefold` rather than `lower`: it is the comparison Unicode defines for this, and
    although `NAME_PATTERN` admits only ASCII today, the fields matched here are expected
    to grow to include the description, which is free text.
    """
    normalised = normalise_query(query)
    return normalised is None or normalised in schema.name.casefold()


class SchemaRepository(ABC):
    """The storage contract, and the seam a third-party backend implements.

    **Five methods are required**: `add`, `get`, `set_metadata`, `list_versions` and
    `list_names`. The other three - `get_latest`, `list_latest` and `list_predecessors` -
    are derived from those here, and a backend overrides them only when it can answer them
    better (the SQL backend does; it has real queries for all three).

    The split is deliberate. Two of the derived methods encode the *latest* rule, which is
    policy rather than storage: newest current version, falling back to newest outright.
    Defining it once means a new backend is correct about `latest` before its author has
    read what `latest` means, rather than correct only if the conformance suite catches
    them being wrong.

    Ordering is never derived from the version string - the registry does not interpret it
    (see `DECISIONS.md`). Everything orders by `publication_id`, whose byte order is
    publication order, so a backend must store it in a form that preserves that ordering.
    """

    @abstractmethod
    async def add(self, schema: Schema) -> Schema:
        """Add and save the schema version.

        Raises SchemaConflictError if (name, version) is already present.
        """

    @abstractmethod
    async def get(self, identity: SchemaIdentity) -> Schema:
        """Retrieve a specific schema version.

        Raises UnknownSchemaError if the version does not exist.
        """
        ...

    @abstractmethod
    async def set_metadata(
        self,
        identity: SchemaIdentity,
        *,
        deprecated: bool | None = None,
        successor: SuccessorReference | None | Unset = UNSET,
    ) -> Schema:
        """Update an existing version's mutable metadata.

        `deprecated` changes only when non-None; `successor` changes only when not
        `UNSET` (`None` clears it, a reference sets it). Touches no immutable
        field (identity, json_schema, publication_id). Returns the updated schema. Raises
        UnknownSchemaError if the version does not exist.
        """
        ...

    @abstractmethod
    def list_versions(self, schema_name: SchemaName) -> AsyncIterable[Schema]:
        """All versions of a schema, yielded newest first (by `publication_id`).

        Raises UnknownSchemaError if the name has no versions.
        """
        ...

    @abstractmethod
    def list_names(self) -> AsyncIterable[SchemaName]:
        """Every schema name held by this store, in ascending order.

        The enumerate primitive the derived methods are built on: a directory listing, a
        delimited prefix listing, a `SELECT DISTINCT name`.
        """
        ...

    # ---- derived: correct as written, overridable where a backend can do better ----

    async def get_latest(self, schema_name: SchemaName) -> Schema:
        """Retrieve the latest version of a schema by name.

        "Latest" is the most recently published version that is still `is_current`
        (neither deprecated nor superseded), falling back to the most recently published
        version outright when every one of them is disqualified. Without the fallback a
        schema whose versions are all deprecated would have no latest at all; with it,
        the answer is always the most useful version available.

        Raises UnknownSchemaError if no versions exist for that name.
        """
        newest: Schema | None = None
        async for schema in self.list_versions(schema_name):
            if schema.is_current:
                return schema
            if newest is None:
                newest = schema
        if newest is None:
            raise UnknownSchemaError(schema_name)
        return newest

    async def list_latest(self, *, query: str | None = None) -> AsyncIterable[Schema]:
        """The latest version of every schema, in name-ascending order.

        "Latest" means the same thing as in `get_latest`, per name. `query` narrows the
        result to versions satisfying `matches_query`; `None` or blank selects everything.

        Filtering costs nothing extra here, since this already fetches each name's
        latest - so a backend overrides this to push the filter into the store, not to
        rescue work that this does badly.
        """
        async for schema_name in self.list_names():
            schema = await self.get_latest(schema_name)
            if matches_query(schema, query):
                yield schema

    async def list_predecessors(self, successor_url: str) -> AsyncIterable[Schema]:
        """All versions whose declared successor is `successor_url` (derived predecessors).

        Yielded in a stable order (name asc, version asc).
        """
        async for schema_name in self.list_names():
            versions = [schema async for schema in self.list_versions(schema_name)]
            for schema in sorted(versions, key=lambda s: s.version):
                if schema.has_successor(successor_url):
                    yield schema
