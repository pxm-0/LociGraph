from __future__ import annotations

import math
from uuid import UUID

import numpy as np
import umap

UMAP_RANDOM_STATE = 42
UMAP_N_NEIGHBORS_DEFAULT = 15
MIN_CONCEPTS_FOR_UMAP = 3

# Target extent of the layout, in the same world units the scene camera and
# node radii use (node radii run 1-5, camera sits at z=30). UMAP output has an
# arbitrary scale, so we normalize it to fill this radius; sphere fallbacks use
# it directly. Tune here if planets look too sparse or too crowded.
SCENE_RADIUS = 12.0

PROJECTION_ALGORITHM = "umap"
PROJECTION_VERSION = "v2"

# Golden angle — the increment that spreads successive points evenly, avoiding
# the seams a naive lat/long grid produces.
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


def fibonacci_sphere(count: int, radius: float) -> list[tuple[float, float, float]]:
    """`count` points spread evenly over a sphere of `radius` via the golden-angle
    spiral. Deterministic, and no two points coincide, so it is the fallback
    whenever we have no meaningful embedding-based layout to place nodes with."""
    if count <= 0:
        return []
    if count == 1:
        return [(0.0, 0.0, radius)]
    points = []
    for i in range(count):
        y = 1.0 - 2.0 * i / (count - 1)  # walk y from +1 down to -1
        r_xy = math.sqrt(max(0.0, 1.0 - y * y))
        theta = _GOLDEN_ANGLE * i
        points.append(
            (radius * math.cos(theta) * r_xy, radius * y, radius * math.sin(theta) * r_xy)
        )
    return points


def project_concepts(
    embeddings: dict[UUID, list[float]],
) -> dict[UUID, tuple[float, float, float]]:
    """Maps each embeddable concept_id to (x, y, z) filling a sphere of
    SCENE_RADIUS. Runs UMAP when there are enough concepts and their embeddings
    actually differ; otherwise (too few, or embeddings that collapse to a point)
    falls back to an even spread on the sphere so nodes never pile up."""
    if not embeddings:
        return {}

    concept_ids = list(embeddings.keys())
    if len(embeddings) >= MIN_CONCEPTS_FOR_UMAP:
        matrix = np.array([embeddings[cid] for cid in concept_ids])
        n_neighbors = min(UMAP_N_NEIGHBORS_DEFAULT, len(concept_ids) - 1)
        reducer = umap.UMAP(
            n_components=3, random_state=UMAP_RANDOM_STATE, n_neighbors=n_neighbors
        )
        coords = reducer.fit_transform(matrix)
        centered = coords - coords.mean(axis=0)
        max_dist = float(np.max(np.linalg.norm(centered, axis=1)))
        if max_dist > 0:
            scaled = centered * (SCENE_RADIUS / max_dist)
            return {
                cid: (float(scaled[i][0]), float(scaled[i][1]), float(scaled[i][2]))
                for i, cid in enumerate(concept_ids)
            }
        # else: UMAP collapsed every point onto one spot (near-identical
        # embeddings) — fall through to an even sphere spread.

    return dict(
        zip(concept_ids, fibonacci_sphere(len(concept_ids), SCENE_RADIUS), strict=True)
    )
