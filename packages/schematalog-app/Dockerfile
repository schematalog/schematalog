# --- Frontend build stage: compile Tailwind/DaisyUI + bundle islands with Vite ---
# Produces the manifest + hashed assets the Jinja `vite_asset()` helper resolves.
# Built from the workspace root, so every path below is repo-relative even though this
# file lives with the package it builds: `docker build -f packages/schematalog-app/Dockerfile .`
FROM node:24-bookworm-slim AS frontend
WORKDIR /app
RUN corepack enable pnpm
COPY packages/schematalog-app/frontend/ ./packages/schematalog-app/frontend/
# Tailwind v4 scans the Jinja templates (via the @source directive) at build time to
# decide which utility classes to emit, so the templates must be present to build.
COPY packages/schematalog-app/schematalog/app/presentation/webapp/templates/ ./packages/schematalog-app/schematalog/app/presentation/webapp/templates/
# Same relative layout as the repo, so Vite's `outDir` (../schematalog/app/...)
# resolves to the same place here as it does locally.
RUN cd packages/schematalog-app/frontend && pnpm install --frozen-lockfile && pnpm build

# --- App stage ---
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE uv.lock ./
COPY scripts/ ./scripts/
COPY packages/ ./packages/

# Sources first, then one sync. The obvious optimisation - copy only the manifests, install
# third-party dependencies into a cached layer, then add the code - does not survive this
# workspace: every package takes its version from a source file, so building any member's
# metadata needs sources present, and each new member broke the manifest list again. A
# rebuild therefore reinstalls dependencies whenever any package file changes. Deploys are
# infrequent and the base image is cached, so that is the cheaper mistake to make.
RUN uv sync --no-default-groups --locked
# The built frontend assets (manifest + hashed CSS/JS) from the frontend stage. Copied
# after the app code so it lands on top regardless of what the source tree carried.
COPY --from=frontend /app/packages/schematalog-app/schematalog/app/presentation/webapp/static/dist/ ./packages/schematalog-app/schematalog/app/presentation/webapp/static/dist/

EXPOSE 8000

# Build metadata: the deployed commit and its date, surfaced at GET /version and
# the webapp footer (commit also as an OCI label). Placed late so changing it
# doesn't invalidate the dependency-install cache. Passed at deploy via `just deploy`.
ARG GIT_COMMIT=unknown
ARG GIT_COMMIT_DATE=
LABEL org.opencontainers.image.revision=$GIT_COMMIT
ENV GIT_COMMIT=$GIT_COMMIT
ENV GIT_COMMIT_DATE=$GIT_COMMIT_DATE

# ENTRYPOINT is only the interpreter prefix so a platform release command appended as
# args forms a valid `uv run --no-sync ...`. The default server command lives in CMD,
# which such a command overrides. It binds 0.0.0.0 deliberately - the command's own
# default is loopback, which is right for a laptop and useless in a container.
ENTRYPOINT ["uv", "run", "--no-sync"]
CMD ["schematalog", "serve", "--host", "0.0.0.0", "--port", "8000"]
