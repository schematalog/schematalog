import asyncio

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from schematalog.app.infrastructure.repositories import SQLAlchemySchemaRepository


async def test_ensure_tables_skips_recreation_for_a_waiting_caller():
    """A second caller blocked on the init lock must not re-create the tables:
    once the first caller marks initialisation done, the waiter resumes and
    returns via the double-checked guard rather than running `create_all` again.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    repo = SQLAlchemySchemaRepository(engine)
    async with repo._init_lock:
        waiter = asyncio.create_task(repo._ensure_tables())
        await asyncio.sleep(0)  # let the waiter park on the lock
        repo._initialized = True
    await waiter  # resumes, sees the flag set, returns via the inner guard
    assert repo._initialized is True
    await engine.dispose()
