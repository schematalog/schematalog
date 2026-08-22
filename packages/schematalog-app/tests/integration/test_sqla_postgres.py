"""What is true of PostgreSQL and cannot be shown on SQLite.

The contract itself is checked by `test_conformance_postgres.py`, which runs the whole
published suite against this backend. What remains here is dialect behaviour that suite
does not exercise because it needs no exotic data: JSONB round-tripping of a document
with real structure to it.

The collation the identifier columns pin is *not* here - it moved into the suite, so
every backend is held to the same byte ordering rather than PostgreSQL being checked
against a hand-written expectation.
"""

from schematalog.app.application.schema import GetSchemaCommand, PublishCommand, SchemaService


async def test_a_structured_document_survives_jsonb(pg_schema_repo, example_schema_dict):
    """JSONB is a parsed representation, not a string: it can reorder keys or coerce types.

    The suite publishes a trivial `{"type": "object"}`, which would round-trip through
    almost anything. This uses a document with nesting, arrays and mixed value types.
    """
    service = SchemaService(pg_schema_repo)
    published = await service.publish_schema(
        PublishCommand(
            name="person",
            version="1.2",
            json_schema=example_schema_dict,
            description="A person.",
        )
    )
    fetched = await service.get_schema(GetSchemaCommand(name="person", version="1.2"))

    # What went in comes back byte-identical, `$schema` inference aside (the service adds
    # it before storage, so `published` and not the input is the thing to compare against).
    assert fetched.document == published.document
    # JSONB keeps array order but not object key order, so the ordered parts are the ones
    # worth naming: a `required` list that came back permuted would still be valid JSON.
    assert fetched.document["required"] == example_schema_dict["required"]
    assert fetched.document["properties"] == example_schema_dict["properties"]
    assert fetched.description == "A person."
    assert fetched.published_on == published.published_on
