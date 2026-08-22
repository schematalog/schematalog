"""Cross-dialect SQLAlchemy helpers (PostgreSQL in production, SQLite in tests).

Lifted from the gapmap project's `common/sqla.py`. Schematalog's `add` is
fail-on-conflict rather than upsert, so the `UniversalUpsert` construct from
gapmap is deliberately not carried over.
"""

from datetime import UTC

from sqlalchemy import JSON, DateTime, String, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on PostgreSQL (indexable, typed), plain JSON everywhere else (e.g. SQLite).
AdaptiveJSONColumn = JSON().with_variant(JSONB(), "postgresql")

# Byte-order name listing is part of the storage contract (the conformance suite pins
# it), not a PostgreSQL preference. It just happens that PostgreSQL is the only backend
# here that needs telling: Python sorts by code point and SQLite's default `BINARY`
# collation agrees with it, while PostgreSQL follows the database's locale.
#
# Identifier columns (`name`, `version`) are still *listed* in string order -
# `list_latest` yields name-ascending, `list_predecessors` in (name, version) order -
# and those listings must be identical on every backend. SQLite's default `BINARY`
# collation orders by byte value, matching Python's `str` comparison; PostgreSQL uses
# the database's locale collation, which sorts mixed-case and punctuated identifiers
# differently. Pinning the `C` (byte-order) collation on PostgreSQL keeps them in
# agreement; SQLite has no `C` collation name, so the variant only touches PostgreSQL
# DDL.
#
# This no longer decides *which version is latest*: that is publication order now, from
# `publication_id`, and the version string is never compared (see DECISIONS.md). The
# collation is therefore no longer load-bearing for correctness, only for listings
# looking the same everywhere.
IdentifierColumn = String(256).with_variant(String(256, collation="C"), "postgresql")


class TimezoneAwareDateTime(TypeDecorator):
    """A `DateTime` that always round-trips timezone-aware UTC values.

    SQLite stores naïve datetimes, so a tz-aware value written there would come
    back naïve. This decorator enforces aware-in, converts to UTC for storage,
    and re-attaches UTC on the way out — so PostgreSQL and SQLite behave alike.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: F841
        # Going IN to the database.
        if value is not None:
            if value.tzinfo is None:
                msg = "Refusing to store a naïve datetime; use a timezone-aware value."
                raise ValueError(msg)
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):  # noqa: F841
        # Coming OUT of the database: we stored UTC, so re-attach it.
        if value is not None:
            value = value.replace(tzinfo=UTC)
        return value
