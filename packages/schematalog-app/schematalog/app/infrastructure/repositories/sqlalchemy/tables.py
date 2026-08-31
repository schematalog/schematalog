"""SQLAlchemy Core table definitions for the schema registry.

Columns mirror the wire-flat form of `Schema` (`name`, `version`,
`description`, `schema`, `publication_id`). Identity is the composite primary key
`(name, version)`, which is what gives `add` its fail-on-conflict semantic via
`IntegrityError`.
"""

import sqlalchemy as sa

from schematalog.app.infrastructure.repositories.sqlalchemy.types import (
    AdaptiveJSONColumn,
    DescriptionColumn,
    IdentifierColumn,
)

# Deterministic constraint names so the DDL is identical across dialects (otherwise
# PostgreSQL and SQLite invent different ones, and a constraint could not be named
# in a query without knowing which database built it).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db_metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)

schema = sa.Table(
    "schema",
    db_metadata,
    sa.Column("name", IdentifierColumn, primary_key=True),
    sa.Column("version", IdentifierColumn, primary_key=True),
    sa.Column("description", DescriptionColumn, nullable=False, server_default=""),
    sa.Column("json_schema", AdaptiveJSONColumn, nullable=False),
    # The registry's sort key: a UUIDv7, whose high bits are a big-endian millisecond
    # timestamp, so ordering by it is publication order and `published_on` is derived
    # from it rather than stored. Unique because it identifies one publication event.
    sa.Column(
        "publication_id",
        sa.Uuid,
        nullable=False,
        unique=True,
        comment="Opaque publication identifier (UUIDv7); the ordering of every version.",
    ),
    # Mutable lifecycle metadata (not part of the immutable identity/definition).
    sa.Column(
        "deprecated",
        sa.Boolean,
        nullable=False,
        server_default=sa.false(),
        comment="Whether this version is deprecated (still resolvable, not for new use).",
    ),
    # Reference to the version that replaces this one, as an absolute URI - an internal
    # schema's canonical `$id`, or any external registry. Open-world, so a plain nullable
    # URL, not a FK; internal refs are resolved/validated at set-time.
    sa.Column(
        "successor_url",
        sa.Text,
        nullable=True,
        # Indexed: the predecessor reverse-lookup filters on this on every document GET.
        index=True,
        comment="Absolute URI of the version that supersedes this one (internal $id or external).",
    ),
)
