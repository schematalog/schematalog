"""The storage contract, expressed as tests a backend must pass.

Subclass it, supply a `repository` fixture yielding an **empty** repository, and the
whole specification comes with it:

    from schematalog.testing import SchemaRepositoryConformance

    class TestMyBackend(SchemaRepositoryConformance):
        @pytest.fixture
        async def repository(self):
            repo = MyRepository(...)
            yield repo
            await repo.teardown()

How the repository is emptied is the author's business - a temporary directory, a fresh
database, a truncate. The contract deliberately carries no reset operation, because the
running application never needs one.

Every case here is `async def`, so the suite needs pytest-asyncio in automatic mode
(`asyncio_mode = "auto"`); under its default strict mode every case errors out on the
fixture instead of running. The plugin ships with the `testing` extra, but the mode is
the author's own configuration and cannot be set from here.

These cases test a *repository*, not the service above it: they are the behaviour a
backend owes, and nothing about validation, HTTP or command handling. Three of the eight
methods are derived by `SchemaRepository` itself, so a backend that overrides them for
efficiency is checked here against the same expectations as one that does not.
"""

import asyncio

import pytest

from schematalog.domain.exceptions import SchemaConflictError, UnknownSchemaError
from schematalog.domain.schema import (
    JsonSchemaDocument,
    Schema,
    SchemaDescription,
    SchemaIdentity,
    SchemaRepository,
    SuccessorReference,
)
from schematalog.testing.samples import example_document

DOCUMENT = example_document()
"""A document with nesting, arrays and mixed types - a trivial one would round-trip
through almost anything and so would check almost nothing."""
SUCCESSOR_URL = "https://example.com/api/schemas/other/versions/2"


def build_schema(name: str = "person", version: str = "1", description: str = ""):
    """A minimal valid `Schema`, with its publication identifier minted as usual."""
    return Schema(
        identity=SchemaIdentity(name=name, version=version),
        description=SchemaDescription(text=description),
        json_schema=JsonSchemaDocument(document=dict(DOCUMENT)),
    )


class SchemaRepositoryConformance:
    """Every behaviour a `SchemaRepository` implementation owes its callers."""

    @pytest.fixture
    def repository(self) -> SchemaRepository:
        """An empty repository under test. **Subclasses must override this.**"""
        raise NotImplementedError("Supply a `repository` fixture yielding an empty repository.")

    # ---- add ------------------------------------------------------------------------

    async def test_add_stores_the_version_and_returns_it(self, repository):
        stored = await repository.add(build_schema(description="A person."))
        assert stored.name == "person"
        assert stored.version == "1"
        read_back = await repository.get(SchemaIdentity(name="person", version="1"))
        assert read_back.json_schema.document == DOCUMENT
        assert str(read_back.description) == "A person."

    async def test_add_preserves_the_publication_identifier_it_was_given(self, repository):
        """The identifier is minted above the repository; a backend stores what it gets.

        A backend that minted its own would order correctly in isolation and wrongly
        against anything that had already read the value.
        """
        schema = build_schema()
        stored = await repository.add(schema)
        assert stored.publication_id == schema.publication_id
        read_back = await repository.get(schema.identity)
        assert read_back.publication_id == schema.publication_id
        assert read_back.published_on == schema.published_on

    async def test_add_refuses_a_duplicate_name_and_version(self, repository):
        await repository.add(build_schema())
        with pytest.raises(SchemaConflictError):
            await repository.add(build_schema())

    async def test_add_accepts_another_version_of_the_same_name(self, repository):
        await repository.add(build_schema(version="1"))
        await repository.add(build_schema(version="2"))
        assert [s.version async for s in repository.list_versions("person")] == ["2", "1"]

    # ---- get ------------------------------------------------------------------------

    async def test_get_refuses_an_unknown_name(self, repository):
        with pytest.raises(UnknownSchemaError):
            await repository.get(SchemaIdentity(name="nobody", version="1"))

    async def test_get_refuses_an_unknown_version_of_a_known_name(self, repository):
        await repository.add(build_schema(version="1"))
        with pytest.raises(UnknownSchemaError):
            await repository.get(SchemaIdentity(name="person", version="99"))

    # ---- set_metadata ---------------------------------------------------------------

    async def test_set_metadata_sets_and_persists_deprecation(self, repository):
        schema = await repository.add(build_schema())
        updated = await repository.set_metadata(schema.identity, deprecated=True)
        assert updated.deprecated is True
        assert (await repository.get(schema.identity)).deprecated is True

    async def test_set_metadata_sets_changes_and_clears_a_successor(self, repository):
        schema = await repository.add(build_schema())
        await repository.set_metadata(
            schema.identity, successor=SuccessorReference(url=SUCCESSOR_URL)
        )
        assert str((await repository.get(schema.identity)).successor) == SUCCESSOR_URL
        await repository.set_metadata(schema.identity, successor=None)
        assert (await repository.get(schema.identity)).successor is None

    async def test_set_metadata_leaves_the_immutable_fields_alone(self, repository):
        schema = await repository.add(build_schema(description="Original."))
        updated = await repository.set_metadata(schema.identity, deprecated=True)
        assert updated.publication_id == schema.publication_id
        assert updated.json_schema.document == DOCUMENT
        assert str(updated.description) == "Original."

    async def test_set_metadata_refuses_an_unknown_version(self, repository):
        with pytest.raises(UnknownSchemaError):
            await repository.set_metadata(
                SchemaIdentity(name="nobody", version="1"), deprecated=True
            )

    # ---- list_versions --------------------------------------------------------------

    async def test_list_versions_yields_newest_first(self, repository):
        for version in ("1", "2", "3"):
            await repository.add(build_schema(version=version))
        assert [s.version async for s in repository.list_versions("person")] == ["3", "2", "1"]

    async def test_list_versions_orders_by_publication_not_by_string(self, repository):
        """`10` sorts below `9` as a string and above it as a publication."""
        for version in ("9", "10"):
            await repository.add(build_schema(version=version))
        assert [s.version async for s in repository.list_versions("person")] == ["10", "9"]

    async def test_list_versions_holds_its_order_across_a_millisecond(self, repository):
        """A store that loses the identifier's byte order still passes a same-millisecond test."""
        await repository.add(build_schema(version="1"))
        await asyncio.sleep(0.005)
        await repository.add(build_schema(version="2"))
        assert [s.version async for s in repository.list_versions("person")] == ["2", "1"]

    async def test_list_versions_refuses_an_unknown_name(self, repository):
        with pytest.raises(UnknownSchemaError):
            [s async for s in repository.list_versions("nobody")]

    # ---- list_names -----------------------------------------------------------------

    async def test_list_names_is_empty_for_an_empty_store(self, repository):
        assert [n async for n in repository.list_names()] == []

    async def test_list_names_yields_each_name_once_ascending(self, repository):
        for name, version in (("beta", "1"), ("alpha", "1"), ("alpha", "2")):
            await repository.add(build_schema(name=name, version=version))
        assert [n async for n in repository.list_names()] == ["alpha", "beta"]

    async def test_list_names_orders_by_byte_value(self, repository):
        """Names order by byte value, which is part of the contract rather than a detail.

        Two instances read the same catalog and must list it identically, so "ascending"
        has to mean one thing. Mixed case and punctuation are what separate the
        candidates: byte order puts `Beta` before `alpha` (`B` is 0x42, `a` is 0x61),
        while a case-insensitive or locale-aware ordering puts `alpha` first.

        A store that sorts in Python satisfies this without trying, and so does SQLite,
        whose default `BINARY` collation agrees with Python. A store that delegates
        sorting to a database with its own idea of ordering does not: PostgreSQL uses a
        locale collation by default, which is why the identifier columns here pin
        `COLLATE "C"`, and MySQL's default is case- and accent-insensitive, so a MySQL
        backend would fail this until it said otherwise. If your store has a collation
        setting, this is the test that tells you which one to choose.
        """
        for name in ("beta", "Beta", "alpha-two", "alphaone"):
            await repository.add(build_schema(name=name))
        assert [n async for n in repository.list_names()] == sorted(
            ["beta", "Beta", "alpha-two", "alphaone"]
        )

    # ---- get_latest (derived, may be overridden) ------------------------------------

    async def test_get_latest_is_the_most_recent_publication(self, repository):
        for version in ("9", "10"):
            await repository.add(build_schema(version=version))
        assert (await repository.get_latest("person")).version == "10"

    async def test_get_latest_skips_a_deprecated_version(self, repository):
        await repository.add(build_schema(version="1"))
        newer = await repository.add(build_schema(version="2"))
        await repository.set_metadata(newer.identity, deprecated=True)
        assert (await repository.get_latest("person")).version == "1"

    async def test_get_latest_skips_a_superseded_version(self, repository):
        await repository.add(build_schema(version="1"))
        newer = await repository.add(build_schema(version="2"))
        await repository.set_metadata(
            newer.identity, successor=SuccessorReference(url=SUCCESSOR_URL)
        )
        assert (await repository.get_latest("person")).version == "1"

    async def test_get_latest_falls_back_when_nothing_is_current(self, repository):
        """Every version disqualified still has to yield an answer - the newest one."""
        for version in ("1", "2"):
            schema = await repository.add(build_schema(version=version))
            await repository.set_metadata(schema.identity, deprecated=True)
        assert (await repository.get_latest("person")).version == "2"

    async def test_get_latest_refuses_an_unknown_name(self, repository):
        with pytest.raises(UnknownSchemaError):
            await repository.get_latest("nobody")

    # ---- list_latest (derived, may be overridden) -----------------------------------

    async def test_list_latest_yields_one_version_per_name_ascending(self, repository):
        await repository.add(build_schema(name="beta", version="1"))
        await repository.add(build_schema(name="alpha", version="1"))
        await repository.add(build_schema(name="alpha", version="2"))
        assert [(s.name, s.version) async for s in repository.list_latest()] == [
            ("alpha", "2"),
            ("beta", "1"),
        ]

    async def test_list_latest_applies_the_same_rule_as_get_latest(self, repository):
        await repository.add(build_schema(name="alpha", version="1"))
        newer = await repository.add(build_schema(name="alpha", version="2"))
        await repository.set_metadata(newer.identity, deprecated=True)
        assert [s.version async for s in repository.list_latest()] == ["1"]

    async def test_list_latest_is_empty_for_an_empty_store(self, repository):
        assert [s async for s in repository.list_latest()] == []

    # ---- search: the guarantee every backend must meet exactly ----
    # A case-insensitive substring of the name, name-ascending, filtered not ranked.
    # A backend that stems, fuzzy-matches or reorders fails here.

    async def test_list_latest_filters_by_a_name_substring(self, repository):
        await repository.add(build_schema(name="billing.invoice", version="1"))
        await repository.add(build_schema(name="billing.payment", version="1"))
        await repository.add(build_schema(name="shipping.parcel", version="1"))
        assert [s.name async for s in repository.list_latest(query="billing")] == [
            "billing.invoice",
            "billing.payment",
        ]

    async def test_list_latest_matches_a_substring_anywhere_in_the_name(self, repository):
        await repository.add(build_schema(name="billing.invoice", version="1"))
        assert [s.name async for s in repository.list_latest(query="voi")] == [
            "billing.invoice"
        ]

    async def test_list_latest_matches_regardless_of_case(self, repository):
        await repository.add(build_schema(name="Billing", version="1"))
        for query in ("billing", "BILLING", "BiLLiNg"):
            assert [s.name async for s in repository.list_latest(query=query)] == ["Billing"]

    async def test_list_latest_treats_a_blank_query_as_no_query(self, repository):
        """An empty search box selects everything, rather than nothing."""
        await repository.add(build_schema(name="alpha", version="1"))
        for query in (None, "", "   "):
            assert [s.name async for s in repository.list_latest(query=query)] == ["alpha"]

    async def test_list_latest_yields_nothing_when_the_query_matches_nothing(self, repository):
        await repository.add(build_schema(name="alpha", version="1"))
        assert [s async for s in repository.list_latest(query="omega")] == []

    async def test_list_latest_keeps_its_name_order_when_filtering(self, repository):
        for name in ("gamma.one", "alpha.one", "beta.one"):
            await repository.add(build_schema(name=name, version="1"))
        assert [s.name async for s in repository.list_latest(query="one")] == [
            "alpha.one",
            "beta.one",
            "gamma.one",
        ]

    async def test_list_latest_filters_without_stemming_the_query(self, repository):
        """A longer query does not match a shorter name.

        The case a full-text backend fails if it turns matching on: an engine with
        stemming would answer "orders" with `order`, which is a better search and a
        different one. Being different is what is disallowed.
        """
        await repository.add(build_schema(name="order", version="1"))
        assert [s async for s in repository.list_latest(query="orders")] == []

    async def test_list_latest_treats_sql_wildcards_as_ordinary_characters(self, repository):
        """`_` and `%` are legal in a name and mean nothing special in a query.

        `_` matches any single character in SQL `LIKE`, so a backend that interpolates
        the query into a pattern without escaping answers this with both names.
        """
        await repository.add(build_schema(name="a_b", version="1"))
        await repository.add(build_schema(name="axb", version="1"))
        assert [s.name async for s in repository.list_latest(query="a_b")] == ["a_b"]

    async def test_list_latest_searches_only_the_latest_version(self, repository):
        """One hit per name, not one per version - the filter narrows the same listing."""
        await repository.add(build_schema(name="alpha", version="1"))
        await repository.add(build_schema(name="alpha", version="2"))
        assert [(s.name, s.version) async for s in repository.list_latest(query="alpha")] == [
            ("alpha", "2")
        ]

    # ---- list_predecessors (derived, may be overridden) -----------------------------

    async def test_list_predecessors_finds_every_version_pointing_at_the_url(self, repository):
        for name in ("beta", "alpha"):
            schema = await repository.add(build_schema(name=name, version="1"))
            await repository.set_metadata(
                schema.identity, successor=SuccessorReference(url=SUCCESSOR_URL)
            )
        await repository.add(build_schema(name="unrelated", version="1"))
        found = [s.name async for s in repository.list_predecessors(SUCCESSOR_URL)]
        assert found == ["alpha", "beta"]

    async def test_list_predecessors_is_empty_when_nothing_points_there(self, repository):
        await repository.add(build_schema())
        assert [s async for s in repository.list_predecessors(SUCCESSOR_URL)] == []
