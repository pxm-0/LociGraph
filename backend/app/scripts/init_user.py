from __future__ import annotations

import asyncio

from backend.app.config import Settings
from kernel.auth.passwords import hash_password
from kernel.db.engine import get_engine
from kernel.db.users import UserRepository


async def init_user() -> bool:
    settings = Settings.from_env()
    engine = get_engine()
    async with engine.begin() as conn:
        repo = UserRepository(conn)
        if await repo.get_by_email(settings.locigraph_email) is not None:
            return False
        await repo.create(settings.locigraph_email, hash_password(settings.locigraph_password))
        return True


if __name__ == "__main__":
    created = asyncio.run(init_user())
    print("created" if created else "already exists")
