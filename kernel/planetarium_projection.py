from __future__ import annotations

from uuid import UUID

import numpy as np
import umap

UMAP_RANDOM_STATE = 42
UMAP_N_NEIGHBORS_DEFAULT = 15
MIN_CONCEPTS_FOR_UMAP = 3
UMAP_FALLBACK_JITTER = 0.1

PROJECTION_ALGORITHM = "umap"
PROJECTION_VERSION = "v1"


def project_concepts(
    embeddings: dict[UUID, list[float]],
) -> dict[UUID, tuple[float, float, float]]:
    """Maps each concept_id to (x, y, z). Below MIN_CONCEPTS_FOR_UMAP total
    embeddable concepts, UMAP has too few neighbors to run meaningfully —
    each concept is placed near the origin with a small deterministic jitter
    (by insertion order) so they don't exactly overlap."""
    if len(embeddings) < MIN_CONCEPTS_FOR_UMAP:
        return {
            concept_id: (index * UMAP_FALLBACK_JITTER, 0.0, 0.0)
            for index, concept_id in enumerate(embeddings)
        }

    concept_ids = list(embeddings.keys())
    matrix = np.array([embeddings[cid] for cid in concept_ids])
    n_neighbors = min(UMAP_N_NEIGHBORS_DEFAULT, len(concept_ids) - 1)
    reducer = umap.UMAP(
        n_components=3, random_state=UMAP_RANDOM_STATE, n_neighbors=n_neighbors
    )
    coords = reducer.fit_transform(matrix)
    return {
        concept_id: (float(coords[i][0]), float(coords[i][1]), float(coords[i][2]))
        for i, concept_id in enumerate(concept_ids)
    }
