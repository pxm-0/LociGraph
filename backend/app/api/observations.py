from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from kernel.db.observations import ObservationRepository
from kernel.db.session import session

router = APIRouter()


@router.get("/observations")
async def list_observations(
    source_id: str | None = None,
    speaker: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        obs = await ObservationRepository(conn).list(
            source_id=source_id,
            speaker=speaker,
            status=status,
            limit=limit,
            offset=offset,
        )
    return [
        {
            "id": str(o.id),
            "content": o.content,
            "speaker": o.speaker,
            "observed_at": o.observed_at.isoformat() if o.observed_at else None,
            "confidence": o.confidence,
            "source_id": str(o.source_id) if o.source_id else None,
        }
        for o in obs
    ]


@router.get("/observations/count")
async def count_observations(
    source_id: str | None = None,
    speaker: str | None = None,
    status: str | None = None,
    user_id: str = Depends(get_current_user),
) -> dict[str, int]:
    async with session(user_id) as conn:
        total = await ObservationRepository(conn).count(
            source_id=source_id, speaker=speaker, status=status
        )
    return {"total": total}
