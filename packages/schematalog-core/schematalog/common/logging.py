"""Structured logging: unclogger (JSON via structlog) plus a redaction safety net.

This is the one place logging is configured. The policy:

- `get_logger(name)` returns an `unclogger.Unclogger` that emits JSON; use it for
  *our* events (presentation/application, and domain where a rule needs a trace).
  We deliberately do not reroute uvicorn/FastAPI's own access logs through here -
  they already log requests; duplicating them adds noise, not signal.
- `LogContext` is a typed mapping of the identifier fields that may be bound to the
  context. The type checker rejects unknown keys, so a misspelled or contents-bearing
  field is a type error rather than a silent leak.
- `bind_context` / `clear_context` bind those identifiers (request id) at a
  request entry point so every downstream log inherits them without
  the call site repeating them.
- A `sanitary.StructlogSanitizer` processor redacts credential-shaped keys and values
  as a last-resort net. It is not a license to log secrets - it is the backstop for
  when one slips through.

`common` is layer-neutral, so `configure_logging` takes `debug` as an argument rather
than importing `wiring.config`; the composition root passes `settings.DEBUG`.
"""

import logging
import re
from typing import Final, TypedDict, Unpack

from sanitary import StructlogSanitizer
import unclogger

REDACTED: Final = "[REDACTED]"

# Value patterns are the primary net: they catch a credential-shaped *value* even
# under an innocuous field name. Matched against string values.
_FORBIDDEN_VALUE_PATTERNS: Final = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),  # bearer token
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT (PropelAuth)
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),  # credentials in a URL/DSN userinfo
)

# Field names are the secondary fallback for a sensitive value logged under an obvious
# name. Matched case-insensitively by exact name (not substring).
_FORBIDDEN_KEYS: Final = frozenset(
    {
        "password",
        "secret",
        "token",
        "access_token",
        "session_token",
        "pending_token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "set-cookie",
        "credentials",
    }
)

# Noisy third-party loggers pinned to WARNING; raise only when actively debugging.
# Uvicorn is deliberately absent - we leave its access/error logs as-is.
_THIRD_PARTY_LOGGERS: Final = (
    "sqlalchemy",
    "sqlalchemy.engine",
    "asyncio",
)

# `unknown_objects="deny"` is the runtime backstop: any object reaching the sanitizer
# without a `__sanitary_context__` hook is masked wholesale rather than walked via
# `vars()` (which would leak its every attribute). Scalars pass through untouched.
_sanitizer: Final = StructlogSanitizer(
    keys=_FORBIDDEN_KEYS,
    patterns=_FORBIDDEN_VALUE_PATTERNS,
    replacement=REDACTED,
    message=REDACTED,
    unknown_objects="deny",
)


class LogContext(TypedDict, total=False):
    """Identifier fields that may be bound to the logging context.

    Only identifiers belong here, never contents. Binding via `bind_context` is
    type-checked against this mapping, so an unknown or misspelled key is a type
    error rather than a silently-leaked field.

    Deliberately minimal (request correlation only): richer per-request attributes
    and spans are left to the planned OpenTelemetry instrumentation rather than
    hand-bound here.
    """

    request_id: str
    method: str
    path: str


def bind_context(**fields: Unpack[LogContext]) -> None:
    """Bind identifier fields to the logging context for all downstream logs.

    Call at a request entry point so every log line emitted while handling the
    request inherits the identifiers without repeating them.
    """
    unclogger.context_bind(**fields)


def clear_context(*keys: str) -> None:
    """Clear bound context fields, or all of them if no keys are named."""
    unclogger.context_clear(*keys)


def redact(text: str) -> str:
    """Mask credential-shaped substrings in text that is printed rather than logged.

    The sanitizer processor covers everything emitted through a logger, but the CLI
    writes to stdout and an HTTP handler writes to a response body, and neither passes
    through it. This applies the same value patterns so the definition of "looks like a
    credential" stays in one place.

    Substitutes each match in place rather than discarding the whole string, because the
    text around the credential is usually the diagnosis - a storage URL appears in a
    driver's connection error precisely when an operator most needs to read it.

    Args:
        text: The string about to be shown to someone.

    Returns:
        The string with every credential-shaped match replaced.
    """
    for pattern in _FORBIDDEN_VALUE_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


_configured = False


def configure_logging(*, debug: bool = False) -> None:
    """Configure process-wide structured logging. Idempotent; safe to call repeatedly.

    Registers the redaction processor, pins noisy third-party loggers to WARNING, and
    sets the root level from `debug`. Does not touch uvicorn's loggers.

    Args:
        debug: When true, emit DEBUG-level logs; otherwise INFO.
    """
    global _configured
    if _configured:
        return
    unclogger.add_processors(_sanitizer)
    for name in _THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    unclogger.set_level(logging.DEBUG if debug else logging.INFO)
    _configured = True


def get_logger(name: str) -> unclogger.Unclogger:
    """Return a structured logger.

    Args:
        name: The logger name; by convention `__name__`.

    Returns:
        An `Unclogger` usable like a standard library logger, emitting JSON.
    """
    return unclogger.get_logger(name)
