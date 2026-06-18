import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Migrations run as the OWNER role.
DATABASE_URL = os.environ["MIGRATION_DATABASE_URL"]


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


run_migrations_online()
