from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from kernel.db.claims import ClaimRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from kernel.models import Source

router = APIRouter()


async def _serialize_source(
    source: Source, observations: ObservationRepository, claims: ClaimRepository
) -> dict[str, Any]:
    claim_count = await claims.count_for_source(source.id)
    extraction_status = "ready" if source.import_status == "VERIFIED" else "waiting"
    if claim_count:
        extraction_status = "proposed"
    return {
        "id": str(source.id),
        "source_type": source.source_type,
        "original_filename": source.original_filename,
        "import_status": source.import_status,
        "file_size_bytes": source.file_size_bytes,
        "imported_at": source.imported_at.isoformat() if source.imported_at else None,
        "observation_count": await observations.count_for_source(source.id),
        "claim_count": claim_count,
        "claim_extraction_status": extraction_status,
    }


@router.get("/dashboard/summary")
async def dashboard_summary(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        sources = SourceRepository(conn)
        observations = ObservationRepository(conn)
        claims = ClaimRepository(conn)
        jobs = JobRepository(conn)
        recent_sources = await sources.list(limit=5)
        return {
            "source_count": await sources.count(),
            "observation_count": await observations.count(),
            "pending_job_count": await jobs.count_by_statuses(["pending", "running"]),
            "recent_sources": [
                await _serialize_source(source, observations, claims)
                for source in recent_sources
            ],
        }
