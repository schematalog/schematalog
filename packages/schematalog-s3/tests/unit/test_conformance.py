"""The out-of-tree S3 backend, discovered and held to the storage contract.

These live with the package rather than with the registry's tests, because that is what
being a separate distribution means. They are also the end-to-end proof of the extension
point: a scheme is added by installing a package, and such a package passes the same
contract as a built-in backend. Nothing in the registry knows this one exists.

S3 itself is mocked. The mock is not the point; the seam is.
"""

import boto3
import moto
import pytest

from schematalog.app.wiring.storage import build_schema_repository
from schematalog.testing import SchemaRepositoryConformance

BUCKET = "conformance-bucket"


@pytest.fixture
def s3_bucket():
    """A mocked S3 with one empty bucket, for the duration of a test."""
    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield BUCKET


def test_the_scheme_comes_from_an_installed_package(s3_bucket):
    """`s3` is in no builders table here; it is discovered from the package's metadata."""
    from schematalog.app.wiring.storage import BUILT_IN_BUILDERS

    assert "s3" not in BUILT_IN_BUILDERS
    repo = build_schema_repository(f"s3://{s3_bucket}/schemas")
    assert type(repo).__name__ == "S3SchemaRepository"


def test_the_url_carries_the_bucket_prefix_and_options(s3_bucket):
    repo = build_schema_repository(f"s3://{s3_bucket}/nested/prefix?region=eu-west-2")
    assert repo.bucket_name == s3_bucket
    assert repo.prefix == "nested/prefix"
    assert repo.client.meta.region_name == "eu-west-2"


class TestS3RepositoryConformance(SchemaRepositoryConformance):
    """The whole contract, against a backend this repository does not contain."""

    @pytest.fixture
    def repository(self, s3_bucket):
        return build_schema_repository(f"s3://{s3_bucket}/schemas")
