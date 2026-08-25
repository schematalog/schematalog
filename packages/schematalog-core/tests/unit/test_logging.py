"""Redaction for text that is printed rather than logged."""

import pytest

from schematalog.common.logging import REDACTED, redact


@pytest.mark.parametrize(
    "text",
    [
        "could not connect to postgresql://user:hunter2@host/db",
        "Bearer abcdefghijklmnop was rejected",
        "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1g",
    ],
)
def test_redact_masks_credential_shaped_text(text):
    """The CLI and a response body bypass the logging pipeline, so they need the same net."""
    cleaned = redact(text)
    assert REDACTED in cleaned
    for secret in ("hunter2", "abcdefghijklmnop", "eyJhbGciOiJIUzI1NiJ9"):
        assert secret not in cleaned


def test_redact_keeps_the_text_around_the_credential():
    """Whole-message replacement would discard the diagnosis along with the password."""
    cleaned = redact("could not connect to postgresql://user:hunter2@host/db")
    assert "could not connect to" in cleaned
    assert "host/db" in cleaned


def test_redact_leaves_ordinary_text_alone():
    message = "[Errno 111] Connect call failed ('127.0.0.1', 5432)"
    assert redact(message) == message
