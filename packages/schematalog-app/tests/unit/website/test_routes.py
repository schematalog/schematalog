from http import HTTPStatus

from schematalog.app.presentation import app


def test_homepage_renders(client):
    response = client.get("/")
    assert response.status_code == HTTPStatus.OK
    assert "text/html" in response.headers["content-type"]


def test_footer_shows_version(client):
    response = client.get("/")
    assert f"version {app.version}" in response.text


def test_schemas_list_renders(client, published):
    response = client.get("/schemas/")
    assert response.status_code == HTTPStatus.OK
    assert published["name"] in response.text


def test_schema_detail_renders(client, published):
    response = client.get(f"/schemas/{published['name']}")
    assert response.status_code == HTTPStatus.OK
    assert published["version"] in response.text


def test_unknown_schema_detail_returns_404(client):
    response = client.get("/schemas/does-not-exist")
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_publishing_does_not_live_under_the_schema_namespace(client):
    """The publish page is at `/publish`, deliberately not `/schemas/new`.

    `/schemas/{name}` is a user-chosen namespace, so a `/schemas/new` route would
    permanently shadow a schema legitimately named "new".
    """
    assert client.get("/schemas/new").status_code == HTTPStatus.NOT_FOUND


def test_lifecycle_metadata_renders_in_detail(client, example_schema):
    """Temporary UI surfaces the new lifecycle metadata: deprecated badge, successor
    link, and derived predecessor links (display-only; guides the real UI)."""
    name = example_schema["name"]
    base = "http://testserver/api/schemas"
    for version in ("1.2", "2.0"):
        client.post(
            "/api/schemas",
            json={**example_schema, "version": version},
        )
    # 1.2 is deprecated and superseded by 2.0.
    client.patch(
        f"/api/schemas/{name}/versions/1.2",
        json={"deprecated": True, "successor": f"{base}/{name}/versions/2.0"},
    )

    old = client.get(f"/schemas/{name}?version=1.2").text
    assert "This version is deprecated" in old
    assert "Superseded by" in old
    assert f"{base}/{name}/versions/2.0" in old

    new = client.get(f"/schemas/{name}?version=2.0").text
    assert "Supersedes" in new
    assert f"/schemas/{name}?version=1.2" in new  # predecessor links to its webapp page


def test_schema_detail_renders_highlighted_code(client, published):
    """The format tabs are syntax-highlighted server-side (no JS, no bundle cost)."""
    response = client.get(f"/schemas/{published['name']}")
    assert 'class="hl"' in response.text
    # Each tab anchors its line spans separately, so the ids stay unique on the page.
    for anchor in ("json", "yaml", "pydantic", "avro"):
        assert f'id="{anchor}-line-1"' in response.text


def test_highlighted_code_keeps_its_copy_target(client, published):
    """The copy button reads `textContent`, so it must still wrap the code block."""
    response = client.get(f"/schemas/{published['name']}")
    assert 'id="code-json"' in response.text
    assert 'data-copy="code-json"' in response.text
