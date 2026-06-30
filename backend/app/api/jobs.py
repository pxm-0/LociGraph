from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.dependencies import get_current_user
from kernel.db.jobs import JobRepository
from kernel.db.session import session
from kernel.models import Job

router = APIRouter()


def _serialize(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "attempts": job.attempts,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        job = await JobRepository(conn).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not found")
    return _serialize(job)
