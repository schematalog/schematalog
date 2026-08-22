"""The `SchemaService` use cases: validation, command handling, error translation.

Deliberately *not* storage behaviour - ordering, the `latest` rule, listing, conflict on
duplicate - which is the storage contract and lives in
`schematalog.testing.SchemaRepositoryConformance`, run against every backend. These
cases run over one backend because none of them depends on which it is; anything that
does belongs in the suite, where four backends check it instead of three.
"""

from pydantic import ValidationError
import pytest

from schematalog.app.application.exceptions import (
    InvalidSuccessorError,
    SchemaNotFoundError,
)
from schematalog.app.application.schema import (
    GetSchemaCommand,
    ListVersionsCommand,
    MetadataUpdateCommand,
    PublishCommand,
    SchemaService,
)
from schematalog.app.infrastructure.repositories import MemorySchemaRepository
from schematalog.domain.schema import SchemaIdentity, SuccessorReference


@pytest.fixture
def schema_repo():
    """One in-process backend: these tests are about the service, not the store."""
    return MemorySchemaRepository()


def _service(repo) -> SchemaService:
    return SchemaService(repo)


async def _publish(repo, schema):
    return await _service(repo).publish_schema(
        PublishCommand(
            name=schema["name"],
            version=schema["version"],
            json_schema=schema["schema"],
            description=schema.get("description"),
        )
    )


async def test_published_schema_is_retrieved_by_latest(schema_repo, example_schema):
    await _publish(schema_repo, example_schema)
    retrieved = await _service(schema_repo).get_schema(
        GetSchemaCommand(name=example_schema["name"])
    )
    assert retrieved.version == example_schema["version"]


async def test_specific_version_is_retrieved_by_identity(schema_repo, example_schema):
    await _publish(schema_repo, example_schema)
    retrieved = await _service(schema_repo).get_schema(
        GetSchemaCommand(name=example_schema["name"], version=example_schema["version"])
    )
    assert retrieved.name == example_schema["name"]
    assert retrieved.version == example_schema["version"]


async def test_unknown_schema_raises(schema_repo):
    with pytest.raises(SchemaNotFoundError):
        await _service(schema_repo).get_schema(GetSchemaCommand(name="does-not-exist"))


async def test_invalid_name_raises_validation_error(schema_repo):
    with pytest.raises(ValidationError):
        await _service(schema_repo).publish_schema(
            PublishCommand(name="has spaces!", version="1.0", json_schema={})
        )


async def test_list_versions_unknown_name_raises(schema_repo):
    """Every backend raises for an unknown name (a name exists iff it has >=1 version),
    which the service translates to `SchemaNotFoundError`.
    """
    with pytest.raises(SchemaNotFoundError):
        [
            s
            async for s in _service(schema_repo).list_schema_versions(
                ListVersionsCommand(name="does-not-exist")
            )
        ]


# ---- metadata update (PATCH): mutable-only, owner-gated ---------------------------


async def _update(repo, schema, deprecated=None):
    return await _service(repo).update_schema_metadata(
        MetadataUpdateCommand(
            name=schema["name"],
            version=schema["version"],
            deprecated=deprecated,
        )
    )


async def test_publish_defaults_deprecated_to_false(schema_repo, example_schema):
    published = await _publish(schema_repo, example_schema)
    assert published.deprecated is False


# ---- successor reference (set/clear, internal existence + self-reference) -----------

_EXTERNAL_SUCCESSOR = "https://other.example.com/api/schemas/elsewhere/versions/9"


async def _set_successor(repo, schema, *, successor, target=None):
    command_args = {
        "name": schema["name"],
        "version": schema["version"],
        "successor": successor,
    }
    if target is not None:
        command_args["successor_target"] = target
    return await _service(repo).update_schema_metadata(MetadataUpdateCommand(**command_args))


async def test_update_internal_successor_to_existing_target(schema_repo, example_schema):
    await _publish(schema_repo, {**example_schema, "version": "1"})
    await _publish(schema_repo, {**example_schema, "version": "2"})
    updated = await _set_successor(
        schema_repo,
        {**example_schema, "version": "1"},
        successor=SuccessorReference(url=_EXTERNAL_SUCCESSOR),
        target=SchemaIdentity(name=example_schema["name"], version="2"),
    )
    assert str(updated.successor) == _EXTERNAL_SUCCESSOR


async def test_update_internal_successor_must_exist(schema_repo, example_schema):
    await _publish(schema_repo, example_schema)
    with pytest.raises(InvalidSuccessorError):
        await _set_successor(
            schema_repo,
            example_schema,
            successor=SuccessorReference(url=_EXTERNAL_SUCCESSOR),
            target=SchemaIdentity(name="ghost", version="1"),
        )


async def test_update_rejects_self_successor(schema_repo, example_schema):
    await _publish(schema_repo, example_schema)
    with pytest.raises(InvalidSuccessorError):
        await _set_successor(
            schema_repo,
            example_schema,
            successor=SuccessorReference(url=_EXTERNAL_SUCCESSOR),
            target=SchemaIdentity(
                name=example_schema["name"], version=example_schema["version"]
            ),
        )


async def test_update_with_no_changes_leaves_the_version_untouched(schema_repo, example_schema):
    published = await _publish(schema_repo, example_schema)
    updated = await _update(schema_repo, example_schema)
    assert updated.deprecated is published.deprecated
    assert updated.successor == published.successor


async def test_update_unknown_schema_raises(schema_repo, example_schema):
    with pytest.raises(SchemaNotFoundError):
        await _update(schema_repo, example_schema)
