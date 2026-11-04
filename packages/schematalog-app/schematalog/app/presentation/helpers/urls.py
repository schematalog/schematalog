"""Canonical-`$id` construction and injection, shared by the API and the Web UI.

Builds a schema version's HTTP permalink and stamps it into the document as `$id`.
Lives in presentation because it depends on the app's routing (`request.url_for`);
future link-relation URLs (`successor-version`, `version-history`, ...) belong here
too. Operates on the application's `SchemaView` vocabulary, never the domain entity.
"""

import re
from typing import Any
from urllib.parse import urlparse

from fastapi import Request

from schematalog.app.application.schema import (
    SchemaIdentity,
    SchemaName,
    SchemaVersion,
    SuccessorReference,
)

# Path shape of `get_json_schema` (with the name/version pattern), for recognising a
# successor URL that points back at this registry.
_INTERNAL_PATH = re.compile(
    r"^/api/schemas/(?P<name>[0-9a-zA-Z][0-9a-zA-Z\-_.]*)"
    r"/versions/(?P<version>[0-9a-zA-Z][0-9a-zA-Z\-_.]*)$"
)


def canonical_url_for(name: SchemaName, version: SchemaVersion, request: Request) -> str:
    """Build the canonical URL of a schema version - its `$id` and registry permalink.

    Takes a bare `(name, version)` rather than a whole view so it can address *any*
    version (e.g. a future `successor-version` link), not just the one in hand. The
    URL depends on the `get_json_schema` route, which is why it lives in presentation.
    """
    return str(request.url_for("get_json_schema", schema_name=name, version=version))


def resolve_successor(
    url: str | None, request: Request
) -> tuple[SuccessorReference | None, SchemaIdentity | None]:
    """Resolve a submitted successor URL into a stored reference + optional internal target.

    A URL pointing at this registry's own `get_json_schema` route is *internal*: it is
    canonicalised (re-emitted via `canonical_url_for`, so predecessor matching is reliable)
    and its `(name, version)` is returned for the service to existence-check. Any other
    absolute URL is *external*: kept as-is, with no target. `None` (clearing the successor)
    yields `(None, None)`. Route resolution is a presentation concern, hence it lives here.
    """
    if url is None:
        return None, None
    parsed = urlparse(url)
    base = request.base_url
    match = _INTERNAL_PATH.match(parsed.path)
    if match and (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc):
        identity = SchemaIdentity(name=match["name"], version=match["version"])
        canonical = canonical_url_for(identity.name, identity.version, request)
        return SuccessorReference(url=canonical), identity
    return SuccessorReference(url=url), None


def stamp_canonical_id(
    document: dict[str, Any],
    *,
    canonical_url: str,
    title: str,
    description: str,
    deprecated: bool = False,
) -> dict[str, Any]:
    """Return a copy of `document` advertising its canonical `$id` and lifecycle state.

    Stamps the registry permalink as `$id`, fills in `title`/`description` defaults, and
    reconciles the standard JSON Schema `deprecated` keyword with the *domain* flag (the
    single source of truth): set when the version is deprecated, removed otherwise, so any
    author-written `deprecated` in the stored document never contradicts the registry. This
    is the document-shaping policy that used to live on the domain entity; it moved here
    because the canonical URL it injects is a presentation/HTTP concern.
    """
    document = dict(document)
    document["$id"] = canonical_url
    document.setdefault("title", title)
    if "description" not in document and description:
        document["description"] = description
    if deprecated:
        document["deprecated"] = True
    else:
        document.pop("deprecated", None)
    return document
