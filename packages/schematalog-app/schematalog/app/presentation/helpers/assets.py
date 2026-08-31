"""Vite asset resolution - the FastAPI <-> Vite handshake for the frontend build.

Jinja owns the HTML, so it must write the right `<link>`/`<script>` tags for the
assets Vite builds off to the side. Templates call `vite_asset("src/styles/app.css")`
(the entry's manifest key); this helper returns the tags:

- **Production / normal local runs**: resolve the entry through Vite's `manifest.json`
  to its hashed, cache-busted file under `/static/dist/`.
- **Dev** (when `SCHEMATALOG_VITE_DEV_SERVER` is set): point at the running Vite dev
  server so HMR works; no build needed.

The built `dist/` is gitignored and produced by `just build-fe` (and baked into the
Docker image at deploy), so a fresh checkout has no manifest until the first build -
in that case the helper degrades to an HTML comment and logs a warning rather than
breaking page rendering (keeps the test suite and un-built dev runs alive).
"""

import json
from pathlib import Path
from typing import Any

from markupsafe import Markup

from schematalog.app.wiring.config import settings
from schematalog.common.logging import get_logger

log = get_logger(__name__)

_DIST_DIR = Path(__file__).resolve().parent.parent / "webapp" / "static" / "dist"
_MANIFEST_PATH = _DIST_DIR / ".vite" / "manifest.json"
_STATIC_BASE = "/static/dist"

# Cache the parsed manifest keyed on its mtime, so a rebuild (new hashes) is picked up
# without a process restart, but we do not re-read the file on every render. A mutable
# dict (rather than a rebindable global) keeps the cache update local to the function.
_manifest_cache: dict[str, Any] = {}


def _load_manifest() -> dict[str, Any] | None:
    """Return the parsed Vite manifest, or None when it has not been built yet."""
    try:
        mtime = _MANIFEST_PATH.stat().st_mtime
    except FileNotFoundError:
        return None
    if _manifest_cache.get("mtime") != mtime:
        _manifest_cache["mtime"] = mtime
        _manifest_cache["data"] = json.loads(_MANIFEST_PATH.read_text())
    return _manifest_cache["data"]


def _render_link(path: str) -> str:
    return f'<link rel="stylesheet" href="{_STATIC_BASE}/{path}">'


def _render_script(path: str) -> str:
    return f'<script type="module" src="{_STATIC_BASE}/{path}"></script>'


def _build_tags_for(chunk: dict[str, Any]) -> list[str]:
    """The tags for one manifest chunk: its own file plus any CSS it imports.

    A CSS entry's `file` is the stylesheet itself; a JS entry's `file` is the script,
    and its bundled styles arrive via the `css` array.
    """
    tags = [_render_link(css) for css in chunk.get("css", [])]
    file = chunk["file"]
    tags.append(_render_link(file) if file.endswith(".css") else _render_script(file))
    return tags


def _render(entry: str) -> str:
    """Build the HTML for a Vite entry as a trusted markup string.

    Every interpolated value is build- or config-controlled - the configured
    dev-server URL, the static base, the manifest's own hashed filenames, and the
    `entry` template literal - never request input. That contract is why `_render`
    is whitelisted in `allowed-markup-calls`, letting `vite_asset` wrap it in `Markup`
    without an S704 false positive. Keep it that way: do not interpolate user input.
    """
    dev_server = settings.VITE_DEV_SERVER
    if dev_server:
        return (
            f'<script type="module" src="{dev_server}/@vite/client"></script>\n'
            f'<script type="module" src="{dev_server}/{entry}"></script>'
        )
    manifest = _load_manifest()
    if manifest is None or entry not in manifest:
        log.warning("vite_asset_unresolved", entry=entry, built=manifest is not None)
        return f"<!-- vite asset not built: {entry} (run `just build-fe`) -->"
    return "\n".join(_build_tags_for(manifest[entry]))


def vite_asset(entry: str) -> Markup:
    """Render the HTML tags that load a Vite entry (by its manifest key)."""
    # `_render` builds the tags from build- and config-controlled values only (manifest
    # paths, the configured dev-server URL) and never from request input, so the result
    # is markup-safe. Previously expressed as ruff's `allowed-markup-calls`, which
    # resolves a call by dotted module path and stopped matching once the package moved
    # into the workspace.
    return Markup(_render(entry))  # noqa: S704
