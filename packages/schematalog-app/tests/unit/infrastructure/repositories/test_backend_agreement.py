"""Generated cases asserting the backends answer a search identically.

The conformance suite states the search guarantee by example; this states it as a
property. Both bugs this codebase has had in this area were divergences no chosen
example happened to cover - `COLLATE "C"`, where PostgreSQL and SQLite disagreed about
ordering, and a null byte that returned nothing on one backend and raised on another -
so the case for generating the examples rather than picking them is not hypothetical.

The oracle is the domain's own predicate: whatever a backend does underneath, its answer
must equal filtering the stored schemas through `SearchQuery.matches` and sorting by name.
That is the "faster, never different" promise written as something a machine can check.
"""

import asyncio
import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import create_async_engine

from schematalog.app.infrastructure.repositories.memory import MemorySchemaRepository
from schematalog.app.infrastructure.repositories.sqlalchemy import SQLAlchemySchemaRepository
from schematalog.domain.schema import Schema, SearchQuery

# Deliberately tiny, and short: near misses are what break a SQL `LIKE`, and a wider
# alphabet never generates them. Do not widen it without re-checking it still fails
# when the escaping of `_` is removed.
ALPHABET = "ab_.-A"
FIRST = st.sampled_from("abA")
REST = st.text(alphabet=ALPHABET, min_size=0, max_size=3)
names = st.builds(lambda head, tail: head + tail, FIRST, REST)
# Descriptions draw from the same alphabet plus spaces, so a term can land in either
# field - which is where an OR/AND mix-up and an uncoalesced NULL both show up. Empty
# is included deliberately: it is what a schema nobody described stores.
descriptions = st.text(alphabet=ALPHABET + " ", min_size=0, max_size=6)
# Queries come from the same alphabet as names, plus the space that separates terms,
# since anything else is rejected at the boundary and never reaches a repository.
queries = st.text(alphabet=ALPHABET + " ", min_size=0, max_size=5)


def build(name: str, description: str = "") -> Schema:
    return Schema.model_validate(
        {
            "name": name,
            "version": "1",
            "description": description,
            "schema": {"type": "object"},
            "publication_id": str(uuid.uuid7()),
        }
    )


async def _answers(repository, schemas, query):
    for schema in schemas:
        await repository.add(schema)
    return [s.name async for s in repository.list_latest(query=query)]


def _matches(schema, query: SearchQuery | None) -> bool:
    return query is None or query.matches(schema)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    names=st.lists(names, min_size=0, max_size=6, unique=True),
    descriptions=st.lists(descriptions, min_size=6, max_size=6),
    query=queries,
)
def test_every_backend_answers_a_search_the_same_way(names, descriptions, query):
    async def run():
        schemas = [build(name, text) for name, text in zip(names, descriptions, strict=False)]
        parsed = SearchQuery.parse(query)
        expected = sorted(s.name for s in schemas if _matches(s, parsed))

        memory = await _answers(MemorySchemaRepository(), schemas, parsed)
        sql = await _answers(
            SQLAlchemySchemaRepository(create_async_engine("sqlite+aiosqlite:///:memory:")),
            schemas,
            parsed,
        )
        assert memory == expected, "the in-Python backend disagrees with the predicate"
        assert sql == expected, "the SQL pushdown disagrees with the predicate"

    asyncio.run(run())
