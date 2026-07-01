from __future__ import annotations

from worker.tasks.extract_claims import extract_claims
from worker.tasks.ingest_source import ingest_source


def submit_ingest(source_id: str, user_id: str, job_id: str) -> None:
    ingest_source.send(source_id, user_id, job_id)


def submit_claim_extraction(
    source_id: str, user_id: str, job_id: str, *, force: bool = False
) -> None:
    extract_claims.send(source_id, user_id, job_id, force)
