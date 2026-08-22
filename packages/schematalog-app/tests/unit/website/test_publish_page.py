"""The workspace publish page: the schema-editor form and its submit path."""

from http import HTTPStatus
import json
import re

from schematalog.app.presentation.webapp import _suggest_next_version
from schematalog.domain.schema import NAME_PATTERN

VALID_DOCUMENT = json.dumps({"type": "object", "properties": {"id": {"type": "string"}}})


def _form(**overrides):
    """A valid publish submission, with any field overridden."""
    return {
        "name": "customer",
        "version": "1.0",
        "description": "",
        "json_schema": VALID_DOCUMENT,
    } | overrides


def test_publish_page_renders_the_editor_form(client):
    response = client.get("/publish")
    assert response.status_code == HTTPStatus.OK
    # The textarea is the form field; the island upgrades it in place.
    assert "data-editor" in response.text
    assert 'name="json_schema"' in response.text
    # It opens on a starter document rather than an empty buffer.
    assert "&#34;type&#34;: &#34;object&#34;" in response.text


def test_publish_redirects_to_the_new_schema_page(client):
    response = client.post(
        "/publish", data=_form(description="A customer."), follow_redirects=False
    )
    assert response.status_code == HTTPStatus.SEE_OTHER
    assert response.headers["location"].endswith("/schemas/customer?version=1.0")

    page = client.get("/schemas/customer")
    assert page.status_code == HTTPStatus.OK
    assert "A customer." in page.text


def test_malformed_json_re_renders_the_form_with_the_input_intact(client):
    response = client.post("/publish", data=_form(json_schema="{not json"))
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "not valid JSON" in response.text
    # The typed document comes back so the edit is not lost.
    assert "{not json" in response.text


def test_a_non_object_document_is_refused(client):
    response = client.post("/publish", data=_form(json_schema="[1, 2]"))
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "must be a JSON object" in response.text


def test_an_invalid_name_re_renders_the_form(client):
    response = client.post("/publish", data=_form(name="not a name!"))
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "may contain only letters" in response.text
    assert "not a name!" in response.text


def test_a_document_matching_no_metaschema_is_refused(client):
    response = client.post("/publish", data=_form(json_schema=json.dumps({"type": "nonsense"})))
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "does not conform" in response.text


def test_republishing_the_same_version_is_a_conflict(client):
    client.post("/publish", data=_form())
    response = client.post("/publish", data=_form())
    assert response.status_code == HTTPStatus.CONFLICT
    assert "already exists" in response.text


def test_submitted_values_are_escaped_when_echoed_back(client):
    """A rejected submission is re-rendered; its input must not become live markup."""
    payload = '<script>alert("xss")</script>'
    response = client.post("/publish", data=_form(name=payload, json_schema="{bad"))
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert payload not in response.text
    assert "&lt;script&gt;" in response.text


def test_an_over_long_description_is_refused_not_crashed(client):
    """The domain caps the description; that cap must not escape as a raw pydantic error."""
    response = client.post("/publish", data=_form(description="x" * 70_000))
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_publishing_a_further_version_of_an_existing_schema(client):
    """The same form publishes a new version: type the existing name and a new version."""
    first = client.post("/publish", data=_form(version="1.0"), follow_redirects=False)
    assert first.status_code == HTTPStatus.SEE_OTHER
    second = client.post("/publish", data=_form(version="2.0"), follow_redirects=False)
    assert second.status_code == HTTPStatus.SEE_OTHER
    assert second.headers["location"].endswith("/schemas/customer?version=2.0")

    page = client.get("/schemas/customer")
    assert "2.0" in page.text and "1.0" in page.text


def test_suggest_next_version_bumps_the_trailing_number():
    assert _suggest_next_version("1.0") == "1.1"
    assert _suggest_next_version("2.9") == "2.10"
    assert _suggest_next_version("3") == "4"
    assert _suggest_next_version("v1") == "v2"
    assert _suggest_next_version("1.0-beta") == "1.1-beta"
    # No digits at all: append one, and keep chaining from there.
    assert _suggest_next_version("beta") == "beta.1"
    assert _suggest_next_version("beta.1") == "beta.2"
    assert _suggest_next_version("") == ""


def test_publish_form_seeds_from_an_existing_version(client):
    """The 'publish a new version' path off the detail page."""
    client.post("/publish", data=_form(description="A customer."))

    response = client.get("/publish?name=customer&version=1.0")
    assert response.status_code == HTTPStatus.OK
    assert "Publish a new version" in response.text
    assert 'value="customer"' in response.text
    # The version is bumped: republishing 1.0 would always conflict.
    assert 'value="1.1"' in response.text
    assert 'value="A customer."' in response.text
    assert "&#34;id&#34;" in response.text  # the stored document, in the editor


def test_seeded_form_shows_the_stored_document_not_the_stamped_one(client):
    """The detail page stamps a canonical `$id`; publishing strips it, so it must not
    appear in the editor as if the author maintained it."""
    client.post("/publish", data=_form())
    response = client.get("/publish?name=customer")
    # Scoped to the editor: the form's own help text mentions `$id`.
    document = re.search(r"<textarea[^>]*>(.*?)</textarea>", response.text, re.S)
    assert document is not None
    assert "$id" not in document.group(1)


def test_seeding_from_an_unknown_schema_is_a_404(client):
    assert client.get("/publish?name=nope").status_code == HTTPStatus.NOT_FOUND


def test_detail_page_offers_a_new_version_to_members(client, published):
    response = client.get(f"/schemas/{published['name']}")
    assert "Publish a new version" in response.text
    assert f"name={published['name']}" in response.text


def test_seeded_form_warns_that_renaming_starts_a_new_schema(client):
    """The name arrives prefilled and editable, so the consequence must be spelled out."""
    client.post("/publish", data=_form())
    response = client.get("/publish?name=customer")
    assert "changing it publishes a separate" in response.text.lower()


def test_blank_form_explains_what_the_name_does(client):
    response = client.get("/publish")
    assert "adds a version to it" in response.text


def test_every_suggested_version_is_one_the_server_would_accept():
    """A suggestion the domain rejects is worse than none - note NAME_PATTERN has no space."""
    for version in ("1.0", "2.9", "v3", "beta", "2026-01", "a_b", "1.0-beta"):
        suggestion = _suggest_next_version(version)
        assert re.fullmatch(NAME_PATTERN, suggestion), (version, suggestion)
