from datetime import datetime
from http import HTTPStatus

import pytest
from starlette.testclient import TestClient
import yaml

from schematalog.app.application.schema import MAX_QUERY_LENGTH

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


@pytest.mark.parametrize(
    "query",
    (
        "bill ing",
        "two words",
        "ordér",
        "İ",
        "\U0001f600",
        "'; DROP TABLE schema; --",
        "' OR 1=1 --",
        '"',
        "or\x00der",
        "50%",
        "a\\b",
        "or\nder",
        "<script>alert(1)</script>",
        "../../etc/passwd",
    ),
    ids=(
        "internal space",
        "two words",
        "non-ascii",
        "turkish dotted I",
        "emoji",
        "sql injection",
        "sql tautology",
        "double quote",
        "null byte",
        "percent",
        "backslash",
        "newline",
        "script tag",
        "path traversal",
    ),
)
def test_listing_schemas_rejects_a_query_no_name_could_contain(client, query):
    """Rejected rather than answered with an empty result.

    Search matches names, so a query holding a character no name can hold cannot match
    anything. Saying so beats returning nothing and leaving the caller to guess why -
    and it keeps strings no database can store from reaching a driver at all. A null
    byte is not valid in PostgreSQL `text`, so before this was validated the same
    request answered `200 []` on SQLite and raised on PostgreSQL.
    """
    assert (
        client.get("/api/schemas", params={"q": query}).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )


@pytest.mark.parametrize(
    "query",
    ("billing.invoice", "billing", "BILLING", "order-2", "a_b", "1", ".", "-", "_", ""),
    ids=(
        "full name",
        "prefix",
        "upper case",
        "hyphen",
        "underscore",
        "digit",
        "dot alone",
        "hyphen alone",
        "underscore alone",
        "empty",
    ),
)
def test_listing_schemas_accepts_every_character_a_name_may_contain(client, query):
    """The accepting half of the rule: anything a name can hold is searchable."""
    assert client.get("/api/schemas", params={"q": query}).status_code == HTTPStatus.OK


def test_listing_schemas_refuses_a_query_longer_than_the_cap(client):
    """A resource guard, not a semantic one.

    No real search approaches the cap, so refusing past it costs nobody a legitimate
    query while keeping an unbounded string out of a `LIKE` pattern.
    """
    response = client.get("/api/schemas", params={"q": "x" * (MAX_QUERY_LENGTH + 1)})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_listing_schemas_accepts_a_query_at_the_cap(client):
    response = client.get("/api/schemas", params={"q": "x" * MAX_QUERY_LENGTH})
    assert response.status_code == HTTPStatus.OK
    assert response.json()["schemas"] == []


@pytest.mark.parametrize("query", ("  order  ", "   ", "\t"), ids=("padded", "spaces", "tab"))
def test_listing_schemas_accepts_surrounding_whitespace(client, query):
    """Whitespace around a query is a typing artifact; whitespace-only is no query."""
    assert client.get("/api/schemas", params={"q": query}).status_code == HTTPStatus.OK


def test_listing_schemas_accepts_a_query_padded_with_spaces(client, example_schema):
    """Surrounding whitespace is trimmed rather than matched on."""
    client.post("/api/schemas", json=example_schema)
    response = client.get("/api/schemas", params={"q": f"  {example_schema['name']}  "})
    assert [s["name"] for s in response.json()["schemas"]] == [example_schema["name"]]


@pytest.mark.parametrize("field", ("name", "version"))
def test_publishing_rejects_an_identifier_longer_than_the_column(client, example_schema, field):
    """Bounded in the domain, so every backend refuses it the same way.

    The SQL column is `VARCHAR(256)`, which PostgreSQL enforces and SQLite ignores - so
    while the length lived only in the schema, a 300-character name was stored happily
    by three backends and answered with a 500 by the fourth.
    """
    response = client.post("/api/schemas", json={**example_schema, field: "a" * 300})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
