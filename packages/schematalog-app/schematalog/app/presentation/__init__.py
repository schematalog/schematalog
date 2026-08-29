"""Application assembly: one FastAPI app serving both the JSON API and the HTML UI."""

from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
import yaml

from schematalog.app.application.exceptions import (
    ApplicationError,
    DuplicateSchemaError,
    InvalidSchemaError,
    InvalidSuccessorError,
    SchemaNotFoundError,
)
from schematalog.app.presentation import api, webapp
from schematalog.app.presentation.helpers import buildinfo
from schematalog.app.wiring.config import settings
from schematalog.app.wiring.storage import build_schema_repository, check_storage
from schematalog.common.logging import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
)

STATIC_DIR = Path(__file__).parent / "webapp" / "static"

log = get_logger(__name__)

configure_logging(debug=settings.DEBUG)

app = FastAPI(
    title="Schematalog",
    description="API for cataloguing JSON Schema specifications.",
    version=buildinfo.app_version(),
    debug=settings.DEBUG,
    openapi_tags=[
        {
            "name": "Schemas",
            "description": (
                "Publishing and retrieving versioned JSON Schema documents. A schema is "
                "identified by its name and version; every published version is "
                "immutable, apart from its deprecation metadata."
            ),
        }
    ],
)
# Fly terminates TLS at the edge and forwards over plain HTTP, so honour the
# `X-Forwarded-Proto`/`-For` headers it sets - otherwise the canonical `$id`
# (built from `request.url_for`) would be stamped as `http://` in production.
# Trust any client because the app is only ever reachable through Fly's proxy.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.state.schemas = build_schema_repository(settings.STORAGE_URL)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(api.router)
app.include_router(webapp.router)


@app.middleware("http")
async def _request_context(request: Request, call_next: Callable) -> Response:
    """Bind a request id (+ method/path) to the logging context for the request.

    Outermost middleware, so every downstream log line - in middleware, dependencies,
    and handlers - inherits these fields for correlation. We do not emit an access log
    line here (uvicorn already does); this only attaches identifiers to *our* logs.
    The id echoes an inbound `X-Request-ID` (e.g. from Fly) when present, else is fresh.
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    bind_context(request_id=request_id, method=request.method, path=request.url.path)
    try:
        response = await call_next(request)
    finally:
        clear_context()
    response.headers["X-Request-ID"] = request_id
    return response


# The presentation layer owns the application-error -> HTTP-status mapping (the
# application stays transport-agnostic).
_HTTP_STATUS: dict[type[ApplicationError], HTTPStatus] = {
    SchemaNotFoundError: HTTPStatus.NOT_FOUND,
    DuplicateSchemaError: HTTPStatus.CONFLICT,
    InvalidSchemaError: HTTPStatus.UNPROCESSABLE_ENTITY,
    InvalidSuccessorError: HTTPStatus.UNPROCESSABLE_ENTITY,
}


@app.exception_handler(ApplicationError)
async def _application_error(request: Request, exc: ApplicationError) -> Response:
    """Map a service-level error to its HTTP status."""
    status = _HTTP_STATUS.get(type(exc), HTTPStatus.INTERNAL_SERVER_ERROR)
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.get("/openapi.yaml", include_in_schema=False)
def openapi_yaml() -> Response:
    """The generated OpenAPI specification in YAML."""
    return Response(yaml.safe_dump(app.openapi()), media_type="application/yaml")


@app.get("/version", include_in_schema=False)
def version() -> dict[str, str]:
    """The running build: curated app version, commit, and where/how it runs.

    `commit`/`commit_date` are the build-baked `GIT_COMMIT`/`GIT_COMMIT_DATE` in
    deployed images or the working tree's `HEAD` locally (matching the webapp
    footer); `environment`/`platform` come from settings (the two orthogonal
    deploy axes - see `Environment`/`Platform`).
    """
    return {
        "version": app.version,
        "commit": buildinfo.commit(),
        "commit_date": buildinfo.commit_date(),
        "environment": settings.ENVIRONMENT,
        "platform": settings.PLATFORM,
    }


@app.get("/health", include_in_schema=False)
async def health() -> Response:
    """Whether this instance can reach its store: a real read, not a liveness ping.

    An instance whose store is unreachable starts and serves pages perfectly well, so
    "the process is up" answers the wrong question. This one does the read.

    The status code carries the answer - 503 rather than 200 with a field to inspect -
    because a load balancer, a container health check and an uptime monitor can all act
    on a code and none of them will parse a body.

    That body deliberately holds no detail. The endpoint is public and unauthenticated,
    and a driver's connection error names hosts, ports and user names; the detail goes
    to the log, which is redacted and which only the operator can read.
    """
    try:
        await check_storage(app.state.schemas)
    except Exception:
        log.exception("health check failed: storage unreachable")
        return JSONResponse(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "storage": "unreachable"},
        )
    return JSONResponse(content={"status": "ok", "storage": "ok"})
