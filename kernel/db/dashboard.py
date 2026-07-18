from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# Per-entity timestamp column: sources tracks ``imported_at``; the rest use
# ``created_at``. These are fixed constants (never user input), so interpolating
# them into the query is safe.
_ENTITY_TS = {
    "sources": "imported_at",
    "claims": "created_at",
    "concepts": "created_at",
    "contradictions": "created_at",
}


async def counts_by_day(
    conn: AsyncConnection, since: datetime
) -> dict[str, list[tuple[date, int]]]:
    """New-row counts per day (``created_at``/``imported_at`` >= ``since``), one
    ascending series per entity. RLS-scoped by the caller's ``session``. Only
    non-empty days are returned; the API layer zero-fills to a contiguous window.
    """
    out: dict[str, list[tuple[date, int]]] = {}
    for entity, ts_col in _ENTITY_TS.items():
        rows = (
            await conn.execute(
                text(
                    f"SELECT date_trunc('day', {ts_col})::date AS d, count(*) AS c "
                    f"FROM {entity} WHERE {ts_col} >= :since GROUP BY d ORDER BY d"
                ),
                {"since": since},
            )
        ).all()
        out[entity] = [(r[0], int(r[1])) for r in rows]
    return out
