from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from backend.app.api.sources import serialize_source
from backend.app.auth.dependencies import get_current_user
from kernel.db.claims import ClaimRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.dashboard import counts_by_day
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository

router = APIRouter()


@router.get("/dashboard/summary")
async def dashboard_summary(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        sources = SourceRepository(conn)
        observations = ObservationRepository(conn)
        claims = ClaimRepository(conn)
        concepts = ConceptRepository(conn)
        jobs = JobRepository(conn)
        recent_sources = await sources.list(limit=5)
        return {
            "source_count": await sources.count(),
            "observation_count": await observations.count(),
            "claim_count": await claims.count(),
            "concept_count": await concepts.count(),
            "pending_job_count": await jobs.count_by_statuses(["pending", "running"]),
            "recent_sources": [
                await serialize_source(source, observations, claims)
                for source in recent_sources
            ],
        }


@router.get("/dashboard/trends")
async def dashboard_trends(
    window: int = 30,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    window = max(1, min(window, 365))
    start_day = (datetime.now(UTC) - timedelta(days=window - 1)).date()
    days = [start_day + timedelta(days=i) for i in range(window)]
    since = datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC)
    async with session(user_id) as conn:
        raw = await counts_by_day(conn, since)
    series = {
        entity: [{"date": d.isoformat(), "count": found.get(d, 0)} for d in days]
        for entity, points in raw.items()
        for found in (dict(points),)
    }
    return {"window_days": window, "series": series}
