"""JSON API for the schema catalogue."""

from http import HTTPStatus
from typing import Annotated, Any
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse

from schematalog.app.application.schema import (
    GetSchemaCommand,
    ListLatestCommand,
    ListPredecessorsCommand,
    ListVersionsCommand,
    MetadataUpdateCommand,
    PublishCommand,
    SchemaService,
    SchemaView,
)
from schematalog.app.presentation.api.schemas import (
    SchemaListResponse,
    SchemaMetadataRequest,
    SchemaRequest,
    SchemaResponse,
)
from schematalog.app.presentation.helpers.urls import (
    canonical_url_for,
    resolve_successor,
    stamp_canonical_id,
)
from schematalog.app.wiring.factories import get_service

# Tagged for the reader of the generated reference, who sees the tag as the section
# heading over these operations. "Schemas" names the resource they act on; the old
# "json-schema" named the format of one field of it, which grouped nothing.
router = APIRouter(prefix="/api", tags=["Schemas"])


def _to_response(view: SchemaView, request: Request) -> SchemaResponse:
    """Stamp the canonical `$id` into the document and project the view onto the wire DTO."""
    url = canonical_url_for(view.name, view.version, request)
    document = stamp_canonical_id(
        view.document,
        canonical_url=url,
        title=view.name,
        description=view.description,
        deprecated=view.deprecated,
    )
    return SchemaResponse.from_view(view, document, url)


@router.get("/schemas", response_model=SchemaListResponse, response_model_exclude_none=True)
async def get_schemas(
    request: Request,
    service: SchemaService = Depends(get_service),
    q: Annotated[
        str | None,
        Query(
            description=(
                "Narrow the listing to schemas whose name contains this, ignoring case. "
                "Matching is a plain substring: it does not stem, spell-correct or rank, "
                "and results keep their name order whether or not a query is given."
            )
        ),
    ] = None,
) -> SchemaListResponse:
    """Retrieve the latest versions of all published schemas, optionally filtered.

    A query parameter on the collection rather than a separate search resource: this
    narrows the same listing, in the same order, returning the same representation.
    """
    return SchemaListResponse(
        schemas=[
            _to_response(view, request)
            async for view in service.list_latest_schemas(ListLatestCommand(query=q))
        ]
    )


@router.post(
    "/schemas",
    status_code=HTTPStatus.CREATED,
    response_model=SchemaResponse,
    response_model_exclude_none=True,
)
async def publish_schema(
    body: SchemaRequest,
    request: Request,
    response: Response,
    service: SchemaService = Depends(get_service),
) -> SchemaResponse:
    """Publish a new schema version, returning a conflict if it already exists."""
    created = await service.publish_schema(
        PublishCommand(
            name=body.name,
            version=body.version,
            json_schema=body.json_schema,
            description=body.description,
        )
    )
    result = _to_response(created, request)
    response.headers["Location"] = result.canonical_url
    return result


@router.get(
    "/schemas/{schema_name}",
    status_code=HTTPStatus.FOUND,
    response_class=RedirectResponse,
)
async def get_schema(
    schema_name: str,
    request: Request,
    service: SchemaService = Depends(get_service),
) -> RedirectResponse:
    """Redirect to the canonical URL of the schema's latest version.

    A schema is only fully identified by `(name, version)`, so the name on its own
    has no document of its own to return — it points at whichever version is latest.
    """
    latest = await service.get_schema(GetSchemaCommand(name=schema_name))
    return RedirectResponse(
        url=canonical_url_for(latest.name, latest.version, request),
        status_code=HTTPStatus.FOUND,
    )


@router.get(
    "/schemas/{schema_name}/versions",
    response_model=SchemaListResponse,
    response_model_exclude_none=True,
)
async def get_schema_versions(
    schema_name: str, request: Request, service: SchemaService = Depends(get_service)
) -> SchemaListResponse:
    """Retrieve all versions of a published schema, newest first."""
    versions = [
        _to_response(view, request)
        async for view in service.list_schema_versions(ListVersionsCommand(name=schema_name))
    ]
    return SchemaListResponse(schemas=versions)


@router.get("/schemas/{schema_name}/versions/{version}", name="get_json_schema")
async def get_json_schema(
    schema_name: str,
    version: str,
    request: Request,
    response: Response,
    service: SchemaService = Depends(get_service),
) -> dict[str, Any]:
    """The canonical URL for a schema version's JSON Schema document."""
    view = await service.get_schema(GetSchemaCommand(name=schema_name, version=version))
    url = canonical_url_for(view.name, view.version, request)
    # RFC 5829 link relations: the superseding version, and the versions this one
    # supersedes (predecessors are derived - whoever declares this URL as their successor).
    links: list[str] = []
    if view.successor is not None:
        links.append(f'<{view.successor}>; rel="successor-version"')
    async for pred in service.list_schema_predecessors(
        ListPredecessorsCommand(successor_url=url)
    ):
        pred_url = canonical_url_for(pred.name, pred.version, request)
        links.append(f'<{pred_url}>; rel="predecessor-version"')
    if links:
        response.headers["Link"] = ", ".join(links)
    return stamp_canonical_id(
        view.document,
        canonical_url=url,
        title=view.name,
        description=view.description,
        deprecated=view.deprecated,
    )


@router.patch(
    "/schemas/{schema_name}/versions/{version}",
    response_model=SchemaResponse,
    response_model_exclude_none=True,
)
async def update_schema_metadata(
    schema_name: str,
    version: str,
    body: SchemaMetadataRequest,
    request: Request,
    service: SchemaService = Depends(get_service),
) -> SchemaResponse:
    """Update a schema version's mutable metadata (owner only).

    Carries `deprecated` and `successor`; immutable fields cannot be changed. An
    internal successor that is self-referential or missing returns 422. The successor is
    tri-state (omit = leave, null = clear, value = set): only when it is present in the
    request body do we resolve it and carry it on the command. All error outcomes
    (404/422/401/403) are mapped centrally by the app-level handlers.
    """
    command_args: dict[str, Any] = {
        "name": schema_name,
        "version": version,
        "deprecated": body.deprecated,
    }
    if "successor" in body.model_fields_set:
        url = str(body.successor) if body.successor is not None else None
        successor, target = resolve_successor(url, request)
        command_args["successor"] = successor
        command_args["successor_target"] = target
    updated = await service.update_schema_metadata(MetadataUpdateCommand(**command_args))
    return _to_response(updated, request)
