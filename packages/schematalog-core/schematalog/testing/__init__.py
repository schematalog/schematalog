"""Test support that is part of the public surface.

`SchemaRepositoryConformance` is the storage contract expressed as tests: a backend - in
this repository or anyone else's - subclasses it, supplies one fixture, and inherits the
whole specification. `example_document` and `example_payload` are the sample schema every
test tree here uses, published so a backend author has a realistic one to hand.
"""

from schematalog.testing.conformance import SchemaRepositoryConformance
from schematalog.testing.samples import example_document, example_payload

__all__ = ["SchemaRepositoryConformance", "example_document", "example_payload"]
