from __future__ import annotations

from worker.tasks.ingest_source import ingest_source


def submit_ingest(source_id: str, user_id: str, job_id: str) -> None:
    ingest_source.send(source_id, user_id, job_id)
