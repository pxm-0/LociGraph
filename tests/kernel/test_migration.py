import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

OWNER_URL = os.environ["MIGRATION_DATABASE_URL"]


@pytest.mark.asyncio
async def test_rls_is_forced_on_data_tables():
    engine = create_async_engine(OWNER_URL)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT relname FROM pg_class "
                    "WHERE relrowsecurity AND relforcerowsecurity "
                    "ORDER BY relname"
                )
            )
            forced = {r[0] for r in rows}
        assert {"sources", "fragments", "observations", "jobs"} <= forced
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_app_role_exists_and_is_not_superuser():
    engine = create_async_engine(OWNER_URL)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles "
                        "WHERE rolname = 'locigraph_app'"
                    )
                )
            ).first()
        assert row is not None, "locigraph_app role must exist"
        assert row[0] is False, "app role must not be superuser"
        assert row[1] is False, "app role must not bypass RLS"
    finally:
        await engine.dispose()
