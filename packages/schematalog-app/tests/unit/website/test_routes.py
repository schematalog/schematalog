from http import HTTPStatus

from schematalog.app.presentation import app
from schematalog.app.presentation.helpers import buildinfo


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


def test_home_page_title_is_just_the_site_name(client):
    """Home has nothing to add, so it does not repeat itself.

    The base template appends " - Schematalog" only when a page contributes a title
    of its own; the home page leaves the block empty.
    """
    assert "<title>Schematalog</title>" in client.get("/").text


def test_page_titles_lead_with_the_page(client, published):
    """A tab label truncates from the right, so the distinguishing part comes first."""
    assert "<title>Publish a schema - Schematalog</title>" in client.get("/publish").text
    assert "<title>All schemas - Schematalog</title>" in client.get("/schemas/").text

    detail = client.get(f"/schemas/{published['name']}").text
    assert f"<title>{published['name']} v{published['version']} - Schematalog</title>" in detail


def test_footer_links_to_the_documentation_and_the_source(client):
    """Everything the app can tell you about itself is reachable from any page."""
    footer = client.get("/").text
    assert buildinfo.DOCS_URL in footer
    assert buildinfo.REPOSITORY_URL in footer
    assert 'href="http://testserver/docs"' in footer
    assert 'href="http://testserver/openapi.json"' in footer


def test_the_two_routes_to_the_api_reference_agree(client):
    """One destination, named and behaving one way wherever it is offered.

    The home page called it "API documentation" and the footer "API reference", and
    only one of them opened a new tab.
    """
    home = client.get("/").text
    assert "API documentation" not in home
    assert home.count("API reference") == 2


def test_the_header_mark_takes_the_page_colour(client):
    """Inlined, not linked, so it cannot disagree with the theme the reader chose.

    A linked SVG resolves `prefers-color-scheme` against the operating system, which
    is a different question from which theme this page is showing.
    """
    header = client.get("/").text
    assert 'fill="currentColor"' in header
    assert 'aria-label="Schematalog"' in header


def test_the_favicon_is_a_square_vector_with_a_touch_icon_beside_it(client):
    """The PNG it replaces was 372x306, so every square favicon slot squashed it."""
    head = client.get("/").text
    assert '<link rel="icon" href="/static/schematalog-icon.svg" type="image/svg+xml">' in head
    assert '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">' in head


def test_every_new_tab_link_says_so(client, published):
    """A link that leaves for a new tab announces it rather than surprising the reader.

    Checked structurally rather than per-link: the rule is that `target="_blank"` and
    the note travel together, so a link added later without one is caught.
    """
    for path in ("/", "/schemas/", f"/schemas/{published['name']}"):
        page = client.get(path).text
        assert page.count('target="_blank"') == page.count("(opens in a new tab)"), path


def test_the_page_does_not_pin_a_colour_theme(client):
    """The theme is resolved per reader, so the markup must not decide it.

    A `data-theme` baked into the template would win over both the stored preference
    and the system setting, which is how this page was stuck in light mode.
    """
    html = client.get("/").text
    assert 'data-theme="light"' not in html[: html.index("<head>")]
    assert "schematalog-theme" in html[: html.index("</head>")], "no pre-paint resolution"


def test_the_spec_describes_the_json_api_and_nothing_else(client):
    """The HTML pages are not part of the API contract, so they are not in the contract.

    They returned documents rather than data, promised nothing about their shape, and
    arrived in the generated reference as an untagged "default" group.
    """
    spec = client.get("/openapi.json").json()
    assert [tag["name"] for tag in spec["tags"]] == ["Schemas"]
    assert all(path.startswith("/api/") for path in spec["paths"]), spec["paths"].keys()
    for operations in spec["paths"].values():
        for operation in operations.values():
            assert operation["tags"] == ["Schemas"]


def test_the_mark_strokes_only_its_inner_rules(client):
    """The surround is a filled shape, so stroking it draws a second, fatter outline.

    It kept a `stroke-width` from the font it was converted out of, which drew nothing
    until a stroke colour was inherited from above and then thickened it well past the
    rules inside.
    """
    mark = client.get("/").text
    mark = mark[mark.index('aria-label="Schematalog"') :]
    mark = mark[: mark.index("</svg>")]
    assert "stroke-width:9" not in mark, "the leftover font stroke width is back"
    assert mark.count('stroke="currentColor"') == 1, "only the bars group is stroked"
