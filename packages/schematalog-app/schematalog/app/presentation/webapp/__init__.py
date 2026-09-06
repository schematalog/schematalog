from datetime import UTC, datetime, timedelta
from http import HTTPStatus
import json
import re
from typing import Annotated, Any
import uuid

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from markupsafe import Markup, escape
from pydantic import BaseModel, ValidationError

from schematalog.app.application.exceptions import (
    DuplicateSchemaError,
    InvalidLabelError,
    InvalidSchemaError,
    InvalidSearchQueryError,
)
from schematalog.app.application.schema import (
    GetSchemaCommand,
    ListLatestCommand,
    ListPredecessorsCommand,
    ListVersionsCommand,
    PublishCommand,
    SchemaService,
    SchemaView,
)
from schematalog.app.presentation.helpers.property_type import render_property_type
from schematalog.app.presentation.helpers.urls import canonical_url_for, stamp_canonical_id
from schematalog.app.wiring.config import settings
from schematalog.app.wiring.factories import get_service

from .templates import templates

# Out of the OpenAPI specification entirely. The spec is the JSON API's contract, and
# these routes are none of it: they return HTML, they take form posts, and the pages
# themselves are free to change without anything having been promised about them. Left
# in, they showed up as an untagged "default" group of endpoints whose "Try it out"
# button returns a document rather than data, and any generated client grew methods for
# them. `/version` and `/health` are already excluded for the same reason.
router = APIRouter(include_in_schema=False)


def _build_template_schema(view: SchemaView, request: Request) -> tuple[dict[str, Any], str]:
    """Project a `SchemaView` onto the flat dict the templates read, plus its `$id` URL.

    Mirrors the old wire form (None fields omitted, so unguarded `{{ schema.x }}`
    renders empty rather than "None"); the document carries the stamped canonical `$id`.
    """
    url = canonical_url_for(view.name, view.version, request)
    document = stamp_canonical_id(
        view.document,
        canonical_url=url,
        title=view.name,
        description=view.description,
        deprecated=view.deprecated,
    )
    data: dict[str, Any] = {
        "name": view.name,
        "version": view.version,
        "schema": document,
        "deprecated": view.deprecated,
        "successor": str(view.successor) if view.successor is not None else None,
        "labels": view.labels,
    }
    if view.description:
        data["description"] = view.description
    data["published_on"] = view.published_on
    return data, url


@router.get("/", name="homepage")
async def homepage(request: Request):
    """Render the home page."""
    return templates.TemplateResponse(request=request, name="index.html.jinja")


@router.get("/schemas/", name="schemas_list")
async def schemas_list(
    request: Request,
    q: str = "",
    label: Annotated[list[str] | None, Query()] = None,
    service: SchemaService = Depends(get_service),
):
    """Render the schema list, narrowed by `q` and/or label when given.

    Both filters round-trip into the response so the page still shows what was asked
    for, and so the empty state can say which search found nothing rather than claiming
    the registry is empty. The labels in use come along too - they are the filter's
    affordance, one click applying what would otherwise have to be typed.
    """
    # The API answers an unusable query or label with 422; a browser gets a page instead,
    # because an error document is the wrong response to someone mistyping in a search
    # box. The length cap is the API's, applied here too so the two surfaces accept the
    # same queries.
    try:
        if len(q) > settings.MAX_QUERY_LENGTH:
            raise InvalidSearchQueryError  # noqa: TRY301
        schemas = [
            _build_template_schema(view, request)[0]
            async for view in service.list_latest_schemas(
                ListLatestCommand(query=q, labels=label)
            )
        ]
    except InvalidSearchQueryError, InvalidLabelError:
        schemas, valid = [], False
    else:
        valid = True
    return templates.TemplateResponse(
        request,
        "schemas.html.jinja",
        {
            "schemas": schemas,
            "query": q,
            "labels": label or [],
            "labels_in_use": [used async for used in service.list_labels()],
            "query_is_valid": valid,
            "max_query_length": settings.MAX_QUERY_LENGTH,
        },
    )


@router.get("/schemas/{schema_name}", name="schemas_detail")
async def schemas_detail(
    request: Request,
    schema_name: str,
    version: str = "",
    service: SchemaService = Depends(get_service),
):
    """Retrieve a version of a schema (the latest if none is selected)."""
    view = await service.get_schema(GetSchemaCommand(name=schema_name, version=version or None))
    serialized, url = _build_template_schema(view, request)
    all_versions = [
        v.version
        async for v in service.list_schema_versions(ListVersionsCommand(name=schema_name))
    ]
    # Derived predecessors (versions superseded by this one), linked to their webapp pages.
    predecessors = [
        {
            "name": predecessor.name,
            "version": predecessor.version,
            "url": request.url_for(
                "schemas_detail", schema_name=predecessor.name
            ).include_query_params(version=predecessor.version),
        }
        async for predecessor in service.list_schema_predecessors(
            ListPredecessorsCommand(successor_url=url)
        )
    ]
    return templates.TemplateResponse(
        request,
        "schema.html.jinja",
        {
            "current_version": version,
            "schema": serialized,
            "render_property_type": render_property_type,
            "all_versions": all_versions,
            "canonical_url": url,
            "metadata_url": str(
                request.url_for(
                    "get_schema_metadata", schema_name=view.name, version=view.version
                )
            ),
            "predecessors": predecessors,
        },
    )


class PublishForm(BaseModel):
    """The publish form's fields, exactly as the browser submits them.

    Every field is a plain optional string: a form must be able to round-trip whatever
    was typed back into the re-rendered page, so validation of names, versions and the
    document belongs in the handler (which turns a failure into an error message),
    never in this model.
    """

    name: str = ""
    version: str = ""
    description: str = ""
    labels: str = ""
    json_schema: str = ""


# A starter document for a blank publish form, so the editor opens on something valid
# and self-explanatory rather than an empty buffer.
_STARTER_DOCUMENT = json.dumps(
    {
        "type": "object",
        "properties": {"id": {"type": "string", "format": "uuid"}},
        "required": ["id"],
    },
    indent=2,
)


def _render_publish_response(
    request: Request,
    fields: dict[str, str],
    error: str | None = None,
    status_code: int = HTTPStatus.OK,
    based_on: str | None = None,
    labels_in_use: list[str] | None = None,
):
    """Render the publish form, echoing back what was submitted plus any error.

    `based_on` is the version a "publish a new version" form was seeded from; it only
    changes the heading, so the page can say what it is continuing from. `labels_in_use`
    feeds the label field's suggestions - the nudge towards reusing an existing
    spelling rather than coining `payments` beside `payment`.
    """
    return templates.TemplateResponse(
        request,
        "publish.html.jinja",
        {
            "fields": fields,
            "error": error,
            "based_on": based_on,
            "labels_in_use": labels_in_use or [],
        },
        status_code=status_code,
    )


_TRAILING_NUMBER = re.compile(r"(\d+)(\D*)$")


def _suggest_next_version(version: str) -> str:
    """Suggest the version after `version` by incrementing its last run of digits.

    Versions are free-form strings here (any `NAME_PATTERN` value), so this is a
    convenience for the common numeric cases - `1.0` -> `1.1`, `2.9` -> `2.10`,
    `v3` -> `v4` - and nothing more. A version carrying no digits at all gets `.1`
    appended (`beta` -> `beta.1`), which then chains: the next suggestion after that
    is `beta.2`. A dot rather than a space or any other separator because
    `NAME_PATTERN` admits only alphanumerics, `-`, `_` and `.` - a suggestion the
    server would reject is worse than none.

    It is only ever a *suggestion* in an editable field; publishing the same version
    twice is refused by the service either way.

    Args:
        version: The version being continued from.

    Returns:
        The suggested next version, or `""` if `version` is empty.
    """
    if not version:
        return ""
    match = _TRAILING_NUMBER.search(version)
    if match is None:
        return f"{version}.1"
    number, suffix = match.groups()
    return f"{version[: match.start(1)]}{int(number) + 1}{suffix}"


@router.get("/publish", name="schemas_publish")
async def schemas_publish(
    request: Request,
    name: str = "",
    version: str = "",
    service: SchemaService = Depends(get_service),
):
    """Render the schema publish form.

    With a `name`, the form is seeded from that existing version - the "publish a new
    version" path off the detail page - with the version suggestion bumped, since
    republishing the same one is always a conflict. Otherwise it opens blank.
    """
    labels_in_use = [used async for used in service.list_labels()]
    if not name:
        return _render_publish_response(
            request,
            {
                "name": "",
                "version": "1.0",
                "description": "",
                "labels": "",
                "json_schema": _STARTER_DOCUMENT,
            },
            labels_in_use=labels_in_use,
        )
    view = await service.get_schema(GetSchemaCommand(name=name, version=version or None))
    return _render_publish_response(
        request,
        {
            "name": view.name,
            "version": _suggest_next_version(view.version),
            "description": view.description,
            # Carried forward like the description: a new version starts label-less
            # otherwise, and quietly drops the schema from its groups (see DECISIONS.md).
            "labels": " ".join(view.labels),
            # The stored document, not the one the detail page shows: that one carries a
            # stamped canonical `$id`, which publishing strips anyway - showing it in the
            # editor would imply it is part of the document the author maintains.
            "json_schema": json.dumps(view.document, indent=2),
        },
        based_on=view.version,
        labels_in_use=labels_in_use,
    )


def _build_publish_command(fields: dict[str, str]) -> tuple[PublishCommand | None, str]:
    """Build a `PublishCommand` from the submitted fields, or explain the refusal.

    Args:
        fields: The stripped form values.

    Returns:
        `(command, "")` when the submission is usable, else `(None, message)` with a
        message written for the person who filled the form in.
    """
    try:
        document = json.loads(fields["json_schema"])
    except json.JSONDecodeError as exc:
        return None, f"The document is not valid JSON: {exc}."
    if not isinstance(document, dict):
        return None, "The document must be a JSON object."
    try:
        return (
            PublishCommand(
                name=fields["name"],
                version=fields["version"],
                json_schema=document,
                description=fields["description"],
                # Commas are accepted as separators too, so both habits parse; the
                # service does the folding, deduplication and refusing.
                labels=fields["labels"].replace(",", " ").split(),
            ),
            "",
        )
    except ValidationError:
        return None, (
            "Name and version are required, and may contain only letters, digits, "
            "'-', '_' and '.' (starting with a letter or digit)."
        )


@router.post("/publish", name="schemas_publish_submit")
async def schemas_publish_submit(
    request: Request,
    form: Annotated[PublishForm, Form()],
    service: SchemaService = Depends(get_service),
):
    """Publish the submitted document, then redirect to its schema page.

    Catches the errors a *form* can provoke and re-renders with the input intact - a
    browser filling in a form needs the page back, not the central handler's JSON.
    """
    fields = {
        "name": form.name.strip(),
        "version": form.version.strip(),
        "description": form.description.strip(),
        "labels": form.labels.strip(),
        "json_schema": form.json_schema,
    }
    command, error = _build_publish_command(fields)
    labels_in_use = [used async for used in service.list_labels()]
    if command is None:
        return _render_publish_response(
            request, fields, error, HTTPStatus.UNPROCESSABLE_ENTITY, labels_in_use=labels_in_use
        )
    try:
        view = await service.publish_schema(command)
    except InvalidLabelError:
        return _render_publish_response(
            request,
            fields,
            "Labels are separated by spaces, and each may contain only letters, "
            "digits, '-', '_' and '.'.",
            HTTPStatus.UNPROCESSABLE_ENTITY,
            labels_in_use=labels_in_use,
        )
    except InvalidSchemaError:
        # Covers both of the service's reasons - a document matching no metaschema, and a
        # field breaking a domain constraint. The exact cap lives in the domain, which
        # presentation cannot import, so the wording spans the two rather than quoting it.
        return _render_publish_response(
            request,
            fields,
            "The document does not conform to any supported JSON Schema metaschema, "
            "or a field is longer than allowed.",
            HTTPStatus.UNPROCESSABLE_ENTITY,
            labels_in_use=labels_in_use,
        )
    except DuplicateSchemaError:
        return _render_publish_response(
            request,
            fields,
            f"Version '{fields['version']}' of '{fields['name']}' already exists.",
            HTTPStatus.CONFLICT,
            labels_in_use=labels_in_use,
        )
    return RedirectResponse(
        str(
            request.url_for("schemas_detail", schema_name=view.name).include_query_params(
                version=view.version
            )
        ),
        status_code=HTTPStatus.SEE_OTHER,
    )
