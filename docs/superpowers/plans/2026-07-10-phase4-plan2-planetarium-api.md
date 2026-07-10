# Planetarium API (Phase 4 Plan 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the merged Planetarium Engine over HTTP: `POST /planetarium/rebuild` to trigger a rebuild, `GET /planetarium/nodes` to read the current projection.

**Architecture:** One new router, `backend/app/api/planetarium.py`, registered in `main.py` alongside the existing routers. No new kernel logic — both endpoints call functions that already exist (`JobRepository.create`, `project_planetarium.send`, `PlanetaryNodeRepository.list_for_user`).

**Tech Stack:** FastAPI, the existing `get_current_user`/`session`/`JobRepository` dependencies.

## Global Constraints

- `POST /planetarium/rebuild`: `status_code=202`, no request body, creates a `Job` row (`job_type="project_planetarium"`, no payload), sends `project_planetarium.send(user_id, str(job.id))` after the `session()` block closes, returns `{"job_id": str(job.id), "status": "pending"}` — identical shape to `POST /sources/{source_id}/embed-claims`.
- No duplicate-rebuild guard — every call enqueues a fresh job.
- `GET /planetarium/nodes`: returns `list[dict]`, one dict per `PlanetaryNode`, via a `_serialize` function following `jobs.py`'s exact style (every field name-for-name, `created_at` as `.isoformat()`). Empty list for a user with no nodes yet — not an error.
- No new job-status endpoint — reuses the existing `GET /jobs/{job_id}`.
- Both endpoints require `get_current_user` (401 without auth), matching every other route.

---

### Task 1: Router, endpoints, and tests

**Files:**
- Create: `backend/app/api/planetarium.py`
- Modify: `backend/app/main.py` (register the router)
- Test: `tests/backend/test_planetarium_api.py`

**Interfaces:**
- Consumes: `kernel.db.jobs.JobRepository`, `kernel.db.planetary_nodes.PlanetaryNodeRepository`, `kernel.db.session.session`, `worker.tasks.project_planetarium.project_planetarium`, `backend.app.auth.dependencies.get_current_user` (all pre-existing).
- Produces: `router` (FastAPI `APIRouter`) exporting `POST /planetarium/rebuild` and `GET /planetarium/nodes` — Plan 3's frontend calls these two routes directly by path, no further kernel interface needed.

- [ ] **Step 1: Write the failing tests**

Create `tests/backend/test_planetarium_api.py`:

```python
from __future__ import annotations

import os

import pytest

from kernel.db.jobs import JobRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.session import session


@pytest.fixture(autouse=True)
def _no_broker(monkeypatch):  # type: ignore[no-untyped-def]
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.planetarium.project_planetarium.send",
        lambda *a, **k: calls.append(a),
    )
    return calls


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


def _node(concept_id) -> dict:
    return {
        "concept_id": concept_id,
        "x": 1.0,
        "y": 2.0,
        "z": 3.0,
        "theta": 0.1,
        "phi": 0.2,
        "radius": 2.0,
        "mass": 0.5,
        "brightness": 0.9,
        "color": "#4a90d9",
        "visual_class": "planet",
        "projection_version": "v1/v1",
        "projection_algorithm": "umap",
    }


@pytest.mark.asyncio
async def test_rebuild_creates_job_and_enqueues(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post("/planetarium/rebuild")

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    async with session(seeded_user) as conn:
        job = await JobRepository(conn).get(body["job_id"])
    assert job is not None
    assert job.job_type == "project_planetarium"
    assert len(_no_broker) == 1


@pytest.mark.asyncio
async def test_rebuild_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.post("/planetarium/rebuild")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rebuild_has_no_duplicate_guard(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    first = await client.post("/planetarium/rebuild")
    second = await client.post("/planetarium/rebuild")

    assert first.json()["job_id"] != second.json()["job_id"]
    assert len(_no_broker) == 2


@pytest.mark.asyncio
async def test_list_nodes_empty_for_fresh_user(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/planetarium/nodes")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_nodes_returns_serialized_nodes(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Alpha", concept_type="entity"
        )
        assert concept is not None
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            seeded_user, [_node(concept.id)]
        )

    await _login(client)
    r = await client.get("/planetarium/nodes")

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["concept_id"] == str(concept.id)
    assert body[0]["visual_class"] == "planet"
    assert body[0]["mass"] == 0.5


@pytest.mark.asyncio
async def test_list_nodes_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.get("/planetarium/nodes")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_nodes_isolated_between_tenants(client, seeded_user, make_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    other_user = await make_user()
    async with session(other_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=other_user, concept_name="Secret", concept_type="entity"
        )
        assert concept is not None
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            other_user, [_node(concept.id)]
        )

    await _login(client)
    r = await client.get("/planetarium/nodes")

    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/backend/test_planetarium_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.api.planetarium'` (or a 404 from FastAPI once the module import itself is patched around — either way, no passing tests yet)

- [ ] **Step 3: Implement the router**

Create `backend/app/api/planetarium.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from kernel.db.jobs import JobRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.session import session
from kernel.models import PlanetaryNode
from worker.tasks.project_planetarium import project_planetarium

router = APIRouter()


def _serialize(node: PlanetaryNode) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "concept_id": str(node.concept_id),
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
    return [_serialize(node) for node in nodes]
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, add `planetarium` to the import tuple (alphabetically, between `observations` and `search`):

```python
from backend.app.api import (
    auth,
    claims,
    concepts,
    contradictions,
    custodian,
    dashboard,
    jobs,
    observations,
    planetarium,
    search,
    sources,
)
```

Add the registration line after `app.include_router(custodian.router)`:

```python
    app.include_router(custodian.router)
    app.include_router(planetarium.router)
    app.include_router(search.router)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/backend/test_planetarium_api.py -v`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/planetarium.py backend/app/main.py tests/backend/test_planetarium_api.py
git commit -m "feat: add Planetarium API (rebuild trigger, node listing)"
```

---

### Task 2: Docs

**Files:**
- Modify: `README.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add the README section**

In `README.md`, immediately after the "Phase 4 Planetarium Engine" section (added by Plan 1) and before "## Project Layout", add:

```markdown
## Phase 4 Planetarium API

`POST /planetarium/rebuild` triggers a projection rebuild (creates a `Job`,
enqueues the existing `project_planetarium` worker task, returns
`{"job_id", "status": "pending"}` — poll `GET /jobs/{job_id}` for
completion, same as any other background job in this app). `GET
/planetarium/nodes` returns the user's current `planetary_nodes` rows. No
frontend yet — see the Phase 4 roadmap for Plan 3.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document the Planetarium API"
```

---

## Final Verification

- [ ] Run the full test suite: `pytest`
- [ ] Run `ruff check backend/` and `mypy backend/`.
