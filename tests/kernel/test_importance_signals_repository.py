from __future__ import annotations

from uuid import uuid4

import pytest

from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.session import session


@pytest.mark.asyncio
async def test_create_and_list_for_target(make_user):
    user_id = await make_user()
    target_id = uuid4()
    async with session(user_id) as conn:
        repo = ImportanceSignalRepository(conn)
        created = await repo.create(user_id=user_id, target_type="claim", target_id=target_id)
        listed = await repo.list_for_target("claim", target_id)

    assert created.target_type == "claim"
    assert [s.id for s in listed] == [created.id]
