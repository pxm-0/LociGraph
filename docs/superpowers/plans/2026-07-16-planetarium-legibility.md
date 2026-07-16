# Planetarium Legibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Planetarium legible — a legend explaining what position/size/color/glow encode, a hover label showing a node's name, and a click-opened in-place panel explaining why a specific node looks the way it does.

**Architecture:** Backend adds one new repo method (`get_for_concept`), enriches the existing bulk list endpoint with concept identity, and adds one new lazy per-click detail endpoint. Frontend adds two new components (`PlanetariumLegend`, `ConceptDetailPanel`), a pure `describeNode()` formatter, and rewires `PlanetNode`'s click from "navigate away" to "notify parent to open panel," plus a hover label.

**Tech Stack:** Python/FastAPI/SQLAlchemy (async, raw `text()` queries) backend; Next.js/React/`@react-three/fiber`+`@react-three/drei` frontend; pytest (real Postgres test DB, no mocking) and Vitest+RTL (mocked `api.ts`) for tests.

## Global Constraints

- Every backend test hits the real test Postgres DB via the `session`/`client`/`seeded_user`/`make_user` fixtures already in `tests/conftest.py` and `tests/backend/conftest.py` — no mocking the DB layer, matching every existing test in this repo.
- Every frontend component test mocks `@/lib/api` via `vi.mock`, matching `RebuildButton.test.tsx`'s convention — never renders a real `<Canvas>` (no WebGL in jsdom).
- Tailwind classes for any new panel/legend UI must reuse the existing tokens already used by `CustodianPanel.tsx`/`planetarium/page.tsx`: `bg-surface`, `border-hairline`, `rounded-hearth`, `text-ink`, `text-muted`, `font-heading`, `font-ui`, `shadow-lg`.
- Run backend tests with these env vars exported (already the case in this repo's dev setup): `MIGRATION_DATABASE_URL`, `DATABASE_URL`, `APP_DB_PASSWORD`, `LOCIGRAPH_EMAIL`, `LOCIGRAPH_PASSWORD`, `JWT_SECRET`, `RAW_STORAGE_PATH`.
- After each backend task: `.venv/bin/ruff check <files>` and `.venv/bin/mypy <files>` must be clean before committing.
- Commit after every task (see Task Structure below) — do not batch multiple tasks into one commit.

---

### Task 1: `PlanetaryNodeRepository.get_for_concept`

**Files:**
- Modify: `kernel/db/planetary_nodes.py`
- Test: `tests/kernel/test_planetary_nodes_repository.py`

**Interfaces:**
- Produces: `PlanetaryNodeRepository.get_for_concept(self, user_id: str | UUID, concept_id: str | UUID) -> PlanetaryNode | None` — used by Task 3's detail endpoint.

- [ ] **Step 1: Write the failing test**

Append to `tests/kernel/test_planetary_nodes_repository.py`:

```python
@pytest.mark.asyncio
async def test_get_for_concept_returns_none_when_no_node_exists(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Gamma", concept_type="entity"
        )
        assert concept is not None
        node = await PlanetaryNodeRepository(conn).get_for_concept(user_id, concept.id)
    assert node is None


@pytest.mark.asyncio
async def test_get_for_concept_returns_the_matching_node(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Delta", concept_type="entity"
        )
        assert concept is not None
        repo = PlanetaryNodeRepository(conn)
        await repo.replace_all_for_user(user_id, [_node(concept.id, mass=0.42)])

        node = await repo.get_for_concept(user_id, concept.id)

    assert node is not None
    assert node.concept_id == concept.id
    assert node.mass == 0.42
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest -q tests/kernel/test_planetary_nodes_repository.py -k get_for_concept`
Expected: FAIL — `AttributeError: 'PlanetaryNodeRepository' object has no attribute 'get_for_concept'`

- [ ] **Step 3: Implement `get_for_concept`**

In `kernel/db/planetary_nodes.py`, add this method to `PlanetaryNodeRepository` (after `replace_all_for_user`, before `list_for_user`):

```python
    async def get_for_concept(
        self, user_id: str | UUID, concept_id: str | UUID
    ) -> PlanetaryNode | None:
        row = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM planetary_nodes "
                    "WHERE user_id = :user_id AND concept_id = :concept_id"
                ),
                {"user_id": str(user_id), "concept_id": str(concept_id)},
            )
        ).mappings().first()
        return PlanetaryNode.from_row(_as_mapping(row)) if row else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest -q tests/kernel/test_planetary_nodes_repository.py`
Expected: PASS (4 passed — the 2 existing + 2 new)

- [ ] **Step 5: Lint and type-check**

Run: `.venv/bin/ruff check kernel/db/planetary_nodes.py && .venv/bin/mypy kernel/db/planetary_nodes.py`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add kernel/db/planetary_nodes.py tests/kernel/test_planetary_nodes_repository.py
git commit -m "feat: add PlanetaryNodeRepository.get_for_concept"
```

---

### Task 2: Enrich `GET /planetarium/nodes` with concept identity

**Files:**
- Modify: `backend/app/api/planetarium.py`
- Test: `tests/backend/test_planetarium_api.py`

**Interfaces:**
- Consumes: `ConceptRepository(conn).list(limit=...)` (existing, `kernel/db/concepts.py`), `Concept.concept_name`/`Concept.concept_type` (existing, `kernel/models.py`).
- Produces: `GET /planetarium/nodes` response items gain `"concept_name": str` and `"concept_type": str` keys (falling back to `"Unknown"`/`"unknown"` if the concept was deleted after the last rebuild).

- [ ] **Step 1: Write the failing test**

Append to `tests/backend/test_planetarium_api.py`:

```python
@pytest.mark.asyncio
async def test_list_nodes_includes_concept_name_and_type(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Epsilon", concept_type="entity"
        )
        assert concept is not None
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            seeded_user, [_node(concept.id)]
        )

    await _login(client)
    r = await client.get("/planetarium/nodes")

    assert r.status_code == 200
    body = r.json()
    assert body[0]["concept_name"] == "Epsilon"
    assert body[0]["concept_type"] == "entity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/backend/test_planetarium_api.py -k concept_name_and_type`
Expected: FAIL — `KeyError: 'concept_name'`

- [ ] **Step 3: Implement the enrichment**

In `backend/app/api/planetarium.py`, add the import and update `_serialize` and `list_planetary_nodes`:

```python
from kernel.db.concepts import ConceptRepository
from kernel.models import Concept, PlanetaryNode
```

Replace `_serialize` and `list_planetary_nodes` with:

```python
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


@router.get("/planetarium/nodes")
async def list_planetary_nodes(
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        nodes = await PlanetaryNodeRepository(conn).list_for_user(user_id)
        concepts_by_id = {c.id: c for c in await ConceptRepository(conn).list(limit=10_000)}
    return [_serialize(node, concepts_by_id.get(node.concept_id)) for node in nodes]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest -q tests/backend/test_planetarium_api.py`
Expected: PASS (all tests in the file, including the pre-existing `test_list_nodes_returns_serialized_nodes`)

- [ ] **Step 5: Lint and type-check**

Run: `.venv/bin/ruff check backend/app/api/planetarium.py && .venv/bin/mypy backend/app/api/planetarium.py`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/planetarium.py tests/backend/test_planetarium_api.py
git commit -m "feat: include concept name/type in planetarium node list"
```

---

### Task 3: `GET /planetarium/nodes/{concept_id}/detail`

**Files:**
- Modify: `backend/app/api/planetarium.py`
- Test: `tests/backend/test_planetarium_api.py`

**Interfaces:**
- Consumes: `PlanetaryNodeRepository.get_for_concept` (Task 1), `ConceptRepository.get`, `RevisionRepository.list`, `ClaimConceptEdgeRepository.list_for_concept`, `ContradictionRepository.list`, `ImportanceSignalRepository.list_for_target`, `SemanticVectorRepository.list_for_concept` (all pre-existing).
- Produces: `GET /planetarium/nodes/{concept_id}/detail` → `200` with the JSON shape below, `404` if the concept doesn't exist or has no planetarium data yet.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backend/test_planetarium_api.py`:

```python
@pytest.mark.asyncio
async def test_node_detail_returns_breakdown_for_embedded_concept(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
    from kernel.db.claims import ClaimRepository
    from kernel.db.concept_candidates import ConceptCandidateRepository
    from kernel.db.concepts import ConceptRepository
    from kernel.db.observations import ObservationRepository
    from kernel.db.semantic_vectors import SemanticVectorRepository
    from kernel.db.sources import SourceRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Zeta", concept_type="entity"
        )
        assert concept is not None
        source = await SourceRepository(conn).create(seeded_user, "json", "detail-test")
        await SourceRepository(conn).mark_verified(source.id)
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Zeta matters."}], source.id, seeded_user
        )
        claim = await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Zeta matters.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Zeta",
            concept_type="entity",
            rationale=None,
            confidence=0.9,
            extraction_method="test",
            model_name=None,
            prompt_version=None,
        )
        await ClaimConceptEdgeRepository(conn).create(
            user_id=seeded_user,
            claim_id=claim.id,
            concept_id=concept.id,
            concept_candidate_id=candidate.id,
            confidence=0.9,
        )
        await SemanticVectorRepository(conn).create(
            user_id=seeded_user,
            claim_id=claim.id,
            embedding=[0.1] * 1536,
            model_name="fake",
        )
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            seeded_user, [_node(concept.id, visual_class="black_hole", mass=0.9)]
        )

    await _login(client)
    r = await client.get(f"/planetarium/nodes/{concept.id}/detail")

    assert r.status_code == 200
    body = r.json()
    assert body["concept_name"] == "Zeta"
    assert body["visual_class"] == "black_hole"
    assert body["edge_count"] == 1
    assert body["revision_count"] == 0
    assert body["contradiction_count"] == 0
    assert body["pin_count"] == 0
    assert body["is_embedded"] is True


@pytest.mark.asyncio
async def test_node_detail_flags_non_embedded_concept(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Eta", concept_type="entity"
        )
        assert concept is not None
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            seeded_user, [_node(concept.id)]
        )

    await _login(client)
    r = await client.get(f"/planetarium/nodes/{concept.id}/detail")

    assert r.status_code == 200
    assert r.json()["is_embedded"] is False


@pytest.mark.asyncio
async def test_node_detail_404s_for_unknown_concept(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/planetarium/nodes/00000000-0000-0000-0000-000000000000/detail")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_node_detail_404s_when_concept_has_no_planetarium_data(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Theta", concept_type="entity"
        )
        assert concept is not None

    await _login(client)
    r = await client.get(f"/planetarium/nodes/{concept.id}/detail")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest -q tests/backend/test_planetarium_api.py -k node_detail`
Expected: FAIL — `404 Not Found` from FastAPI's default (route doesn't exist) for all four

- [ ] **Step 3: Implement the endpoint**

In `backend/app/api/planetarium.py`, add these imports:

```python
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
```

And add this route at the end of the file:

```python
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
```

Also add `HTTPException` to the existing `from fastapi import ...` line if not already imported (check first — `backend/app/api/concepts.py` already imports it the same way, this file currently only imports `APIRouter, Depends`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest -q tests/backend/test_planetarium_api.py`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Lint and type-check**

Run: `.venv/bin/ruff check backend/app/api/planetarium.py && .venv/bin/mypy backend/app/api/planetarium.py`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/planetarium.py tests/backend/test_planetarium_api.py
git commit -m "feat: add planetarium node detail endpoint"
```

---

### Task 4: Frontend types + API client additions

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/lib/api.test.ts`

**Interfaces:**
- Produces: `PlanetariumNode` gains `conceptName: string`, `conceptType: string`. New `PlanetariumNodeDetail` interface. New `getPlanetariumNodeDetail(conceptId: string): Promise<PlanetariumNodeDetail>`. Consumed by Tasks 5–9.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/lib/api.test.ts`, update the existing `listPlanetariumNodes` test's mock input/expected output to include the new fields, and add a new test. Replace the existing test:

```typescript
test("listPlanetariumNodes maps snake_case fields to camelCase", async () => {
  const f = mockFetch(200, [
    {
      id: "n1",
      concept_id: "c1",
      concept_name: "Alpha",
      concept_type: "entity",
      x: 1,
      y: 2,
      z: 3,
      theta: 0.1,
      phi: 0.2,
      radius: 2,
      mass: 0.5,
      brightness: 0.9,
      color: "#4a90d9",
      visual_class: "planet",
      projection_version: "v1/v1",
      projection_algorithm: "umap",
      created_at: "2024-01-01T00:00:00Z",
    },
  ])
  vi.stubGlobal("fetch", f)
  const result = await listPlanetariumNodes()
  expect(result).toEqual([
    {
      id: "n1",
      conceptId: "c1",
      conceptName: "Alpha",
      conceptType: "entity",
      x: 1,
      y: 2,
      z: 3,
      theta: 0.1,
      phi: 0.2,
      radius: 2,
      mass: 0.5,
      brightness: 0.9,
      color: "#4a90d9",
      visualClass: "planet",
      projectionVersion: "v1/v1",
      projectionAlgorithm: "umap",
      createdAt: "2024-01-01T00:00:00Z",
    },
  ])
  expect(f.mock.calls[0][0]).toBe("/api/planetarium/nodes")
})

test("getPlanetariumNodeDetail maps snake_case fields to camelCase", async () => {
  const f = mockFetch(200, {
    concept_id: "c1",
    concept_name: "Alpha",
    concept_type: "entity",
    description: "A concept.",
    mass: 0.7,
    brightness: 0.8,
    visual_class: "black_hole",
    revision_count: 4,
    edge_count: 7,
    contradiction_count: 1,
    pin_count: 2,
    is_embedded: true,
  })
  vi.stubGlobal("fetch", f)
  const result = await getPlanetariumNodeDetail("c1")
  expect(result).toEqual({
    conceptId: "c1",
    conceptName: "Alpha",
    conceptType: "entity",
    description: "A concept.",
    mass: 0.7,
    brightness: 0.8,
    visualClass: "black_hole",
    revisionCount: 4,
    edgeCount: 7,
    contradictionCount: 1,
    pinCount: 2,
    isEmbedded: true,
  })
  expect(f.mock.calls[0][0]).toBe("/api/planetarium/nodes/c1/detail")
})
```

Add `getPlanetariumNodeDetail` to the existing import block at the top of the file (alongside `listPlanetariumNodes`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: FAIL — `listPlanetariumNodes` test fails on the new fields (undefined `conceptName`/`conceptType`); `getPlanetariumNodeDetail` fails as not exported

- [ ] **Step 3: Implement the type and API client changes**

In `frontend/src/lib/types.ts`, update `PlanetariumNode` and add `PlanetariumNodeDetail`:

```typescript
export interface PlanetariumNode {
  id: string
  conceptId: string
  conceptName: string
  conceptType: string
  x: number
  y: number
  z: number
  theta: number
  phi: number
  radius: number
  mass: number
  brightness: number
  color: string
  visualClass: string
  projectionVersion: string
  projectionAlgorithm: string
  createdAt: string | null
}

export interface PlanetariumNodeDetail {
  conceptId: string
  conceptName: string
  conceptType: string
  description: string | null
  mass: number
  brightness: number
  visualClass: string
  revisionCount: number
  edgeCount: number
  contradictionCount: number
  pinCount: number
  isEmbedded: boolean
}
```

In `frontend/src/lib/api.ts`, update `toPlanetariumNode` and add a new converter + function:

```typescript
function toPlanetariumNode(d: Record<string, unknown>): PlanetariumNode {
  return {
    id: String(d.id),
    conceptId: String(d.concept_id),
    conceptName: String(d.concept_name),
    conceptType: String(d.concept_type),
    x: Number(d.x),
    y: Number(d.y),
    z: Number(d.z),
    theta: Number(d.theta),
    phi: Number(d.phi),
    radius: Number(d.radius),
    mass: Number(d.mass),
    brightness: Number(d.brightness),
    color: String(d.color),
    visualClass: String(d.visual_class),
    projectionVersion: String(d.projection_version),
    projectionAlgorithm: String(d.projection_algorithm),
    createdAt: (d.created_at as string | null) ?? null,
  }
}

function toPlanetariumNodeDetail(d: Record<string, unknown>): PlanetariumNodeDetail {
  return {
    conceptId: String(d.concept_id),
    conceptName: String(d.concept_name),
    conceptType: String(d.concept_type),
    description: (d.description as string | null) ?? null,
    mass: Number(d.mass),
    brightness: Number(d.brightness),
    visualClass: String(d.visual_class),
    revisionCount: Number(d.revision_count),
    edgeCount: Number(d.edge_count),
    contradictionCount: Number(d.contradiction_count),
    pinCount: Number(d.pin_count),
    isEmbedded: Boolean(d.is_embedded),
  }
}

export async function getPlanetariumNodeDetail(conceptId: string): Promise<PlanetariumNodeDetail> {
  const r = await req(`/planetarium/nodes/${conceptId}/detail`)
  if (!r.ok) throw await readError(r, "getPlanetariumNodeDetail failed")
  return toPlanetariumNodeDetail(await r.json())
}
```

Add `PlanetariumNodeDetail` to the existing `import type { ... } from "./types"` block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: PASS

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/lib/api.test.ts
git commit -m "feat: add concept identity and node detail to planetarium API client"
```

---

### Task 5: `describeNode()` plain-language formatter

**Files:**
- Create: `frontend/src/components/planetarium/describeNode.ts`
- Test: `frontend/src/components/planetarium/describeNode.test.ts`

**Interfaces:**
- Consumes: `PlanetariumNodeDetail` (Task 4).
- Produces: `describeNode(detail: PlanetariumNodeDetail): string` — used by Task 7's `ConceptDetailPanel`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/planetarium/describeNode.test.ts`:

```typescript
import { expect, test } from "vitest"
import type { PlanetariumNodeDetail } from "@/lib/types"
import { describeNode } from "./describeNode"

function detail(overrides: Partial<PlanetariumNodeDetail> = {}): PlanetariumNodeDetail {
  return {
    conceptId: "c1",
    conceptName: "Alpha",
    conceptType: "entity",
    description: null,
    mass: 0.5,
    brightness: 0.5,
    visualClass: "planet",
    revisionCount: 0,
    edgeCount: 0,
    contradictionCount: 0,
    pinCount: 0,
    isEmbedded: true,
    ...overrides,
  }
}

test("describes a large, glowing black hole", () => {
  const text = describeNode(detail({ visualClass: "black_hole", mass: 0.9, brightness: 0.9 }))
  expect(text).toContain("black hole")
  expect(text).toContain("large")
  expect(text).toContain("glowing")
})

test("describes a small, dim planet", () => {
  const text = describeNode(detail({ visualClass: "planet", mass: 0.1, brightness: 0.05 }))
  expect(text).toContain("planet")
  expect(text).toContain("small")
  expect(text).toContain("dim")
})

test("describes a mid-size, moderately active planet", () => {
  const text = describeNode(detail({ visualClass: "planet", mass: 0.5, brightness: 0.5 }))
  expect(text).toContain("planet")
  expect(text).toContain("medium")
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/planetarium/describeNode.test.ts`
Expected: FAIL — module `./describeNode` does not exist

- [ ] **Step 3: Implement `describeNode`**

Create `frontend/src/components/planetarium/describeNode.ts`:

```typescript
import type { PlanetariumNodeDetail } from "@/lib/types"

function sizeAdjective(mass: number): string {
  if (mass >= 0.66) return "large"
  if (mass >= 0.33) return "medium"
  return "small"
}

function brightnessAdjective(brightness: number): string {
  if (brightness >= 0.66) return "glowing"
  if (brightness >= 0.2) return "dimly lit"
  return "dim"
}

export function describeNode(detail: PlanetariumNodeDetail): string {
  const kind = detail.visualClass === "black_hole" ? "black hole" : "planet"
  const size = sizeAdjective(detail.mass)
  const glow = brightnessAdjective(detail.brightness)
  const activity =
    detail.revisionCount + detail.edgeCount + detail.contradictionCount + detail.pinCount > 0
      ? "well connected"
      : "not yet connected to much"
  return `A ${size}, ${glow} ${kind} — ${activity}.`
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/planetarium/describeNode.test.ts`
Expected: PASS

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/planetarium/describeNode.ts frontend/src/components/planetarium/describeNode.test.ts
git commit -m "feat: add describeNode plain-language planetarium summary"
```

---

### Task 6: `PlanetariumLegend` component

**Files:**
- Create: `frontend/src/components/planetarium/PlanetariumLegend.tsx`
- Test: `frontend/src/components/planetarium/PlanetariumLegend.test.tsx`

**Interfaces:**
- Produces: `PlanetariumLegend()` (no props — self-contained open/dismiss state) — used by Task 9's `page.tsx`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/planetarium/PlanetariumLegend.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, test } from "vitest"
import { PlanetariumLegend } from "./PlanetariumLegend"

test("shows the legend by default and can be dismissed and reopened", async () => {
  render(<PlanetariumLegend />)

  expect(screen.getByText(/semantically similar/i)).toBeInTheDocument()
  expect(screen.getByText(/activity/i)).toBeInTheDocument()

  await userEvent.click(screen.getByRole("button", { name: /close legend/i }))
  expect(screen.queryByText(/semantically similar/i)).not.toBeInTheDocument()

  await userEvent.click(screen.getByRole("button", { name: /show legend/i }))
  expect(screen.getByText(/semantically similar/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/planetarium/PlanetariumLegend.test.tsx`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement `PlanetariumLegend`**

Create `frontend/src/components/planetarium/PlanetariumLegend.tsx`:

```tsx
"use client"

import { useState } from "react"

export function PlanetariumLegend() {
  const [open, setOpen] = useState(true)

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Show legend"
        className="rounded-hearth border border-hairline bg-surface px-3 py-1.5 text-xs font-ui text-muted hover:text-ink"
      >
        Legend
      </button>
    )
  }

  return (
    <div className="w-72 rounded-hearth border border-hairline bg-surface p-4 text-xs text-muted shadow-lg">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-heading text-sm text-ink">Reading the map</span>
        <button
          onClick={() => setOpen(false)}
          aria-label="Close legend"
          className="font-ui text-muted hover:text-ink"
        >
          Close
        </button>
      </div>
      <ul className="space-y-2">
        <li>
          <strong className="text-ink">Position</strong> — clustered concepts are
          semantically similar (based on content). Some nodes have no content
          yet and are spread out arbitrarily just to avoid overlap — not
          semantically positioned.
        </li>
        <li>
          <strong className="text-ink">Size</strong> — bigger means more
          activity: revisions, links to other concepts, contradictions, and
          pins.
        </li>
        <li>
          <strong className="text-ink">Color</strong> — dark "black hole" nodes
          are the top 10% most active/connected concepts.
        </li>
        <li>
          <strong className="text-ink">Glow</strong> — brighter means touched
          more recently; it fades over about a month.
        </li>
      </ul>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/planetarium/PlanetariumLegend.test.tsx`
Expected: PASS

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/planetarium/PlanetariumLegend.tsx frontend/src/components/planetarium/PlanetariumLegend.test.tsx
git commit -m "feat: add PlanetariumLegend explaining the map's encoding"
```

---

### Task 7: `ConceptDetailPanel` component

**Files:**
- Create: `frontend/src/components/planetarium/ConceptDetailPanel.tsx`
- Create: `frontend/src/components/planetarium/ConceptDetailPanel.test.tsx`
- Modify: `frontend/src/components/planetarium/PlanetNode.tsx` (remove `buildConceptHref` — it moves here)
- Modify: `frontend/src/components/planetarium/PlanetNode.test.tsx` (remove the now-moved test)

**Interfaces:**
- Consumes: `getPlanetariumNodeDetail` (Task 4), `describeNode` (Task 5).
- Produces: `ConceptDetailPanel({ conceptId, onClose }: { conceptId: string; onClose: () => void })`, and re-exports `buildConceptHref(conceptId: string): string` (moved from `PlanetNode.tsx`) — used by Task 9's `page.tsx`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/planetarium/ConceptDetailPanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, expect, test, vi } from "vitest"
import type { PlanetariumNodeDetail } from "@/lib/types"

vi.mock("@/lib/api", () => ({ getPlanetariumNodeDetail: vi.fn() }))

import { getPlanetariumNodeDetail } from "@/lib/api"
import { buildConceptHref, ConceptDetailPanel } from "./ConceptDetailPanel"

const mockGetDetail = vi.mocked(getPlanetariumNodeDetail)

function detail(overrides: Partial<PlanetariumNodeDetail> = {}): PlanetariumNodeDetail {
  return {
    conceptId: "c1",
    conceptName: "Alpha",
    conceptType: "entity",
    description: null,
    mass: 0.5,
    brightness: 0.5,
    visualClass: "planet",
    revisionCount: 2,
    edgeCount: 3,
    contradictionCount: 0,
    pinCount: 1,
    isEmbedded: true,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

test("buildConceptHref routes to the concept detail page", () => {
  expect(buildConceptHref("c-123")).toBe("/concepts/c-123")
})

test("shows a loading state, then the concept's name and breakdown", async () => {
  mockGetDetail.mockResolvedValueOnce(detail())
  render(<ConceptDetailPanel conceptId="c1" onClose={vi.fn()} />)

  expect(screen.getByText(/loading/i)).toBeInTheDocument()
  expect(await screen.findByText("Alpha")).toBeInTheDocument()
  expect(screen.getByText(/2 revisions/i)).toBeInTheDocument()
  expect(screen.getByText(/3 edges/i)).toBeInTheDocument()
  expect(screen.getByRole("link", { name: /view full concept/i })).toHaveAttribute(
    "href",
    "/concepts/c1"
  )
})

test("flags when a node isn't semantically positioned", async () => {
  mockGetDetail.mockResolvedValueOnce(detail({ isEmbedded: false }))
  render(<ConceptDetailPanel conceptId="c1" onClose={vi.fn()} />)

  expect(await screen.findByText(/not semantically positioned/i)).toBeInTheDocument()
})

test("shows an error message when the fetch fails", async () => {
  mockGetDetail.mockRejectedValueOnce(new Error("boom"))
  render(<ConceptDetailPanel conceptId="c1" onClose={vi.fn()} />)

  expect(await screen.findByRole("alert")).toHaveTextContent("boom")
})

test("calls onClose when the close button is clicked", async () => {
  mockGetDetail.mockResolvedValueOnce(detail())
  const onClose = vi.fn()
  render(<ConceptDetailPanel conceptId="c1" onClose={onClose} />)
  await screen.findByText("Alpha")

  await userEvent.click(screen.getByRole("button", { name: /close/i }))
  expect(onClose).toHaveBeenCalled()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/planetarium/ConceptDetailPanel.test.tsx`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement `ConceptDetailPanel`**

Create `frontend/src/components/planetarium/ConceptDetailPanel.tsx`:

```tsx
"use client"

import { useEffect, useState } from "react"
import { getPlanetariumNodeDetail } from "@/lib/api"
import type { PlanetariumNodeDetail } from "@/lib/types"
import { describeNode } from "./describeNode"

export function buildConceptHref(conceptId: string): string {
  return `/concepts/${conceptId}`
}

interface ConceptDetailPanelProps {
  conceptId: string
  onClose: () => void
}

export function ConceptDetailPanel({ conceptId, onClose }: ConceptDetailPanelProps) {
  const [detail, setDetail] = useState<PlanetariumNodeDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDetail(null)
    setError(null)
    getPlanetariumNodeDetail(conceptId)
      .then(setDetail)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load concept detail")
      })
  }, [conceptId])

  return (
    <div className="fixed right-6 top-24 z-50 w-80 rounded-hearth border border-hairline bg-surface p-4 shadow-lg">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-heading text-sm text-ink">
          {detail ? detail.conceptName : "Concept"}
        </span>
        <button onClick={onClose} aria-label="Close" className="text-xs font-ui text-muted hover:text-ink">
          Close
        </button>
      </div>

      {error !== null && (
        <p role="alert" className="text-xs text-muted">
          {error}
        </p>
      )}

      {error === null && detail === null && <p className="text-xs text-muted">Loading…</p>}

      {detail !== null && (
        <div className="space-y-2 text-xs text-muted">
          <p className="text-ink">{detail.conceptType}</p>
          <p>{describeNode(detail)}</p>
          <p>
            {detail.revisionCount} revisions, {detail.edgeCount} edges,{" "}
            {detail.contradictionCount} contradictions, {detail.pinCount} pins.
          </p>
          <p>
            {detail.isEmbedded
              ? "Positioned by content similarity to other concepts."
              : "No content yet — not semantically positioned, placed arbitrarily to avoid overlap."}
          </p>
          <a
            href={buildConceptHref(detail.conceptId)}
            className="inline-block font-ui text-ink underline hover:text-muted"
          >
            View full concept →
          </a>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Move `buildConceptHref` out of `PlanetNode.tsx`**

In `frontend/src/components/planetarium/PlanetNode.tsx`, remove this function (it now lives in `ConceptDetailPanel.tsx`):

```typescript
export function buildConceptHref(conceptId: string): string {
  return `/concepts/${conceptId}`
}
```

In `frontend/src/components/planetarium/PlanetNode.test.tsx`, remove the test that imports it:

```typescript
test("buildConceptHref routes to the concept detail page", () => {
  expect(buildConceptHref("c-123")).toBe("/concepts/c-123")
})
```

and its now-unused `import { buildConceptHref } from "./PlanetNode"` line. (Task 8 rewrites the rest of this file and its test anyway — this step just prevents a broken intermediate state if these tasks run out of order.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/planetarium/ConceptDetailPanel.test.tsx`
Expected: PASS

- [ ] **Step 6: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (note: `PlanetNode.tsx` will still reference `buildConceptHref` internally until Task 8 — if Task 8 hasn't run yet, leave `PlanetNode.tsx`'s own usage of `buildConceptHref` as a local import from `./ConceptDetailPanel` for now: add `import { buildConceptHref } from "./ConceptDetailPanel"` to `PlanetNode.tsx` so it still compiles standalone)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/planetarium/ConceptDetailPanel.tsx frontend/src/components/planetarium/ConceptDetailPanel.test.tsx frontend/src/components/planetarium/PlanetNode.tsx frontend/src/components/planetarium/PlanetNode.test.tsx
git commit -m "feat: add ConceptDetailPanel explaining why a node looks the way it does"
```

---

### Task 8: `PlanetNode` hover label + click wiring, `PlanetariumScene` prop threading

**Files:**
- Modify: `frontend/src/components/planetarium/PlanetNode.tsx`
- Modify: `frontend/src/components/planetarium/PlanetNode.test.tsx`
- Modify: `frontend/src/components/planetarium/PlanetariumScene.tsx`

**Interfaces:**
- Consumes: `PlanetariumNode.conceptName` (Task 4).
- Produces: `PlanetNode({ node, color, onSelect }: { node: PlanetariumNode; color: string; onSelect: (conceptId: string) => void })`; `PlanetariumScene({ nodes, onSelect }: { nodes: PlanetariumNode[]; onSelect: (conceptId: string) => void })` — used by Task 9's `page.tsx`.

- [ ] **Step 1: Update `PlanetNode.test.tsx`**

Replace the full contents of `frontend/src/components/planetarium/PlanetNode.test.tsx` with a test for the pure logic that remains testable outside the canvas (the click→`onSelect` wiring is exercised via browser-preview verification in Task 9, matching this repo's established convention that `<Canvas>` content isn't unit-tested):

```typescript
import { expect, test } from "vitest"
import { hoverLabelFor } from "./PlanetNode"

test("hoverLabelFor returns the concept's name", () => {
  expect(hoverLabelFor({ conceptName: "Alpha" } as never)).toBe("Alpha")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/planetarium/PlanetNode.test.tsx`
Expected: FAIL — `hoverLabelFor` is not exported

- [ ] **Step 3: Implement the hover label and click wiring**

Replace `frontend/src/components/planetarium/PlanetNode.tsx` in full:

```tsx
"use client"

import { useState } from "react"
import { Html } from "@react-three/drei"
import type { ThreeEvent } from "@react-three/fiber"
import type { PlanetariumNode } from "@/lib/types"

export function hoverLabelFor(node: PlanetariumNode): string {
  return node.conceptName
}

interface PlanetNodeProps {
  node: PlanetariumNode
  color: string
  onSelect: (conceptId: string) => void
}

// A touch of self-illumination keeps faces angled away from the light
// readable — on the dark canvas they'd otherwise fall to near-black, and it
// gives the nodes a faint "glowing body" feel on both themes.
export function PlanetNode({ node, color, onSelect }: PlanetNodeProps) {
  const [hovered, setHovered] = useState(false)

  function handleClick(event: ThreeEvent<MouseEvent>) {
    event.stopPropagation()
    onSelect(node.conceptId)
  }

  return (
    <mesh
      position={[node.x, node.y, node.z]}
      onClick={handleClick}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => {
        event.stopPropagation()
        setHovered(true)
      }}
      onPointerOut={() => setHovered(false)}
    >
      <icosahedronGeometry args={[node.radius, 1]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.35} flatShading />
      {hovered && (
        <Html distanceFactor={10} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded bg-surface px-2 py-1 text-xs text-ink shadow">
            {hoverLabelFor(node)}
          </div>
        </Html>
      )}
    </mesh>
  )
}
```

Note this removes the `useRouter`/`buildConceptHref` import entirely — clicking now calls `onSelect`, not navigation (that moved to `ConceptDetailPanel`'s "View full concept" link in Task 7).

In `frontend/src/components/planetarium/PlanetariumScene.tsx`, add an `onSelect` prop and thread it through:

```tsx
interface PlanetariumSceneProps {
  nodes: PlanetariumNode[]
  onSelect: (conceptId: string) => void
}

export function PlanetariumScene({ nodes, onSelect }: PlanetariumSceneProps) {
  const { mode } = useMode()
  const palette = PALETTE[mode]

  return (
    <Canvas camera={{ position: [0, 0, 30], fov: 60 }} style={{ width: "100%", height: "100%" }}>
      <color attach="background" args={[palette.bg]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[10, 10, 10]} intensity={1} />
      {palette.stars && <Stars radius={100} depth={50} count={2000} factor={4} fade />}
      <Bounds fit observe margin={1.2}>
        {nodes.map((node) => (
          <PlanetNode
            key={node.id}
            node={node}
            color={node.visualClass === "black_hole" ? palette.blackHole : palette.planet}
            onSelect={onSelect}
          />
        ))}
      </Bounds>
      <OrbitControls makeDefault />
    </Canvas>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/planetarium/PlanetNode.test.tsx`
Expected: PASS

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/planetarium/PlanetNode.tsx frontend/src/components/planetarium/PlanetNode.test.tsx frontend/src/components/planetarium/PlanetariumScene.tsx
git commit -m "feat: hover label and in-place selection for planetarium nodes"
```

---

### Task 9: Wire up `page.tsx` and verify in the browser

**Files:**
- Modify: `frontend/src/app/(app)/planetarium/page.tsx`

**Interfaces:**
- Consumes: `PlanetariumScene` with `onSelect` (Task 8), `ConceptDetailPanel` (Task 7), `PlanetariumLegend` (Task 6).

- [ ] **Step 1: Implement the page wiring**

Replace `frontend/src/app/(app)/planetarium/page.tsx` in full:

```tsx
"use client"

import { useCallback, useEffect, useState } from "react"
import { listPlanetariumNodes } from "@/lib/api"
import type { PlanetariumNode } from "@/lib/types"
import { ConceptDetailPanel } from "@/components/planetarium/ConceptDetailPanel"
import { PlanetariumLegend } from "@/components/planetarium/PlanetariumLegend"
import { PlanetariumScene } from "@/components/planetarium/PlanetariumScene"
import { RebuildButton } from "@/components/planetarium/RebuildButton"

export default function PlanetariumPage() {
  const [nodes, setNodes] = useState<PlanetariumNode[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedConceptId, setSelectedConceptId] = useState<string | null>(null)

  const load = useCallback(() => {
    listPlanetariumNodes()
      .then(setNodes)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load the Planetarium")
      })
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const isLoading = nodes === null && error === null

  return (
    <div className="relative h-screen w-full">
      <div className="absolute right-4 top-4 z-10">
        <RebuildButton onRebuildComplete={load} />
      </div>

      <div className="absolute left-4 top-4 z-10">
        <PlanetariumLegend />
      </div>

      {error !== null && (
        <div
          role="alert"
          className="absolute left-4 top-20 z-10 rounded-hearth border border-hairline bg-surface px-4 py-2 text-sm text-muted"
        >
          {error}
        </div>
      )}

      {isLoading && <p className="absolute left-4 top-20 z-10 text-sm text-muted">Loading…</p>}

      {!isLoading && nodes !== null && nodes.length === 0 && (
        <p className="absolute left-4 top-20 z-10 text-sm text-muted">
          Nothing to show yet — trigger a rebuild.
        </p>
      )}

      {nodes !== null && nodes.length > 0 && (
        <PlanetariumScene nodes={nodes} onSelect={setSelectedConceptId} />
      )}

      {selectedConceptId !== null && (
        <ConceptDetailPanel
          conceptId={selectedConceptId}
          onClose={() => setSelectedConceptId(null)}
        />
      )}
    </div>
  )
}
```

(Moved the error/loading/empty messages from `top-4` to `top-20` so they don't sit directly under the new legend button in the same corner.)

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS (all suites, including `planetarium.test.tsx`, `PlanetariumLegend.test.tsx`, `ConceptDetailPanel.test.tsx`, `PlanetNode.test.tsx`, `api.test.ts`)

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Verify in the browser**

Start the frontend dev server (and backend/worker if not already running) and open `/planetarium` with at least one rebuilt concept present. Confirm:
- The legend renders top-left by default and can be closed/reopened.
- Hovering a node shows its name near the cursor without triggering an orbit-drag.
- Clicking a node opens the panel on the right with its name, type, plain-language summary, factor breakdown, and position-basis line — the map stays visible and orbitable behind it.
- Clicking a node that has no embedding shows the "not semantically positioned" message.
- The panel's "View full concept →" link navigates to `/concepts/{id}`.
- Closing the panel returns to free map exploration.

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/app/(app)/planetarium/page.tsx"
git commit -m "feat: wire planetarium legend and detail panel into the page"
```

---

## Self-Review Notes

- **Spec coverage:** every spec section has a task — encodings/API shape (Tasks 1–3), types/client (Task 4), plain-language summary (Task 5), legend (Task 6), detail panel (Task 7), hover/click (Task 8), page wiring + browser verification (Task 9). The two explicitly-out-of-scope items (nearby-concepts list, editing from the panel) have no task, correctly.
- **Placeholder scan:** no TBD/TODO; every step has real, complete code.
- **Type consistency:** `PlanetariumNodeDetail` field names (`conceptId`, `conceptName`, `conceptType`, `description`, `mass`, `brightness`, `visualClass`, `revisionCount`, `edgeCount`, `contradictionCount`, `pinCount`, `isEmbedded`) are identical across Task 4 (definition), Task 5 (`describeNode` consumption), and Task 7 (`ConceptDetailPanel` consumption). `onSelect(conceptId: string)` signature is identical across Task 8 (`PlanetNode`/`PlanetariumScene`) and Task 9 (`page.tsx`). `buildConceptHref` is defined once (Task 7, `ConceptDetailPanel.tsx`) and only referenced, not redefined, elsewhere.
