"""Fixtures for the contract's own tests.

The sample document comes from `schematalog.testing`, which publishes it precisely so
that this tree, the application's tests and any third-party backend all exercise the same
schema instead of three different ones.
"""

import pytest

from schematalog.testing import example_document, example_payload


@pytest.fixture
def example_schema_dict():
    return example_document()


@pytest.fixture
def example_schema():
    return example_payload()
