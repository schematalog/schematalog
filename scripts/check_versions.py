"""Check that the meta-package's version matches the application's.

`schematalog` ships no modules; it exists so that `pip install schematalog` installs
the registry, and it carries the application's version so the number on the front door
means something. Nothing in the packaging enforces that - the two are written in
different files, in different formats, and neither build reads the other.

Run by CI. Exits non-zero and names both numbers when they disagree.
"""

import ast
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).parent.parent
META_MANIFEST = ROOT / "packages" / "schematalog" / "pyproject.toml"
APP_VERSION_FILE = ROOT / "packages" / "schematalog-app" / "schematalog" / "app" / "__init__.py"


def meta_version() -> str:
    """The meta-package's literal version.

    Read rather than imported: the meta-package has no modules to import, and its
    version is a literal in the manifest rather than sourced from a constant.

    Raises:
        KeyError: if the manifest declares no version.
    """
    return tomllib.loads(META_MANIFEST.read_text())["project"]["version"]


def app_version() -> str:
    """The application's `__version__`, read without importing it.

    Parsed from the source rather than imported, so the check needs neither the
    application installed nor its dependencies resolvable.

    Raises:
        LookupError: naming the file, if it declares no `__version__`.
    """
    module = ast.parse(APP_VERSION_FILE.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    # The path is the whole message: there is one thing wrong and one place to look.
    raise LookupError(APP_VERSION_FILE)


def main() -> int:
    meta, app = meta_version(), app_version()
    if meta != app:
        print(
            f"version mismatch: schematalog is {meta}, schematalog-app is {app}.\n"
            f"  They move together - see DECISIONS.md. Set the version in\n"
            f"  {META_MANIFEST.relative_to(ROOT)} to match\n"
            f"  {APP_VERSION_FILE.relative_to(ROOT)}.",
            file=sys.stderr,
        )
        return 1
    print(f"schematalog and schematalog-app agree at {meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
