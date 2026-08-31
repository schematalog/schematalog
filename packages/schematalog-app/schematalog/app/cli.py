"""The command a `pip install` gives you.

    pip install schematalog-app
    schematalog serve

Deliberately small, and deliberately not the operator CLI removed in the phase-1
teardown: that one provisioned tenants and API tokens, which no longer exist. This runs
the server and reports what it is, so getting from "installed" to "running" needs no
knowledge of ASGI, and argparse rather than a CLI framework because three commands do not
justify a dependency.
"""

import argparse
import asyncio
from collections.abc import Sequence

import uvicorn

from schematalog.app import __version__
from schematalog.app.wiring.config import settings
from schematalog.app.wiring.storage import (
    InvalidStorageUrlError,
    build_schema_repository,
    check_storage,
    get_storage_summary,
)
from schematalog.common.logging import redact

APP_PATH = "schematalog.app.presentation:app"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schematalog", description="A registry and catalog for JSON Schema specifications."
    )
    parser.add_argument("--version", action="version", version=f"schematalog {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="Run the registry.")
    serve.add_argument(
        "--host", default="127.0.0.1", help="Interface to bind (default: %(default)s)."
    )
    serve.add_argument(
        "--port", type=int, default=8000, help="Port to bind (default: %(default)s)."
    )
    serve.add_argument(
        "--reload", action="store_true", help="Restart on code changes (development only)."
    )

    commands.add_parser("info", help="Show the version and the configured store.")
    commands.add_parser("check", help="Check that the configured store can be reached.")
    return parser


def _serve(args: argparse.Namespace) -> int:
    uvicorn.run(APP_PATH, host=args.host, port=args.port, reload=args.reload)
    return 0


def _info(_: argparse.Namespace) -> int:
    """Report the version and how storage resolved - the two things a first run gets wrong.

    The URL itself is never printed: it routinely carries a password, and `info` is
    exactly the output someone pastes into an issue.
    """
    store = get_storage_summary(settings.STORAGE_URL)
    known = "recognised" if store["known"] else "NOT recognised - no backend answers to it"
    print(f"schematalog {__version__}")
    print(f"storage scheme: {store['scheme']} ({known})")
    print(f"environment:    {settings.ENVIRONMENT}")
    return 0


def _check(_: argparse.Namespace) -> int:
    """Open the configured store and say whether it answered.

    The gap this fills: every backend connects lazily, so a wrong host or password
    starts perfectly well and fails on the first request instead. `info` cannot catch
    that - it only asks whether a backend answers to the scheme - so the check that
    actually opens the store is its own command.

    Returns a non-zero status when the store is not usable, so a deploy script can gate
    on it. Distinguishes the three ways it can fail, because each has a different fix:
    an unrecognised scheme, options that do not validate, and a store that will not
    answer. Like `info` it never prints the URL, and the backend's own error goes
    through the same redaction as a log line first.
    """
    store = get_storage_summary(settings.STORAGE_URL)
    print(f"schematalog {__version__}")
    if not store["known"]:
        print(f"storage scheme: {store['scheme']} (NOT recognised - no backend answers to it)")
        return 1
    print(f"storage scheme: {store['scheme']} (recognised)")
    try:
        repository = build_schema_repository(settings.STORAGE_URL)
    except InvalidStorageUrlError as error:
        print(f"store:          misconfigured - {redact(str(error))}")
        return 1
    try:
        asyncio.run(check_storage(repository))
    except Exception as error:  # noqa: BLE001 - anything at all means it is not usable
        print(f"store:          unreachable - {type(error).__name__}")
        print(f"  {redact(str(error))}")
        return 1
    print("store:          reachable")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the `schematalog` command."""
    args = _parser().parse_args(argv)
    return {"serve": _serve, "info": _info, "check": _check}[args.command](args)
