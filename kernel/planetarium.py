from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import numpy as np
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.models import PlanetaryNode
from kernel.planetarium_physics import (
    MASS_FORMULA_VERSION,
    classify_visual_class,
    color_for_visual_class,
    compute_brightness,
    compute_mass,
    mass_percentiles,
    node_radius,
    normalize,
    spherical_from_cartesian,
)
from kernel.planetarium_projection import (
    PROJECTION_ALGORITHM,
    PROJECTION_VERSION,
    project_concepts,
)

# Generous cap on rows fetched per concept per related table — a personal
# archive's per-concept revision/edge/contradiction/pin counts are expected
# to stay far below this; it exists so the query has an explicit LIMIT
# rather than none, matching every other paginated repository method here.
MAX_ROWS_PER_CONCEPT = 10_000


async def rebuild_planetarium(conn: AsyncConnection, user_id: str | UUID) -> list[PlanetaryNode]:
    concepts = await ConceptRepository(conn).list(limit=MAX_ROWS_PER_CONCEPT)
    if not concepts:
        return await PlanetaryNodeRepository(conn).replace_all_for_user(user_id, [])

    revision_repo = RevisionRepository(conn)
    edge_repo = ClaimConceptEdgeRepository(conn)
    contradiction_repo = ContradictionRepository(conn)
    signal_repo = ImportanceSignalRepository(conn)
    vector_repo = SemanticVectorRepository(conn)

    revision_counts: dict[str, float] = {}
    edge_counts: dict[str, float] = {}
    contradiction_counts: dict[str, float] = {}
    pin_counts: dict[str, float] = {}
    days_since_activity: dict[str, float] = {}
    embeddings: dict[UUID, list[float]] = {}
    now = datetime.now(UTC)

    for concept in concepts:
        cid = str(concept.id)
        revisions = await revision_repo.list(concept_id=concept.id, limit=MAX_ROWS_PER_CONCEPT)
        concept_edges = await edge_repo.list_for_concept(concept.id)
        contradictions = await contradiction_repo.list(
            concept_id=concept.id, limit=MAX_ROWS_PER_CONCEPT
        )
        pins = await signal_repo.list_for_target("concept", concept.id)
        vectors = await vector_repo.list_for_concept(concept.id)

        revision_counts[cid] = float(len(revisions))
        edge_counts[cid] = float(len(concept_edges))
        contradiction_counts[cid] = float(len(contradictions))
        pin_counts[cid] = float(len(pins))
        if vectors:
            embeddings[concept.id] = list(np.mean([v.embedding for v in vectors], axis=0))

        timestamps = (
            [concept.created_at]
            + [r.created_at for r in revisions]
            + [e.created_at for e in concept_edges]
            + [c.created_at for c in contradictions]
            + [p.created_at for p in pins]
            + [v.created_at for v in vectors]
        )
        days_since_activity[cid] = (now - max(timestamps)).total_seconds() / 86400.0

    normalized_revision = normalize(revision_counts)
    normalized_edge = normalize(edge_counts)
    normalized_contradiction = normalize(contradiction_counts)
    normalized_pin = normalize(pin_counts)

    masses = {
        cid: compute_mass(
            normalized_revision=normalized_revision[cid],
            normalized_edge=normalized_edge[cid],
            normalized_contradiction=normalized_contradiction[cid],
            normalized_pin=normalized_pin[cid],
        )
        for cid in revision_counts
    }
    normalized_mass = normalize(masses)
    percentiles = mass_percentiles(masses)
    positions = project_concepts(embeddings)

    nodes = []
    for concept in concepts:
        cid = str(concept.id)
        x, y, z = positions.get(concept.id, (0.0, 0.0, 0.0))
        theta, phi = spherical_from_cartesian(x, y, z)
        visual_class = classify_visual_class(
            mass=masses[cid], mass_percentile=percentiles[cid], concept_count=len(concepts)
        )
        nodes.append(
            {
                "concept_id": concept.id,
                "x": x,
                "y": y,
                "z": z,
                "theta": theta,
                "phi": phi,
                "radius": node_radius(normalized_mass[cid]),
                "mass": masses[cid],
                "brightness": compute_brightness(days_since_activity[cid]),
                "color": color_for_visual_class(visual_class),
                "visual_class": visual_class,
                "projection_version": f"{MASS_FORMULA_VERSION}/{PROJECTION_VERSION}",
                "projection_algorithm": PROJECTION_ALGORITHM,
            }
        )
    return await PlanetaryNodeRepository(conn).replace_all_for_user(user_id, nodes)
