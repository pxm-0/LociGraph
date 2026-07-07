"""Worker entrypoint: `dramatiq worker.main`. Imports tasks so actors register."""
from worker.broker import get_broker

get_broker()

from worker.tasks import embed_claims, extract_claims, ingest_source  # noqa: E402,F401
