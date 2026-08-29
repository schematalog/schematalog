from datetime import datetime
from http import HTTPStatus

import pytest
from starlette.testclient import TestClient
import yaml

API_URL_ROOT = "api/"


def test_openapi_json_is_served(test_app):
    with TestClient(test_app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == HTTPStatus.OK
    spec = response.json()
    assert spec["info"]["title"] == "Schematalog"
    assert "/api/schemas" in spec["paths"]


@pytest.mark.filterwarnings("ignore:Unsupported application/yaml mimetype")
def test_openapi_yaml_is_served(test_app):
    with TestClient(test_app) as client:
        response = client.get("/openapi.yaml")

    assert response.status_code == HTTPStatus.OK
    assert "application/yaml" in response.headers["content-type"]
    assert yaml.safe_load(response.content)["info"]["title"] == "Schematalog"


def test_api_docs_are_served(test_app):
    with TestClient(test_app) as client:
        response = client.get("/docs")

    assert response.status_code == HTTPStatus.OK
    assert "text/html" in response.headers["content-type"]


async def test_schema_is_published(client, example_schema):
    response = client.post(f"/{API_URL_ROOT}schemas", json=example_schema)

    assert response.status_code == HTTPStatus.CREATED
    assert response.headers["content-type"] == "application/json"

    response_dict = response.json()
    assert response_dict["published_on"] is not None
    assert isinstance(datetime.fromisoformat(response_dict["published_on"]), datetime)


async def test_schema_version_is_required(client, example_schema):
    del example_schema["version"]
    response = client.post(f"/{API_URL_ROOT}schemas", json=example_schema)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_attempt_to_publish_duplicate_schema_returns_error(client, example_schema):
    assert (
        client.post(f"/{API_URL_ROOT}schemas", json=example_schema).status_code
        == HTTPStatus.CREATED
    )
    assert (
        client.post(f"/{API_URL_ROOT}schemas", json=example_schema).status_code
        == HTTPStatus.CONFLICT
    )


async def test_schema_by_name_redirects_to_latest_version(client, example_schema):
    """`/schemas/{name}` has no document of its own — it redirects to the canonical
    URL of the latest version (which is fully identified by name + version)."""
    assert (
        client.post(f"/{API_URL_ROOT}schemas", json=example_schema).status_code
        == HTTPStatus.CREATED
    )
    redirect = client.get(f"/{API_URL_ROOT}schemas/person-schema", follow_redirects=False)

    assert redirect.status_code == HTTPStatus.FOUND
    assert redirect.headers["location"].endswith(
        f"/{API_URL_ROOT}schemas/person-schema/versions/1.2"
    )


async def test_json_schema_is_retrieved(client, example_schema):
    created = client.post(f"/{API_URL_ROOT}schemas", json=example_schema)
    assert created.status_code == HTTPStatus.CREATED

    response = client.get(f"/{API_URL_ROOT}schemas/person-schema/versions/1.2")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"
    assert response.json() == created.json()["schema"]


async def test_forwarded_proto_yields_https_canonical_id(client, example_schema):
    """Behind Fly's TLS-terminating edge the app is reached over plain HTTP; the
    `X-Forwarded-Proto` header (honoured by ProxyHeadersMiddleware) must make the
    canonical `$id` https rather than http."""
    client.post(f"/{API_URL_ROOT}schemas", json=example_schema)

    plain = client.get(f"/{API_URL_ROOT}schemas/person-schema/versions/1.2")
    forwarded = client.get(
        f"/{API_URL_ROOT}schemas/person-schema/versions/1.2",
        headers={"X-Forwarded-Proto": "https"},
    )

    assert plain.json()["$id"].startswith("http://")
    assert forwarded.json()["$id"].startswith("https://")


async def test_unknown_schema_returns_error(client):
    response = client.get(f"/{API_URL_ROOT}schemas/snafu")
    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_unknown_version_returns_error(client, example_schema):
    assert (
        client.post(f"/{API_URL_ROOT}schemas", json=example_schema).status_code
        == HTTPStatus.CREATED
    )
    assert (
        client.get(f"/{API_URL_ROOT}schemas/person-schema/versions/1.2").status_code
        == HTTPStatus.OK
    )
    assert (
        client.get(f"/{API_URL_ROOT}schemas/person-schema/versions/99.9").status_code
        == HTTPStatus.NOT_FOUND
    )


async def test_incompatible_schema_is_rejected(client, example_schema):
    example_schema["schema"] = {"type": "not-a-valid-type"}
    response = client.post(f"/{API_URL_ROOT}schemas", json=example_schema)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_unknown_json_schema_version_returns_error(client):
    response = client.get(f"/{API_URL_ROOT}schemas/snafu/versions/9.9")
    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_multiple_schemas_are_retrieved(client, example_schema):
    schemas_count = 4
    for index in range(schemas_count):
        response = client.post(
            f"/{API_URL_ROOT}schemas", json={**example_schema, "name": f"person-schema-{index}"}
        )
        assert response.status_code == HTTPStatus.CREATED

    response = client.get(f"/{API_URL_ROOT}schemas")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"

    read_schemas = response.json()
    assert len(read_schemas["schemas"]) == schemas_count
    for index, schema in enumerate(read_schemas["schemas"]):
        assert schema["name"] == f"person-schema-{index}"


async def test_all_versions_of_a_schema_are_returned(client, example_schema):
    schemas_count = 4
    schema_name = example_schema["name"]
    for index in range(schemas_count):
        response = client.post(
            f"/{API_URL_ROOT}schemas", json={**example_schema, "version": str(index)}
        )
        assert response.status_code == HTTPStatus.CREATED

    # publish another schema to ensure it's not retrieved
    assert (
        client.post(
            f"/{API_URL_ROOT}schemas", json={**example_schema, "name": "dummy_schema"}
        ).status_code
        == HTTPStatus.CREATED
    )

    response = client.get(f"/{API_URL_ROOT}schemas/{schema_name}/versions")
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"

    read_schemas = response.json()
    assert len(read_schemas["schemas"]) == schemas_count
    expected_versions = sorted(map(str, range(schemas_count)), reverse=True)
    for index, schema in enumerate(read_schemas["schemas"]):
        assert schema["name"] == schema_name
        assert schema["version"] == expected_versions[index]


def test_listing_schemas_filters_by_a_name_query(client, example_schema):
    """`?q=` narrows the collection rather than being a separate search resource."""
    for name in ("billing.invoice", "billing.payment", "shipping.parcel"):
        client.post("/api/schemas", json={**example_schema, "name": name})

    response = client.get("/api/schemas", params={"q": "billing"})

    assert response.status_code == HTTPStatus.OK
    assert [s["name"] for s in response.json()["schemas"]] == [
        "billing.invoice",
        "billing.payment",
    ]


def test_listing_schemas_ignores_a_blank_query(client, example_schema):
    """An empty search box selects everything, rather than nothing."""
    client.post("/api/schemas", json=example_schema)

    for params in ({}, {"q": ""}, {"q": "   "}):
        response = client.get("/api/schemas", params=params)
        assert [s["name"] for s in response.json()["schemas"]] == [example_schema["name"]]


def test_listing_schemas_keeps_its_order_when_filtered(client, example_schema):
    """Filtered, not ranked: the order is the same with a query as without one."""
    for name in ("gamma.one", "alpha.one", "beta.one"):
        client.post("/api/schemas", json={**example_schema, "name": name})

    response = client.get("/api/schemas", params={"q": "one"})

    assert [s["name"] for s in response.json()["schemas"]] == [
        "alpha.one",
        "beta.one",
        "gamma.one",
    ]
