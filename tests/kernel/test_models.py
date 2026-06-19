import uuid
from datetime import UTC, datetime

from kernel.models import Observation, Source


def test_source_from_row_maps_fields():
    row = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "source_type": "markdown",
        "original_filename": "notes.md",
        "checksum_sha256": "abc",
        "import_status": "PENDING",
    }
    source = Source.from_row(row)
    assert source.source_type == "markdown"
    assert source.import_status == "PENDING"
    assert source.original_filename == "notes.md"


def test_observation_is_immutable():
    obs = Observation.from_row(
        {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "content": "hello",
            "confidence": 1.0,
            "status": "active",
            "created_at": datetime.now(UTC),
        }
    )
    try:
        obs.content = "changed"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised, "frozen dataclass must reject mutation"
