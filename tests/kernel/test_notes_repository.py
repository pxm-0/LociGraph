from __future__ import annotations

import pytest

from kernel.db.notes import NoteRepository
from kernel.db.session import session


@pytest.mark.asyncio
async def test_create_and_list_notes(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = NoteRepository(conn)
        created = await repo.create(user_id=user_id, content="Remember to check the archive.")
        listed = await repo.list()

    assert created.content == "Remember to check the archive."
    assert [n.id for n in listed] == [created.id]
