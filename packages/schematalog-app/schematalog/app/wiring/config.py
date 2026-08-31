"""Application settings.

Storage is one variable - a URL whose scheme selects the backend:

    SCHEMATALOG_STORAGE_URL=sqlite:///./schematalog.db
    SCHEMATALOG_STORAGE_URL=postgresql://user:pw@host/db
    SCHEMATALOG_STORAGE_URL=file:///data/schemas
"""

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from schematalog.app.wiring.storage import DEFAULT_STORAGE_URL


class Environment(StrEnum):
    """Deployment *stage* - the role a run plays and how costly its breakage is."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Platform(StrEnum):
    """Deployment *target* - where the process physically runs.

    Orthogonal to `Environment`: one platform can host several stages (a future
    staging app on `fly`), so the two are kept as separate axes.
    """

    LOCAL = "local"
    COMPOSE = "compose"
    FLY = "fly"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCHEMATALOG_",
        env_file=".env",
        env_nested_delimiter="__",
    )

    DEBUG: bool = False
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    """The deployment stage; `production` on Fly, `development` for local/compose runs."""
    PLATFORM: Platform = Platform.LOCAL
    """Where the process runs; `fly.toml` sets `fly`, a containerised compose app would
    set `compose`, and a bare `just serve` keeps the `local` default."""
    STORAGE_URL: str = DEFAULT_STORAGE_URL
    """Selects and configures the store in one setting: the scheme picks the backend and
    the query string carries its options (see `wiring/storage.py`). Defaults to SQLite in
    the working directory, so a bare run needs no configuration at all."""
    MAX_QUERY_LENGTH: int = Field(default=128, ge=1, le=4096)
    """How long a search query may be, in characters.

    A resource guard rather than a semantic boundary - no real search approaches the
    default - so it is set at the generous end, where being wrong costs nothing, rather
    than the tight end, where being wrong refuses a legitimate search. It bounds the work
    a query can ask for: a leading-wildcard `LIKE` cannot use an index, so cost is linear
    in the text scanned.

    Deliberately not a share of the domain's `MAX_IDENTIFIER_LENGTH`: how long a stored
    name may be and how much someone may type into a box are unrelated questions.

    It is published, not hidden: it appears as `maxLength` on the `q` parameter in this
    instance's OpenAPI document, so a client generated against an instance carries that
    instance's bound. Its own bounds are what keep it from being set to something that
    disables the guard or breaks the schema.
    """
    VITE_DEV_SERVER: str = ""
    """Base URL of a running Vite dev server (e.g. `http://localhost:5173`). When set,
    `vite_asset()` emits dev tags (HMR) instead of resolving the built manifest. Empty
    in production and normal local runs, which serve the built, hashed assets."""


settings = Settings()
