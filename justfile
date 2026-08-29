# List available recipes.
help:
    @just --list --unsorted


# --- Tests ---

# Run unit tests (Python + frontend).
test: test-py test-fe

# Python unit tests (in-process, no external services) with coverage.
test-py:
    # Once per package, from inside it: a distribution that cannot be tested on its own
    # is not really separate. Packages with no unit lane are skipped rather than run -
    # pytest exits non-zero when it collects nothing, and a meta-package has nothing. It also keeps every `tests/` an `__init__.py` package
    # without two of them colliding as one importable `tests` module.
    # Each run happens inside its package, so COVERAGE_FILE and the config are pinned to
    # the workspace root; otherwise every package writes its own coverage data and the
    # combined report has nothing to read. The floor is checked once, on the total.
    rm -f .coverage
    for package in packages/*/; do \
        [ -d "$package/tests/unit" ] || continue; \
        (cd "$package" && COVERAGE_FILE={{justfile_directory()}}/.coverage \
            uv run pytest tests/unit --spec \
            --cov --cov-append --cov-config={{justfile_directory()}}/pyproject.toml \
            --cov-fail-under=0 --no-cov-on-fail) || exit 1; \
    done
    uv run coverage report

# Frontend unit tests (Vitest). No-op until the first island test lands.
test-fe:
    cd packages/schematalog-app/frontend && if find src -name '*.test.ts' -print -quit | grep -q .; then pnpm test; else echo "frontend: no tests yet - skipping vitest"; fi

# Run integration tests against the composed services (Postgres).
test-integration: up
    # Only the packages that have an integration lane; most have nothing to integrate with.
    for package in packages/*/; do \
        if [ -d "$package/tests/integration" ]; then \
            (cd "$package" && uv run pytest tests/integration --spec) || exit 1; \
        fi; \
    done


# --- Checks ---

# Run linting and formating checks (Python + frontend).
lint: lint-py lint-fe

# Python linting and formatting checks.
lint-py:
    # deptry checks a distribution against its own declared dependencies, so it runs once
    # per package rather than at the workspace root, which declares only the packages.
    # From inside each package, so its manifest is found and its `tests/` is excluded
    # by deptry's own defaults.
    # `|| exit 1` because a loop's status is its last iteration's: without it a
    # failure in any package but the last is silently discarded.
    for package in packages/*/; do (cd "$package" && uv run deptry .) || exit 1; done
    uv run ruff format --check .
    uv run ruff check .

# Frontend linting and formatting checks (Biome).
lint-fe:
    cd packages/schematalog-app/frontend && pnpm lint

# Run static typing analysis (Python + frontend).
type: type-py type-fe

# Python static typing analysis.
type-py:
    uv run pyrefly check

# Frontend static typing analysis (tsc). No-op until the first TS island lands.
type-fe:
    cd packages/schematalog-app/frontend && if find src -name '*.ts' -print -quit | grep -q .; then pnpm typecheck; else echo "frontend: no TS sources yet - skipping tsc"; fi

# Run security and safety checks.
safety:
    uvx vulture  --exclude .venv --min-confidence 100 .
    uvx radon mi --show --multi --min B .
    # Advisory only: report cognitive complexity without failing the recipe.
    -uvx complexipy --quiet .

# Run all checks.
check: lint safety type

# Run checks and unit tests.
ready: check test


# --- Compose (local service stack) ---

# Start the local service stack and wait until healthy.
up:
    docker compose -f packages/schematalog-app/compose.yaml up -d --wait

# Stop the local service stack and remove its data.
down:
    docker compose -f packages/schematalog-app/compose.yaml down -v


# --- Code & run ---

# Reformat the code using isort and ruff.
[confirm("Reformat every source file in place? [y/N]")]
reformat:
    uv run ruff format .
    uv run ruff check --select I --fix .

# Extract current production requirements. Save to a file by appending `> requirements.txt`.
reqs:
    uv export --no-dev

# Build, check and publish one distribution to PyPI (append `--dry-run` to rehearse).
[confirm("Publish to PyPI? A version cannot be replaced once uploaded. [y/N]")]
publish package *flags:
    #!/usr/bin/env sh
    set -eu
    # Takes the distribution name in either spelling - `schematalog-core` or
    # `schematalog_core` - because the artifacts on disk are named with underscores and
    # everything else uses hyphens, so both are on screen when reaching for this.
    package=$(echo "{{package}}" | tr '_' '-')
    # An upload cannot be undone: a version number, once used, is spent. So refuse first
    # on the two things that cost nothing to check - uncommitted work, and a version that
    # was never tagged. Release automation proper waits for 1.0 (see DECISIONS.md);
    # until then this is what keeps the handful of manual releases consistent.
    if [ -n "$(git status --porcelain)" ]; then
        echo "ERROR: working tree is dirty; commit or stash before publishing." >&2
        exit 1
    fi
    # Only the application needs this: its sdist force-includes the built frontend, and
    # the build fails outright without them rather than shipping an unstyled wheel.
    if [ "$package" = "schematalog-app" ]; then {{just_executable()}} build-fe; fi
    rm -rf dist
    uv build --package "$package"
    stem=$(basename "$(ls dist/*.tar.gz)" .tar.gz)
    version=${stem##*-}
    # The meta-package gets no tag of its own - the application's release covers both,
    # and the two versions are always equal (DECISIONS.md, enforced by
    # scripts/check_versions.py). Looking for its own tag would refuse it forever.
    if [ "$package" = "schematalog" ]; then
        tag="schematalog-app/v$version"
    else
        tag="$package/v$version"
    fi
    if ! git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
        echo "ERROR: built $version but there is no tag $tag." >&2
        echo "       Every version bump carries an annotated tag - see DECISIONS.md." >&2
        exit 1
    fi
    uvx twine check dist/*
    echo "Publishing $package $version (tagged $tag)"
    uv publish {{flags}} dist/*

port := "3000"

# Run the dev server with reload on http://localhost:3000.
serve: build-fe
    uv run schematalog serve --port {{port}} --reload


# Build distributable wheels and sdists for every package, into dist/.
# Depends on build-fe because the application's sdist force-includes the built assets:
# without them the build fails outright rather than producing a wheel that renders
# unstyled, which is the failure mode worth having.
build: build-fe
    rm -rf dist
    uv build --all-packages

# --- Frontend (Vite + Tailwind v4 + DaisyUI; see packages/schematalog-app/frontend/README.md) ---

# Install frontend dependencies (run once after checkout / when package.json changes).
install-fe:
    cd packages/schematalog-app/frontend && pnpm install

# Build the frontend assets into the app's static dir (manifest + hashed CSS/JS).
build-fe:
    cd packages/schematalog-app/frontend && pnpm build
    # Tailwind emits a utility only when it finds the class in a scanned file, so a wrong
    # content path yields a valid, small stylesheet and unstyled pages - a success the eye
    # has to catch. Assert one utility the templates certainly use.
    @grep -q 'text-2xl' packages/schematalog-app/schematalog/app/presentation/webapp/static/dist/assets/*.css \
        || { echo "ERROR: built CSS has no utility classes - check the @source paths in frontend/src/styles/app.css"; exit 1; }

# Rebuild frontend assets on change (run alongside `just serve` while editing the UI).
watch-fe:
    cd packages/schematalog-app/frontend && pnpm watch

# Format frontend sources in place (Biome).
format-fe:
    cd packages/schematalog-app/frontend && pnpm format

# Regenerate the Pygments token styles used by the server-rendered code blocks.
regen-code-css:
    uv run python scripts/generate_code_css.py
    cd packages/schematalog-app/frontend && pnpm biome format --write src/styles/code.css

# Serve the documentation locally with live reload.
docs:
    uv run --group docs mkdocs serve --livereload -a localhost:7000

# Populate the configured storage (see .env) with sample schemas. Idempotent.
seed:
    uv run python -m scripts.seed

# Recreate the local SQLite dev DB and reseed (use after a schema change).
[confirm("Delete db.sqlite3 and reseed? [y/N]")]
reset: && seed
    rm -f db.sqlite3

# Deploy to fly.io, baking the current commit + its date into the image (surfaced at
# GET /version and the webapp footer).
deploy:
    fly deploy --config packages/schematalog-app/fly.toml --dockerfile packages/schematalog-app/Dockerfile \
        --build-arg GIT_COMMIT="$(git rev-parse --short HEAD)" \
        --build-arg GIT_COMMIT_DATE="$(git show -s --format=%cs HEAD)"
