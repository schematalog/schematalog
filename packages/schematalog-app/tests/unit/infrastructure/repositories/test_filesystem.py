"""The filesystem backend's own behaviour: its on-disk store, not the shared contract.

The conformance cases in `tests/unit/application/test_schema.py` run against every
backend; these cover what is true only of this one.
"""

from pathlib import Path

import pytest

from schematalog.app.infrastructure.repositories import FilesystemSchemaRepository
from schematalog.domain.schema import JsonSchemaDocument, Schema, SchemaIdentity

_DOCUMENT = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}


def _schema(name: str, version: str) -> Schema:
    return Schema(
        identity=SchemaIdentity(name=name, version=version),
        json_schema=JsonSchemaDocument(document=dict(_DOCUMENT)),
    )


async def test_a_reopened_directory_still_holds_its_schemas(tmp_path):
    """The store outlives the process, which is the point of this backend.

    Every other in-process backend starts empty each time, so this is the one place the
    suite checks that a repository opened over an existing directory reads what a
    previous one wrote - the case an operator relies on at every restart.
    """
    directory = tmp_path / "schemas"
    written = await FilesystemSchemaRepository(directory=directory).add(_schema("person", "1"))

    reopened = FilesystemSchemaRepository(directory=directory)
    read_back = await reopened.get(SchemaIdentity(name="person", version="1"))

    assert read_back.publication_id == written.publication_id
    assert read_back.published_on == written.published_on
    assert read_back.json_schema.document == _DOCUMENT
    assert [name async for name in reopened.list_names()] == ["person"]


async def test_a_missing_directory_is_created(tmp_path):
    directory = tmp_path / "does-not-exist-yet"
    FilesystemSchemaRepository(directory=directory)
    assert directory.is_dir()


def test_a_path_that_is_not_a_directory_is_refused(tmp_path):
    not_a_directory = tmp_path / "a-file"
    not_a_directory.write_text("")
    with pytest.raises(ValueError, match="directory"):
        FilesystemSchemaRepository(directory=not_a_directory)


async def test_names_with_no_versions_are_not_listed(tmp_path):
    """An empty directory is not a schema; listing it would break the derived latest."""
    directory = tmp_path / "schemas"
    repo = FilesystemSchemaRepository(directory=directory)
    await repo.add(_schema("real", "1"))
    Path(directory / "leftover").mkdir()
    assert [name async for name in repo.list_names()] == ["real"]


async def test_a_metadata_update_leaves_no_half_written_file(tmp_path):
    """The update writes a sibling and renames it, so a reader never sees a partial file.

    The rename also has to leave the directory clean: a temporary left behind would be
    read back as a schema version named after the temporary file.
    """
    directory = tmp_path / "schemas"
    repo = FilesystemSchemaRepository(directory=directory)
    schema = await repo.add(_schema("person", "1"))
    await repo.set_metadata(schema.identity, deprecated=True)

    files = sorted(p.name for p in (directory / "person").iterdir())
    assert files == ["1.json"]
    assert [s.version async for s in repo.list_versions("person")] == ["1"]
