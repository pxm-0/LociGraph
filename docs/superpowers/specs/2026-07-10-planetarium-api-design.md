# Planetarium API Design (Phase 4 Plan 2)

## Purpose

Expose the Planetarium Engine (Phase 4 Plan 1, merged) over HTTP: trigger a
rebuild and read the current projection. This plan is API-only — no new
kernel logic, no frontend.

## Endpoints

`backend/app/api/planetarium.py` (new router, registered in `main.py`
alongside the existing routers):

### `POST /planetarium/rebuild` (status 202)

```python
@router.post("/planetarium/rebuild", status_code=202)
async def rebuild_planetarium_endpoint(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        job = await JobRepository(conn).create(user_id, "project_planetarium")
    project_planetarium.send(user_id, str(job.id))
    return {"job_id": str(job.id), "status": "pending"}
```

Identical shape to the existing `POST /sources/{source_id}/embed-claims`
endpoint (`backend/app/api/sources.py`): create the `Job` row inside a
`session()` block, send the dramatiq message after the block closes, return
`{"job_id", "status": "pending"}`. No request body — a rebuild always
operates on the calling user's entire archive, there is nothing to
parameterize.

No duplicate-rebuild guard: every call enqueues a fresh job, even if one is
already running for that user. `rebuild_planetarium`'s
delete-then-insert is fully transactional per call — two concurrent
rebuilds can't corrupt data or interleave into a mixed state, only "waste"
one of the two computations (last commit wins). Given this is a
single-user, low-frequency, explicitly user-triggered action (not a hot
path), the wasted-compute cost of a rare double-click doesn't justify the
extra repository method and endpoint logic a guard would need.

### `GET /planetarium/nodes`

```python
@router.get("/planetarium/nodes")
async def list_planetary_nodes(
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        nodes = await PlanetaryNodeRepository(conn).list_for_user(user_id)
    return [_serialize(node) for node in nodes]
```

`_serialize(node: PlanetaryNode) -> dict[str, Any]` follows the exact
pattern already used in `backend/app/api/jobs.py`: every field name-for-name,
`created_at` as `.isoformat()`. Returns `[]` if no rebuild has ever run for
this user — not an error, just an empty archive-projection state (mirrors
how `GET /jobs` returns `[]` for a user with no jobs).

## Job status polling

Reuses the existing `GET /jobs/{job_id}` unchanged — no new status
endpoint. The frontend (Plan 3) polls that route with the `job_id` returned
from `POST /planetarium/rebuild`, exactly as the existing Jobs page already
polls for import/embedding jobs.

## Testing

- `POST /planetarium/rebuild`: returns 202 with a `job_id`; a `Job` row
  exists with `job_type="project_planetarium"` and `status="pending"`;
  calling twice creates two distinct jobs (no guard).
- `GET /planetarium/nodes`: empty list for a fresh user; after directly
  calling `PlanetaryNodeRepository.replace_all_for_user` in the test setup
  (bypassing the worker, matching how other endpoint tests avoid depending
  on dramatiq), returns the serialized nodes with correct field mapping.
- Auth: both endpoints require `get_current_user` (401 without it) — same
  pattern as every other authenticated route, verified with the existing
  test-suite convention rather than a new one-off test.
- Tenant isolation: `GET /planetarium/nodes` only returns the calling
  user's nodes (RLS via `session(user_id)`, already proven at the
  repository level in Plan 1). This is an API-layer concern, not a kernel
  one, so its test lives directly in the new endpoint's test file rather
  than `tests/kernel/test_tenant_isolation.py`: seed a node for user A
  (bypassing the worker, as above), then assert user B's `GET
  /planetarium/nodes` call returns `[]`.

## Out of scope

- Any new job-status endpoint (reuses `GET /jobs/{job_id}`).
- A duplicate-rebuild guard (see rationale above).
- Any frontend code (Plan 3).
- Any automatic/scheduled triggering (Plan 4, Librarian).
