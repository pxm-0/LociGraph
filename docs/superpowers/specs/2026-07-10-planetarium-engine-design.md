# Planetarium Engine Design (Phase 4 Plan 1)

## Purpose

Compute a per-user "planetarium projection": one `planetary_nodes` row per
concept, giving it a 3D position (semantic similarity), a size/mass
(importance), and a visual classification (physics metaphor), so that Plan 3
has something to render. This plan is backend-only (kernel + worker) — no
new API endpoints (Plan 2) and no frontend (Plan 3).

The projection is a disposable, rebuildable cache. It is never a source of
truth: nothing about a concept's canonical state is stored here, only a
derived visualization of state that lives elsewhere (`concepts`, `revisions`,
`claim_concept_edges`, `contradictions`, `importance_signals`). A rebuild
deletes and replaces all of a user's nodes.

## Data inputs (what's real today)

Confirmed by repo inspection — only these four signals have actual data
behind them:

| Signal | Source | Query shape |
|---|---|---|
| `revision_count` | `revisions` (0010) | `COUNT(*) WHERE user_id=:u AND concept_id=:c` |
| `edge_count` | `claim_concept_edges` (0003) | `COUNT(*) WHERE user_id=:u AND concept_id=:c` |
| `contradiction_count` | `contradictions` (0009) | `COUNT(*) WHERE user_id=:u AND concept_id=:c` |
| `pin_count` | `importance_signals` (0012) | `COUNT(*) WHERE user_id=:u AND target_type='concept' AND target_id=:c` |

`implementation/02_Data_Model.md`'s 9-factor `importance_signals` schema
(frequency, recency, emotional_intensity, time_depth, ai_significance,
custodian_interaction) was never built — migration 0012 shipped a bare
`id/user_id/target_type/target_id/created_at` event log instead. This plan
does not touch that table's schema; it only counts existing rows. Extending
`importance_signals` to carry real weighted factors is explicitly out of
scope (noted in the Phase 4 roadmap).

For spatial positioning, a concept's "embedding" is the mean of the
`semantic_vectors.embedding` rows for every claim linked to it via
`claim_concept_edges` (concepts have no embedding of their own — Phase 1
only embeds claims).

For "brightness" (activity/recency — real data, unlike the other unbuilt
recency factor), the concept's most recent related timestamp: the latest of
`concepts.created_at`, and the max `created_at` across its `revisions`,
`claim_concept_edges`, `contradictions`, and `importance_signals` rows.

## Schema: `planetary_nodes`

Matches the columns already named in `implementation/02_Data_Model.md` /
`architecture/07_Planetarium_Physics.md`, migration `0013`:

```sql
CREATE TABLE planetary_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    concept_id UUID NOT NULL REFERENCES concepts(id),
    x DOUBLE PRECISION NOT NULL,
    y DOUBLE PRECISION NOT NULL,
    z DOUBLE PRECISION NOT NULL,
    theta DOUBLE PRECISION NOT NULL,
    phi DOUBLE PRECISION NOT NULL,
    radius DOUBLE PRECISION NOT NULL,
    mass DOUBLE PRECISION NOT NULL,
    brightness DOUBLE PRECISION NOT NULL,
    color TEXT NOT NULL,
    visual_class TEXT NOT NULL,
    projection_version TEXT NOT NULL,
    projection_algorithm TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, concept_id)
);
ALTER TABLE planetary_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE planetary_nodes FORCE ROW LEVEL SECURITY;
CREATE POLICY planetary_nodes_user_isolation ON planetary_nodes
    USING (user_id = current_setting('app.current_user_id')::uuid);
```

`UNIQUE (user_id, concept_id)` — one node per concept per user; a rebuild is
delete-all-then-insert for that user, done inside one transaction.

`visual_class` values shipped in this plan: **`planet`** (default — every
concept) and **`black_hole`** (top decile by mass — "foundational concept",
per the physics doc). `moon` (subconcept), `star`, `constellation_anchor`
(concept cluster), and `archive_point` all require concept-hierarchy or
cross-concept relationship data that doesn't exist yet (concept-to-concept
edges are explicitly out of scope per Phase 1 Plan 2's deferral, reaffirmed
in the Phase 4 roadmap) — deferred to a future plan, not built as unused
enum values.

## Mass formula (`MASS_FORMULA_VERSION = "v1"`)

For each of the 4 signals, min-max normalize across the user's concepts to
`[0, 1]`: `normalized = (value - min) / (max - min)`. If `max == min` (e.g.
a user with one concept, or every concept tied), normalized value is `0.5`
for every concept (named constant `NEUTRAL_NORMALIZED_VALUE`) rather than
dividing by zero.

```
mass = (
    MASS_WEIGHT_REVISION * normalized(revision_count)
    + MASS_WEIGHT_EDGE * normalized(edge_count)
    + MASS_WEIGHT_CONTRADICTION * normalized(contradiction_count)
    + MASS_WEIGHT_PIN * normalized(pin_count)
)
# MASS_WEIGHT_REVISION = MASS_WEIGHT_EDGE = MASS_WEIGHT_CONTRADICTION = MASS_WEIGHT_PIN = 0.25
```

Equal weights for v1 — deliberately unopinionated starting point. Weights
are named module-level constants, not hardcoded inline, so a future
`MASS_FORMULA_VERSION = "v2"` can retune them; `projection_version` on each
row records which formula produced it.

`visual_class = "black_hole"` when `mass` is in the top 10%
(`BLACK_HOLE_MASS_PERCENTILE = 0.9`) of the user's concepts, else `"planet"`.
With fewer than `MIN_CONCEPTS_FOR_BLACK_HOLE = 5` concepts, everyone is a
`"planet"` (a percentile cutoff is meaningless on a handful of items).

## Brightness (activity/recency)

```
days_since_activity = (utcnow() - latest_related_timestamp).days
brightness = exp(-days_since_activity / BRIGHTNESS_DECAY_HALFLIFE_DAYS)
# BRIGHTNESS_DECAY_HALFLIFE_DAYS = 30
```

Produces a value in `(0, 1]` — 1.0 for something touched today, decaying
toward 0 the longer it's been untouched. `latest_related_timestamp` is the
max of `concepts.created_at` and the latest `created_at` among that
concept's `revisions`, `claim_concept_edges`, `contradictions`, and
`importance_signals` rows (a concept with no later activity than its own
creation still gets a well-defined brightness).

## Spatial projection (UMAP)

- Build one embedding per concept: mean of `semantic_vectors.embedding` for
  claims linked via `claim_concept_edges`.
- A concept with zero linked embeddings (no claims yet, or claims not yet
  embedded) is excluded from UMAP input and placed at the origin
  `(0, 0, 0)` as a fallback — this is a real edge case (a freshly created
  concept candidate promoted before embedding finishes) worth a code comment,
  not silent.
- Run `umap.UMAP(n_components=3, random_state=UMAP_RANDOM_STATE, n_neighbors=n)`
  where `n = min(UMAP_N_NEIGHBORS_DEFAULT, k - 1)` and `k` is the number of
  concepts with embeddings (`UMAP_N_NEIGHBORS_DEFAULT = 15`). UMAP requires
  `n_neighbors < n_samples`; below `MIN_CONCEPTS_FOR_UMAP = 3` embeddable
  concepts, skip UMAP entirely and place each at the origin with a small
  deterministic jitter (`index * UMAP_FALLBACK_JITTER` on each axis) so they
  don't all exactly overlap.
- `x, y, z` = the 3 UMAP output components directly (no additional scaling).
- Spherical companions, computed from `x, y, z`:
  `r = sqrt(x**2 + y**2 + z**2)`; `theta = acos(z / r) if r > 0 else 0.0`;
  `phi = atan2(y, x)`.
- `radius` (the rendered node's own size, distinct from the spherical `r`
  above): `NODE_MIN_RADIUS + normalized_mass * (NODE_MAX_RADIUS - NODE_MIN_RADIUS)`,
  reusing the same per-concept normalized mass value computed above
  (`NODE_MIN_RADIUS = 1.0`, `NODE_MAX_RADIUS = 5.0`).
- `color`: a fixed hex string per `visual_class`
  (`COLOR_BY_VISUAL_CLASS = {"planet": "#4a90d9", "black_hole": "#1a1a2e"}`) —
  a real per-pixel gradient by brightness is a Plan 3 (rendering) concern,
  not stored data.
- `projection_algorithm = "umap"`, `projection_version = "v1"` (bumped
  whenever the algorithm or its parameters change).

## Kernel interface

`kernel/planetarium.py` (new, no FastAPI/dramatiq imports — pure
orchestration, matching `kernel/custodian_logging.py`'s pattern):

```python
async def rebuild_planetarium(conn: AsyncConnection, user_id: UUID) -> list[PlanetaryNode]:
    ...
```

Reads all of the user's concepts and the four signal sources, computes mass/
brightness/visual_class/UMAP projection for each, replaces the user's
`planetary_nodes` rows in one transaction via
`PlanetaryNodeRepository.replace_all_for_user(user_id, nodes)`, and returns
the new rows.

`kernel/db/planetary_nodes.py`: `PlanetaryNodeRepository` with
`replace_all_for_user(user_id, nodes: list[PlanetaryNode]) -> list[PlanetaryNode]`
(delete-then-bulk-insert in one transaction) and
`list_for_user(user_id) -> list[PlanetaryNode]` (read-only, used by Plan 2's
API — no other read methods needed since Plan 1 has no consumers of its own
besides the worker).

`kernel/models.py`: new frozen dataclass `PlanetaryNode` with all the
columns above plus `id`, `user_id`, `concept_id`, `created_at`, following the
existing `from_row(cls, row)` classmethod pattern.

## Worker wiring

`worker/tasks/project_planetarium.py`, following `worker/tasks/embed_claims.py`'s
shape exactly:

```python
async def _project_planetarium(user_id: str, job_id: str) -> None:
    async with session(user_id) as conn:
        job_repo = JobRepository(conn)
        await job_repo.mark_running(job_id)
        nodes = await rebuild_planetarium(conn, UUID(user_id))
        await job_repo.mark_completed(job_id, result={"node_count": len(nodes)})
```

wrapped in `@dramatiq.actor(queue_name="extraction", max_retries=3, ...)` +
`run_actor(...)`, with `record_attempt` on exception — identical error
handling to the existing embedding job. `job_type = "project_planetarium"`
(new constant, no job-type enum/registry exists to update — job_type is a
free-text column already). No healing/retry-with-fresh-job-row wrapper is
needed for this job (unlike `embed_claims`'s `heal_embed_claims`) — a
planetarium rebuild is idempotent and safe to just retry via dramatiq's own
`max_retries`, since it fully replaces the output rather than incrementally
appending.

The job row itself is created by Plan 2's API endpoint (`POST
/planetarium/rebuild`), not by this plan — Plan 1 only implements the actor
and the kernel function it calls, matching the existing pattern where
callers create jobs before enqueueing.

## New dependency

`umap-learn` (pulls in `numpy`, `scikit-learn`, `scipy`, `numba` transitively)
— no 3D/embedding-projection library exists in the Python dependencies today.
Added to `pyproject.toml`'s `[project.dependencies]`.

## Testing

- Mass formula: unit tests on the normalization + weighted-sum math directly
  (no DB), including the `max == min` neutral-value edge case.
- `visual_class` threshold: unit test with a synthetic list of masses
  crossing the 90th-percentile boundary, and the `< 5 concepts` fallback.
- Brightness: unit test on the decay formula with known day deltas.
- UMAP fallback paths: integration test with 0, 1, 2 concepts (below
  `MIN_CONCEPTS_FOR_UMAP`) verifying origin/jitter placement instead of a
  UMAP call; separate test with enough concepts to actually invoke UMAP,
  asserting `random_state` determinism (running twice yields identical
  output) rather than fixed coordinate values.
- `rebuild_planetarium`: integration test against the real test DB —
  seed concepts/revisions/edges/contradictions/importance_signals, call it
  twice, assert the second call fully replaces rather than duplicates rows
  (`UNIQUE (user_id, concept_id)` plus row count stays at concept count).
- Worker task: test following `embed_claims`'s existing test pattern —
  job transitions to `running` then `completed` with the right `result`
  shape; a forced exception inside `rebuild_planetarium` results in
  `record_attempt` being called (status `failed`) rather than an uncaught
  exception propagating past the actor.

## Out of scope (this plan)

- `moon`, `star`, `constellation_anchor`, `archive_point` visual classes.
- Any API endpoint (Plan 2) or frontend (Plan 3).
- Automatic/scheduled rebuilds (Plan 4 — Librarian).
- Extending `importance_signals` to a richer schema.
- Per-pixel brightness-driven color gradients (fixed color per `visual_class`
  only).
