from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from kernel.db.dashboard import counts_by_day
from kernel.db.session import session


@pytest.mark.asyncio
async def test_counts_by_day_buckets_sources(make_user):  # type: ignore[no-untyped-def]
    uid = await make_user()
    now = datetime.now(UTC)
    today = now.date()
    yesterday = today - timedelta(days=1)
    async with session(uid) as conn:
        for i, ts in enumerate((now, now, now - timedelta(days=1))):
            await conn.execute(
                text(
                    "INSERT INTO sources (user_id, source_type, checksum_sha256, imported_at) "
                    "VALUES (:u, 'json', :c, :ts)"
                ),
                {"u": str(uid), "c": f"chk-{i}", "ts": ts},
            )
        result = await counts_by_day(conn, now - timedelta(days=7))
    by_day = dict(result["sources"])
    assert by_day.get(today) == 2
    assert by_day.get(yesterday) == 1


@pytest.mark.asyncio
async def test_counts_by_day_excludes_before_since(make_user):  # type: ignore[no-untyped-def]
    uid = await make_user()
    now = datetime.now(UTC)
    async with session(uid) as conn:
        await conn.execute(
            text(
                "INSERT INTO sources (user_id, source_type, checksum_sha256, imported_at) "
                "VALUES (:u, 'json', :c, :ts)"
            ),
            {"u": str(uid), "c": "old", "ts": now - timedelta(days=40)},
        )
        result = await counts_by_day(conn, now - timedelta(days=7))
    assert result["sources"] == []
