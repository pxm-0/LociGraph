from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError

from backend.app.auth.dependencies import get_current_user
from backend.app.config import Settings
from backend.app.jobs.submit import submit_ingest
from kernel.db.claims import ClaimRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from kernel.ingestion.base import SourceType
from kernel.models import Source
from kernel.storage import delete_raw, save_raw
from worker.tasks.extract_claims import dispatch_claim_extraction_jobs, plan_claim_extraction_jobs

router = APIRouter()


async def serialize_source(
    s: Source, observations: ObservationRepository, claims: ClaimRepository
) -> dict[str, Any]:
    claim_count = await claims.count_for_source(s.id)
    extraction_status = "ready" if s.import_status == "VERIFIED" else "waiting"
    if claim_count:
        extraction_status = "proposed"
    return {
        "id": str(s.id),
        "source_type": s.source_type,
        "original_filename": s.original_filename,
        "import_status": s.import_status,
        "file_size_bytes": s.file_size_bytes,
        "imported_at": s.imported_at.isoformat() if s.imported_at else None,
        "observation_count": await observations.count_for_source(s.id),
        "claim_count": claim_count,
        "claim_extraction_status": extraction_status,
    }


@router.post("/sources/upload", status_code=202)
async def upload_source(
    source_type: str = Form(...),
    file: UploadFile = File(...),  # noqa: B008
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    if source_type not in SourceType.ALL:
        raise HTTPException(status_code=400, detail=f"invalid source_type: {source_type}")
    data = await file.read()
    checksum = hashlib.sha256(data).hexdigest()
    source_id: UUID
    job_id: UUID
    try:
        async with session(user_id) as conn:
            # ORDER IS INTENTIONAL: create()'s INSERT enforces UNIQUE(user_id, checksum_sha256)
            # and raises IntegrityError for duplicates BEFORE save_raw() writes any file,
            # so a duplicate upload is rejected without orphaning anything on disk. MUST stay first.
            source = await SourceRepository(conn).create(
                user_id,
                source_type,
                checksum,
                original_filename=file.filename,
                original_mime_type=file.content_type,
                file_size_bytes=len(data),
            )
            path = save_raw(
                Path(Settings.from_env().raw_storage_path),
                user_id,
                source.id,
                file.filename or "upload",
                data,
            )
            await SourceRepository(conn).update_storage_path(source.id, path)
            job = await JobRepository(conn).create(
                user_id, "ingest_source", payload={"source_id": str(source.id)}
            )
            source_id = source.id
            job_id = job.id
    except IntegrityError:
        raise HTTPException(status_code=409, detail="duplicate source (checksum)") from None

    submit_ingest(str(source_id), str(user_id), str(job_id))
    return {"source_id": str(source_id), "job_id": str(job_id), "status": "PENDING"}


@router.get("/sources")
async def list_sources(
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        sources = await SourceRepository(conn).list()
        observations = ObservationRepository(conn)
        claims = ClaimRepository(conn)
        return [await serialize_source(s, observations, claims) for s in sources]


@router.get("/sources/{source_id}")
async def get_source(
    source_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        source = await SourceRepository(conn).get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="not found")
        return await serialize_source(source, ObservationRepository(conn), ClaimRepository(conn))


@router.post("/sources/{source_id}/extract-claims", status_code=202)
async def extract_source_claims(
    source_id: str,
    force: bool = False,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        source = await SourceRepository(conn).get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="not found")
        if source.import_status != "VERIFIED":
            raise HTTPException(status_code=409, detail="source is not verified")
        if await JobRepository(conn).find_active_job_for_source("extract_claims", source_id):
            raise HTTPException(
                status_code=409, detail="claim extraction already in progress for this source"
            )
        jobs = await plan_claim_extraction_jobs(conn, source_id, user_id, force=force)
    dispatch_claim_extraction_jobs(jobs, source_id, user_id, force)
    return {"job_ids": [str(job_id) for job_id, _ in jobs], "status": "pending"}


@router.post("/sources/{source_id}/purge")
async def purge_source(
    source_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        source = await SourceRepository(conn).get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="not found")
        if await ClaimRepository(conn).count_for_source(source_id) > 0:
            raise HTTPException(
                status_code=409, detail="source has claims — cannot delete after extraction"
            )
        if source.raw_storage_path:
            delete_raw(source.raw_storage_path)
        await SourceRepository(conn).purge(source_id)
    return {"status": "purged"}
