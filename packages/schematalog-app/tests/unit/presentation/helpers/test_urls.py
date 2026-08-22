"""Unit tests for canonical-`$id` stamping (the policy relocated from the domain)."""

from schematalog.app.presentation.helpers.urls import stamp_canonical_id

_URL = "https://example.com/api/schemas/smoke/versions/1"


def test_stamps_id_and_fills_title_and_description_defaults():
    result = stamp_canonical_id(
        {"type": "object"}, canonical_url=_URL, title="smoke", description="A schema."
    )
    assert result["$id"] == _URL
    assert result["title"] == "smoke"
    assert result["description"] == "A schema."


def test_preserves_existing_title_and_description():
    result = stamp_canonical_id(
        {"title": "Kept", "description": "Kept too"},
        canonical_url=_URL,
        title="smoke",
        description="Ignored",
    )
    assert result["title"] == "Kept"
    assert result["description"] == "Kept too"


def test_omits_description_when_none():
    result = stamp_canonical_id(
        {"type": "object"}, canonical_url=_URL, title="smoke", description=None
    )
    assert "description" not in result


def test_does_not_mutate_input():
    document = {"type": "object"}
    stamp_canonical_id(document, canonical_url=_URL, title="smoke", description="x")
    assert document == {"type": "object"}


def test_stamps_deprecated_when_true():
    result = stamp_canonical_id(
        {"type": "object"}, canonical_url=_URL, title="smoke", description=None, deprecated=True
    )
    assert result["deprecated"] is True


def test_removes_deprecated_when_false():
    # The domain flag is canonical: a stale `deprecated` in the document is reconciled away.
    result = stamp_canonical_id(
        {"deprecated": True},
        canonical_url=_URL,
        title="smoke",
        description=None,
        deprecated=False,
    )
    assert "deprecated" not in result
