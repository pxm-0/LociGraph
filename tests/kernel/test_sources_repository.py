import pytest
import sqlalchemy.exc

from kernel.db.session import session
from kernel.db.sources import SourceRepository


@pytest.mark.asyncio
async def test_create_and_get_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        created = await repo.create(
            user_id, "markdown", "checksum-1", original_filename="a.md"
        )
        fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.source_type == "markdown"
    assert fetched.import_status == "PENDING"
    assert fetched.original_filename == "a.md"


@pytest.mark.asyncio
async def test_status_transitions(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        src = await repo.create(user_id, "pdf", "checksum-2")
        await repo.set_status(src.id, "INGESTING")
        await repo.mark_verified(src.id)
        fetched = await repo.get(src.id)
    assert fetched is not None
    assert fetched.import_status == "VERIFIED"
    assert fetched.verified_at is not None


@pytest.mark.asyncio
async def test_duplicate_checksum_rejected(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        await repo.create(user_id, "json", "dupe")
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await repo.create(user_id, "json", "dupe")
