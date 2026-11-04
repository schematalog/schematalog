"""Build/version metadata, shared by `GET /version` and the webapp footer.

`commit`/`commit_date` prefer values baked into the image at deploy time
(`GIT_COMMIT` / `GIT_COMMIT_DATE` build-args), fall back to the working tree's
`HEAD` for local runs, and finally to a neutral default when no git checkout is
available (a deployed image without the env vars and without git installed).
"""

import os
from pathlib import Path
import shutil
import subprocess

from schematalog.app import __version__

_SOURCE_TREE = Path(__file__).parent

DOCS_URL = "https://schematalog.readthedocs.io/"
"""Where the prose documentation lives, linked from the footer.

Deliberately off-site rather than served by the app. The docs describe *a version*,
and the host versions them per release with a selector; a copy shipped inside the
application would be frozen at whatever went out and could not be corrected without
a release. It would also have to find a home other than `/docs`, which is already
the generated OpenAPI reference.
"""

REPOSITORY_URL = "https://github.com/schematalog/schematalog"
"""The source repository, linked from the footer."""


def app_version() -> str:
    """The curated app version.

    Single source of truth = `schematalog.app.__version__` (a plain code constant), so
    the runtime depends on neither `pyproject.toml` nor installed package metadata
    (this is a non-packaged `uv` app run from source). `pyproject` sources its
    version from the same constant.
    """
    return __version__


def _run_git(*args: str) -> str | None:
    """Run a read-only git command in the source tree, or `None` if unavailable."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed git path (shutil.which), static args
            [git, *args],
            capture_output=True,
            text=True,
            check=True,
            cwd=_SOURCE_TREE,
        )
    except OSError, subprocess.CalledProcessError:
        return None
    return result.stdout.strip() or None


def commit() -> str:
    """The running commit's short SHA, or `unknown` if it can't be determined."""
    return os.environ.get("GIT_COMMIT") or _run_git("rev-parse", "--short", "HEAD") or "unknown"


def commit_date() -> str:
    """The running commit's date (`YYYY-MM-DD`), or empty if it can't be determined."""
    return (
        os.environ.get("GIT_COMMIT_DATE")
        or _run_git("show", "-s", "--format=%cs", "HEAD")
        or ""
    )
