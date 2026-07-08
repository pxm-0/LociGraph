import uuid
from datetime import UTC, datetime

from kernel.models import Claim, ConceptCandidate, Observation, Source


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


def test_claim_and_concept_candidate_from_row():
    now = datetime.now(UTC)
    claim = Claim.from_row(
        {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "source_id": uuid.uuid4(),
            "observation_id": uuid.uuid4(),
            "claim_text": "Alpha matters.",
            "claim_type": "belief",
            "assertion_type": "interpretation",
            "confidence": 0.77,
            "extraction_method": "test",
            "model_name": "fake",
            "prompt_version": "v1",
            "status": "proposed",
            "created_at": now,
            "metadata": {},
        }
    )
    candidate = ConceptCandidate.from_row(
        {
            "id": uuid.uuid4(),
            "user_id": claim.user_id,
            "source_id": claim.source_id,
            "claim_id": claim.id,
            "candidate_name": "Alpha",
            "concept_type": "idea",
            "rationale": "named entity",
            "confidence": 0.66,
            "extraction_method": "test",
            "model_name": "fake",
            "prompt_version": "v1",
            "status": "proposed",
            "created_at": now,
            "metadata": {},
        }
    )
    assert claim.confidence == 0.77
    assert candidate.claim_id == claim.id
