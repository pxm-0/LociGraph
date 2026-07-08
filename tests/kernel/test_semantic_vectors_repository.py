import pytest

from kernel.db.claims import ClaimRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


def _pad_vector(v: list[float]) -> list[float]:
    """Pad a vector to 1536 dimensions for pgvector."""
    return v + [0.0] * (1536 - len(v))


async def _make_claim(conn, user_id, source_id, content="Alpha matters."):
    [obs_id] = await ObservationRepository(conn).bulk_insert(
        [{"content": content}], source_id, user_id
    )
    claim = await ClaimRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        observation_id=obs_id,
        claim_text=content,
        claim_type="fact",
        assertion_type="reality",
        confidence=0.9,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    assert claim is not None
    return claim


@pytest.mark.asyncio
async def test_create_and_get_for_claim_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "sv-repo-1")
        claim = await _make_claim(conn, user_id, source.id)
        repo = SemanticVectorRepository(conn)
        vector = _pad_vector([0.1, 0.2, 0.3])

        created = await repo.create(
            user_id=user_id, claim_id=claim.id, embedding=vector, model_name="test-model"
        )
        fetched = await repo.get_for_claim(claim.id)

    assert created is not None
    assert created.embedding == pytest.approx(vector)
    assert created.model_name == "test-model"
    assert fetched == created


@pytest.mark.asyncio
async def test_create_is_idempotent_for_same_claim(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "sv-repo-2")
        claim = await _make_claim(conn, user_id, source.id)
        repo = SemanticVectorRepository(conn)

        first = await repo.create(
            user_id=user_id,
            claim_id=claim.id,
            embedding=_pad_vector([0.1, 0.2]),
            model_name="test-model",
        )
        second = await repo.create(
            user_id=user_id,
            claim_id=claim.id,
            embedding=_pad_vector([0.9, 0.9]),
            model_name="test-model",
        )

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_claim_ids_without_vector_excludes_embedded_claims(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "sv-repo-3")
        embedded = await _make_claim(conn, user_id, source.id, "Embedded claim.")
        pending = await _make_claim(conn, user_id, source.id, "Pending claim.")
        repo = SemanticVectorRepository(conn)
        await repo.create(
            user_id=user_id,
            claim_id=embedded.id,
            embedding=_pad_vector([0.1]),
            model_name="test-model",
        )

        missing = await repo.claim_ids_without_vector(source.id)

    assert missing == {pending.id}


@pytest.mark.asyncio
async def test_search_similar_ranks_by_cosine_distance(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "sv-repo-4")
        close = await _make_claim(conn, user_id, source.id, "Close claim.")
        far = await _make_claim(conn, user_id, source.id, "Far claim.")
        repo = SemanticVectorRepository(conn)
        await repo.create(
            user_id=user_id,
            claim_id=close.id,
            embedding=_pad_vector([1.0, 0.0]),
            model_name="test-model",
        )
        await repo.create(
            user_id=user_id,
            claim_id=far.id,
            embedding=_pad_vector([0.0, 1.0]),
            model_name="test-model",
        )

        results = await repo.search_similar(_pad_vector([1.0, 0.0]), limit=2)

    assert [r.claim.id for r in results] == [close.id, far.id]
    assert results[0].similarity > results[1].similarity
    assert results[0].similarity == pytest.approx(1.0, abs=1e-6)
