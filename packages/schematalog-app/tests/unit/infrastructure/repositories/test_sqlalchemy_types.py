from datetime import UTC, datetime, timedelta, timezone

import pytest

from schematalog.app.infrastructure.repositories.sqlalchemy.types import TimezoneAwareDateTime


def test_rejects_naive_datetime_on_write():
    column_type = TimezoneAwareDateTime()
    with pytest.raises(ValueError, match="naïve"):
        column_type.process_bind_param(datetime(2026, 1, 1, 12, 0, 0), dialect=None)  # noqa: DTZ001


def test_converts_aware_datetime_to_naive_utc_for_storage():
    column_type = TimezoneAwareDateTime()
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    stored = column_type.process_bind_param(aware, dialect=None)
    # 12:00 +02:00 is 10:00 UTC, stored naïve for SQLite.
    assert stored == datetime(2026, 1, 1, 10, 0, 0)  # noqa: DTZ001
    assert stored.tzinfo is None


def test_reattaches_utc_on_read():
    column_type = TimezoneAwareDateTime()
    loaded = column_type.process_result_value(datetime(2026, 1, 1, 10, 0, 0), dialect=None)  # noqa: DTZ001
    assert loaded == datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    assert loaded.tzinfo is UTC


def test_none_passes_through_both_directions():
    column_type = TimezoneAwareDateTime()
    assert column_type.process_bind_param(None, dialect=None) is None
    assert column_type.process_result_value(None, dialect=None) is None
