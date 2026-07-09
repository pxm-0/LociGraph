import uuid

import pytest
import sqlalchemy.exc
from sqlalchemy import text

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
async def test_update_storage_path(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        src = await repo.create(user_id, "json", "checksum-path-test")
        await repo.update_storage_path(src.id, "/tmp/test/path.json")
        fetched = await repo.get(src.id)
    assert fetched is not None
    assert fetched.raw_storage_path == "/tmp/test/path.json"


@pytest.mark.asyncio
async def test_duplicate_checksum_rejected(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        await repo.create(user_id, "json", "dupe")
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await repo.create(user_id, "json", "dupe")


@pytest.mark.asyncio
async def test_purge_transitions_status_and_clears_storage_path(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        src = await repo.create(user_id, "pdf", "checksum-purge")
        await repo.update_storage_path(src.id, "/tmp/test/purge.pdf")

        purged = await repo.purge(src.id)
        fetched = await repo.get(src.id)

        # Verify purged_at was actually set in the database
        row = (await conn.execute(
            text("SELECT purged_at FROM sources WHERE id = :id"),
            {"id": str(src.id)},
        )).mappings().first()

    assert purged is True
    assert fetched is not None
    assert fetched.import_status == "PURGED"
    assert fetched.raw_storage_path is None
    assert row is not None
    assert row["purged_at"] is not None


@pytest.mark.asyncio
async def test_purge_returns_false_for_nonexistent_id(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        purged = await repo.purge(uuid.uuid4())
    assert purged is False


@pytest.mark.asyncio
async def test_get_by_type_finds_a_matching_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        await repo.create(user_id, "json", "get-by-type-1")
        custodian_source = await repo.create(user_id, "custodian", "get-by-type-2")
        found = await repo.get_by_type("custodian")

    assert found is not None
    assert found.id == custodian_source.id
