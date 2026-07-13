from __future__ import annotations

import math
from uuid import uuid4

from kernel.planetarium_projection import (
    MIN_CONCEPTS_FOR_UMAP,
    SCENE_RADIUS,
    SCENE_RADIUS_FLOOR,
    fibonacci_sphere,
    project_concepts,
    scene_radius_for,
)


def _embedding(seed: float) -> list[float]:
    return [seed, seed * 2, seed * 3, seed * 4]


def _norm(point: tuple[float, float, float]) -> float:
    return math.sqrt(sum(c * c for c in point))


def test_fibonacci_sphere_places_points_on_the_requested_radius():
    points = fibonacci_sphere(20, SCENE_RADIUS)

    assert len(points) == 20
    for point in points:
        assert abs(_norm(point) - SCENE_RADIUS) < 1e-6
    assert len(set(points)) == 20  # all distinct — no two concepts coincide


def test_fibonacci_sphere_single_point():
    assert fibonacci_sphere(1, SCENE_RADIUS) == [(0.0, 0.0, SCENE_RADIUS)]


def test_scene_radius_grows_with_count_and_has_a_floor():
    assert scene_radius_for(0) == SCENE_RADIUS_FLOOR
    assert scene_radius_for(1) == SCENE_RADIUS_FLOOR
    # sqrt scaling past the floor: 4x the count -> 2x the radius
    big, bigger = scene_radius_for(100), scene_radius_for(400)
    assert bigger > big
    assert abs(bigger - 2 * big) < 1e-6


def test_project_concepts_empty_returns_empty():
    assert project_concepts({}) == {}


def test_project_concepts_below_minimum_spreads_on_a_sphere():
    ids = [uuid4() for _ in range(MIN_CONCEPTS_FOR_UMAP - 1)]
    embeddings = {cid: _embedding(float(i)) for i, cid in enumerate(ids)}

    result = project_concepts(embeddings)

    assert set(result.keys()) == set(ids)
    positions = list(result.values())
    for position in positions:
        assert abs(_norm(position) - SCENE_RADIUS) < 1e-6
    assert len(set(positions)) == len(ids)  # not piled at the origin


def test_project_concepts_runs_umap_above_minimum_scaled_and_deterministic():
    ids = [uuid4() for _ in range(10)]
    embeddings = {cid: _embedding(float(i)) for i, cid in enumerate(ids)}

    first = project_concepts(embeddings)
    second = project_concepts(embeddings)

    assert set(first.keys()) == set(ids)
    for cid in ids:
        assert first[cid] == second[cid]
        assert len(first[cid]) == 3
    # UMAP output is scaled to fill the scene: the farthest point sits on the
    # scene radius, so nodes are never all crammed into a sub-unit blob.
    assert abs(max(_norm(p) for p in first.values()) - SCENE_RADIUS) < 1e-6


def test_project_concepts_never_piles_up_identical_embeddings():
    # Identical embeddings give UMAP nothing meaningful to separate; the
    # invariant that matters is that every concept still gets a distinct,
    # in-scene position instead of collapsing onto one spot.
    ids = [uuid4() for _ in range(10)]
    embeddings = {cid: _embedding(1.0) for cid in ids}

    result = project_concepts(embeddings)

    positions = list(result.values())
    assert set(result.keys()) == set(ids)
    assert len(set(positions)) == len(ids)
    for position in positions:
        assert _norm(position) <= SCENE_RADIUS + 1e-6
