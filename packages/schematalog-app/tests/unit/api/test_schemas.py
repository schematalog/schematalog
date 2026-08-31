"""Unit tests for the API request/response DTOs."""

from datetime import UTC, datetime
import uuid

from pydantic import ValidationError
import pytest

from schematalog.app.application.schema import SchemaView
from schematalog.app.presentation.api.schemas import (
    SchemaListResponse,
    SchemaRequest,
    SchemaResponse,
)

_DOCUMENT = {"$schema": "https://example.com/draft", "type": "object"}


# A fixed UUIDv7 so assertions can name an exact identifier.
_PUBLICATION_ID = uuid.UUID("01a02000-0000-7000-8000-000000000001")


def _view(
    description: str = "A test schema",
    deprecated: bool = False,
    successor: str | None = None,
) -> SchemaView:
    return SchemaView(
        name="smoke",
        version="1",
        description=description,
        document=dict(_DOCUMENT),
        publication_id=_PUBLICATION_ID,
        published_on=datetime(2026, 1, 1, tzinfo=UTC),
        deprecated=deprecated,
        successor=successor,
    )


def test_schema_request_accepts_schema_alias():
    body = SchemaRequest.model_validate(
        {"name": "smoke", "version": "1", "schema": {"type": "object"}}
    )
    assert body.json_schema == {"type": "object"}


def test_schema_request_accepts_field_name():
    body = SchemaRequest(name="smoke", version="1", json_schema={"type": "object"})
    assert body.json_schema == {"type": "object"}


def test_schema_request_rejects_invalid_name():
    with pytest.raises(ValidationError):
        SchemaRequest(name="has spaces", version="1", json_schema={})


def test_schema_response_from_view_flattens_value_objects():
    url = "https://example.com/api/schemas/smoke/versions/1"
    view = _view()
    response = SchemaResponse.from_view(view, view.document, url)
    assert response.name == "smoke"
    assert response.version == "1"
    assert response.canonical_url == url
    assert response.description == "A test schema"
    assert response.json_schema == {
        "$schema": "https://example.com/draft",
        "type": "object",
    }
    assert response.published_on == datetime(2026, 1, 1, tzinfo=UTC)
    assert response.publication_id == _PUBLICATION_ID


def test_schema_response_represents_an_empty_description_as_empty_text():
    view = _view(description="")
    response = SchemaResponse.from_view(view, view.document, "https://x/y")
    assert response.description == ""


def test_schema_response_serialises_to_flat_wire():
    view = _view()
    response = SchemaResponse.from_view(
        view, view.document, "https://example.com/api/schemas/smoke/versions/1"
    )
    wire = response.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert set(wire.keys()) == {
        "name",
        "version",
        "canonical_url",
        "description",
        "schema",
        "publication_id",
        "published_on",
        "deprecated",
    }
    assert wire["schema"] == {"$schema": "https://example.com/draft", "type": "object"}
    assert wire["deprecated"] is False


def test_schema_list_response_wraps_individuals():
    view = _view()
    response = SchemaListResponse(
        schemas=[
            SchemaResponse.from_view(
                view, view.document, "https://example.com/api/schemas/smoke/versions/1"
            )
        ],
    )
    assert len(response.schemas) == 1
    assert response.schemas[0].name == "smoke"
