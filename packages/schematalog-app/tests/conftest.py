"""Fixtures for the application's tests, unit and integration alike.

The sample schema comes from `schematalog.testing`, which publishes it so that this tree,
the contract's own tests and any third-party backend exercise the same document rather
than three different ones.

Lane-specific fixtures live with their lane: in-process storage backends in
`unit/conftest.py`, real Postgres in `integration/conftest.py`.
"""

import pytest

from schematalog.testing import example_document, example_payload


@pytest.fixture
def example_schema_dict():
    return example_document()


@pytest.fixture
def example_schema():
    return example_payload()
