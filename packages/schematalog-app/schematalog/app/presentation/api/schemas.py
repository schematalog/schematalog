"""Request and response models for the JSON API.

Wire-shaped DTOs that FastAPI sees on the route boundary — deliberately flat.
They map from the application's `SchemaView` (never the domain entity) via
`SchemaResponse.from_view`, so presentation depends only on the application layer.
"""

from datetime import datetime
from typing import Annotated, Any
import uuid

from pydantic import AnyUrl, ConfigDict, Field

from schematalog.app.application.schema import (
    SchemaName,
    SchemaVersion,
    SchemaView,
)
from schematalog.common.models import FrozenModel


class SchemaRequest(FrozenModel):
    """Request body for `POST /api/schemas`."""

    # validate_by_name/validate_by_alias let construction work via either `schema` (alias) or `json_schema`.
    model_config = ConfigDict(frozen=True, validate_by_name=True, validate_by_alias=True)

    name: Annotated[SchemaName, Field(description="Unique name of the schema.")]
    version: Annotated[SchemaVersion, Field(description="Version of the schema.")]
    description: Annotated[str | None, Field(description="Description of the schema.")] = None
    json_schema: Annotated[
        dict[str, Any], Field(alias="schema", description="The JSON Schema document.")
    ]


class SchemaMetadataRequest(FrozenModel):
    """Request body for `PATCH /api/schemas/{name}/versions/{version}`.

    A partial update of *mutable* metadata only; omitted fields are left unchanged.
    Immutable fields (name/version/schema/publication_id) are deliberately absent and
    unknown fields are rejected, so the request cannot alter the schema's identity
    or definition.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    deprecated: Annotated[
        bool | None,
        Field(description="New deprecation flag; omit to leave it unchanged."),
    ] = None
    successor: Annotated[
        AnyUrl | None,
        Field(
            description=(
                "URI of the version that supersedes this one; null clears it, "
                "omit to leave it unchanged."
            )
        ),
    ] = None


class SchemaResponse(FrozenModel):
    """Response model for a stored schema."""

    model_config = ConfigDict(frozen=True, validate_by_name=True, validate_by_alias=True)

    name: Annotated[SchemaName, Field(description="Unique name of the schema.")]
    version: Annotated[SchemaVersion, Field(description="Version of the schema.")]
    canonical_url: Annotated[
        str,
        Field(description="The schema's permalink — also stamped as `$id` inside `schema`."),
    ]
    description: Annotated[str | None, Field(description="Description of the schema.")] = None
    json_schema: Annotated[
        dict[str, Any], Field(alias="schema", description="The JSON Schema document.")
    ]
    publication_id: Annotated[
        uuid.UUID,
        Field(description="Opaque publication identifier; a stable cursor for pagination."),
    ]
    published_on: Annotated[datetime, Field(description="When this version was published.")]
    """Derived from `publication_id` rather than stored, so the two cannot disagree.
    Millisecond resolution."""
    deprecated: Annotated[bool, Field(description="Whether this version is deprecated.")]
    successor: Annotated[
        str | None, Field(description="URI of the version that supersedes this one, if any.")
    ] = None

    @classmethod
    def from_view(
        cls, view: SchemaView, document: dict[str, Any], canonical_url: str
    ) -> SchemaResponse:
        """Build the wire response from a `SchemaView` and its `$id`-stamped document."""
        return cls(
            name=view.name,
            version=view.version,
            canonical_url=canonical_url,
            description=view.description,
            json_schema=document,
            publication_id=view.publication_id,
            published_on=view.published_on,
            deprecated=view.deprecated,
            successor=str(view.successor) if view.successor is not None else None,
        )


class SchemaListResponse(FrozenModel):
    """Response model for a list of schemas."""

    schemas: Annotated[list[SchemaResponse], Field(description="The schemas in this response.")]
