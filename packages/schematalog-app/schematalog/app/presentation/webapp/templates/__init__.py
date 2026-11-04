from datetime import datetime
import json
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from markupsafe import Markup

from schematalog.app.presentation.helpers import buildinfo
from schematalog.app.presentation.helpers import format as fmt
from schematalog.app.presentation.helpers.assets import vite_asset
from schematalog.common.avroform import AvroConversionError

TEMPLATES_DIR = Path(__file__).parent


def json_filter(value: Any):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    return fmt.to_json(value)


def yaml_filter(value: Any):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    return fmt.to_yaml(value)


def python_filter(value: Any):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    return fmt.to_pydantic(value)


@pass_context
def avro_filter(ctx, value: Any):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    namespace = ctx.get("schema").get("name")
    try:
        return fmt.to_avro(value, namespace)
    except AvroConversionError as exc:
        return f"# This schema cannot be represented as Avro: {exc}"


def highlight_filter(code: str, language: str, anchor: str) -> Markup:
    """Syntax-highlight already-formatted code for rendering.

    Returns `Markup` because the result *is* HTML: Pygments escapes the code it wraps,
    so the only unescaped content is its own tags. Marking it here rather than with a
    template-side `|safe` keeps the escaping decision next to the reason for it.

    The `S704` suppression rests on that escaping, which is Pygments' contract and not
    an assumption about the input - schema documents are user-controlled and are
    expected to contain hostile strings. `test_highlight_escapes_the_code_it_wraps`
    pins the guarantee.
    """
    return Markup(fmt.highlight(code, language, anchor))  # noqa: S704


def datetime_filter(value: str | datetime):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%d %B %Y %H:%M")


def endpoint_context(request: Request) -> dict[str, Any]:
    return {"endpoint": getattr(request.scope.get("endpoint"), "__name__", "")}


def asset_context(request: Request) -> dict[str, Any]:
    """Expose the Vite asset helper so templates can resolve built frontend assets."""
    return {"vite_asset": vite_asset}


def build_context(request: Request) -> dict[str, Any]:
    """Footer content: the running build, plus where to read about it."""
    return {
        "app_version": request.app.version,
        "version_date": buildinfo.commit_date(),
        "docs_url": buildinfo.DOCS_URL,
        "repository_url": buildinfo.REPOSITORY_URL,
    }


templates = Jinja2Templates(
    directory=TEMPLATES_DIR,
    context_processors=[endpoint_context, asset_context, build_context],
)
# Starlette builds the env with `select_autoescape(["html", "xml"])`, which keys off the
# file *extension* - and every template here is `.jinja`, so autoescaping was silently
# off for all of them. Force it on: these are all HTML, and they render user-controlled
# strings (schema names and descriptions, the submitted
# publish document). Anything rendering deliberate HTML must return `Markup` and
# escape its own input - see `highlight_filter` and `helpers.property_type`.
templates.env.autoescape = True
templates.env.filters["json"] = json_filter
templates.env.filters["yaml"] = yaml_filter
templates.env.filters["python"] = python_filter
templates.env.filters["avro"] = avro_filter
templates.env.filters["datetime"] = datetime_filter
templates.env.filters["highlight"] = highlight_filter
