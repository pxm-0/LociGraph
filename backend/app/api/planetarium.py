from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.dependencies import get_current_user
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.jobs import JobRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.models import Concept, PlanetaryNode
from worker.tasks.project_planetarium import project_planetarium

router = APIRouter()


def _serialize(node: PlanetaryNode, concept: Concept | None) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "concept_id": str(node.concept_id),
        "concept_name": concept.concept_name if concept else "Unknown",
        "concept_type": concept.concept_type if concept else "unknown",
        "x": node.x,
        "y": node.y,
        "z": node.z,
        "theta": node.theta,
        "phi": node.phi,
        "radius": node.radius,
        "mass": node.mass,
        "brightness": node.brightness,
        "color": node.color,
        "visual_class": node.visual_class,
        "projection_version": node.projection_version,
        "projection_algorithm": node.projection_algorithm,
        "created_at": node.created_at.isoformat() if node.created_at else None,
    }


@router.post("/planetarium/rebuild", status_code=202)
async def rebuild_planetarium_endpoint(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        job = await JobRepository(conn).create(user_id, "project_planetarium")
    project_planetarium.send(user_id, str(job.id))
    return {"job_id": str(job.id), "status": "pending"}


@router.get("/planetarium/nodes")
async def list_planetary_nodes(
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        nodes = await PlanetaryNodeRepository(conn).list_for_user(user_id)
        concepts_by_id = {c.id: c for c in await ConceptRepository(conn).list(limit=10_000)}
    return [_serialize(node, concepts_by_id.get(node.concept_id)) for node in nodes]


@router.get("/planetarium/nodes/{concept_id}/detail")
async def get_planetary_node_detail(
    concept_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).get(concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail="concept not found")
        node = await PlanetaryNodeRepository(conn).get_for_concept(user_id, concept_id)
        if node is None:
            raise HTTPException(
                status_code=404, detail="no planetarium data for this concept yet"
            )
        revisions = await RevisionRepository(conn).list(concept_id=concept_id, limit=10_000)
        edges = await ClaimConceptEdgeRepository(conn).list_for_concept(concept_id)
        contradictions = await ContradictionRepository(conn).list(
            concept_id=concept_id, limit=10_000
        )
        pins = await ImportanceSignalRepository(conn).list_for_target(
            "concept", concept_id, limit=10_000
        )
        vectors = await SemanticVectorRepository(conn).list_for_concept(concept_id)

    return {
        "concept_id": str(concept.id),
        "concept_name": concept.concept_name,
        "concept_type": concept.concept_type,
        "description": concept.description,
        "mass": node.mass,
        "brightness": node.brightness,
        "visual_class": node.visual_class,
        "revision_count": len(revisions),
        "edge_count": len(edges),
        "contradiction_count": len(contradictions),
        "pin_count": len(pins),
        "is_embedded": len(vectors) > 0,
    }
