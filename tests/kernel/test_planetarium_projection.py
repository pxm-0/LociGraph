from __future__ import annotations

from uuid import uuid4

from kernel.planetarium_projection import (
    MIN_CONCEPTS_FOR_UMAP,
    UMAP_FALLBACK_JITTER,
    project_concepts,
)


def _embedding(seed: float) -> list[float]:
    return [seed, seed * 2, seed * 3, seed * 4]


def test_project_concepts_empty_returns_empty():
    assert project_concepts({}) == {}


def test_project_concepts_below_minimum_uses_jittered_origin():
    ids = [uuid4() for _ in range(MIN_CONCEPTS_FOR_UMAP - 1)]
    embeddings = {cid: _embedding(float(i)) for i, cid in enumerate(ids)}

    result = project_concepts(embeddings)

    assert set(result.keys()) == set(ids)
    for i, cid in enumerate(ids):
        assert result[cid] == (i * UMAP_FALLBACK_JITTER, 0.0, 0.0)


def test_project_concepts_runs_umap_above_minimum_and_is_deterministic():
    ids = [uuid4() for _ in range(10)]
    embeddings = {cid: _embedding(float(i)) for i, cid in enumerate(ids)}

    first = project_concepts(embeddings)
    second = project_concepts(embeddings)

    assert set(first.keys()) == set(ids)
    for cid in ids:
        assert first[cid] == second[cid]
        assert len(first[cid]) == 3
