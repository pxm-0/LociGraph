# Phase 4 Roadmap — Planetarium

## Summary

Per `implementation/06_Roadmap.md`, Phase 4 is "Planetarium." Per
`ADR-003-Planetarium-Over-Graph-First`, the primary high-level navigation
surface for the archive is a celestial/spatial visualization, not a flat
node-link graph — planets encode concepts, mass encodes importance, orbit
encodes evolution, rings encode contradictions, and so on
(`architecture/07_Planetarium_Physics.md`). Every phase since Phase 0
deferred graph/embedding-visualization work here explicitly (Phase 0 Plan 4's
frontend, Phase 1 Plan 2's concepts/graph, Phase 1 Plan 3's embeddings), so
Phase 4 is where that deferred surface finally gets built.

Some of the data layer already exists on `main`: `implementation/02_Data_Model.md`
and `07_Planetarium_Physics.md` spec a `planetary_nodes` table
(x/y/z/radius/theta/phi/mass/brightness/color/visual_class/projection_version/
projection_algorithm) and an `importance_signals` table feeding "mass" — but
neither table nor any Planetarium code exists yet (confirmed via repo-wide
search). What those docs never specified: the actual projection algorithm,
the mass formula's concrete inputs, the interaction model, or the
"Planetarium Librarian" background role's responsibilities. This roadmap
resolves those gaps.

**Data gap found during scoping:** `importance_signals` was actually shipped
in Phase 3 (migration `0012`, Custodian logging) as a bare event log —
`id, user_id, target_type, target_id, created_at` — not the 9-factor
`signal_type`/`value`/`source` schema `02_Data_Model.md` described. Only 4
real per-concept signals are queryable today: `importance_signals` pin
count, `revisions` count, `claim_concept_edges` count (a centrality proxy),
and `contradictions` count. The other 6 named factors (frequency,
emotional_intensity, time_depth, ai_significance, custodian_interaction,
recency) have no data source and are out of scope for this phase.

## Plans

### Plan 1: Planetarium Engine

Kernel + worker layer. Adds the `planetary_nodes` table and a
`PlanetaryNodeRepository`. Computes each concept's "mass" as a versioned
weighted sum over the 4 real signals above (no LLM call — deterministic and
debuggable). Computes 3D spatial coordinates by running UMAP (3 components,
fixed `random_state`) over each concept's existing claim embeddings. Maps
mass/contradiction-count/edge-count to `visual_class` per the physics
mapping (`planet`, `moon`, `star`, `black_hole`, `constellation_anchor`,
`archive_point`). Exposes `kernel.rebuild_planetarium(user_id)`, wired to a
`project_planetarium` dramatiq job following the existing `Job`/
`JobRepository` pattern (`worker/tasks/embed_claims.py`'s
mark_running/update_progress/mark_completed shape). A rebuild replaces all
of a user's `planetary_nodes` rows — the projection is a disposable cache,
never a source of truth (`07_Planetarium_Physics.md`: "the sphere is
visualization, not truth").

### Plan 2: Planetarium API

Backend surface over Plan 1: `POST /planetarium/rebuild` (creates a Job,
enqueues the actor, returns the job id — same shape as the existing
`backend/app/api/jobs.py` pattern) and `GET /planetarium/nodes` (returns the
current `planetary_nodes` rows for the authenticated user, RLS-scoped like
every other table). No new job-status endpoint — reuses the existing
`GET /jobs/{id}`.

### Plan 3: Planetarium Visualization

Frontend surface: `frontend/src/app/(app)/planetarium/page.tsx`, a React
Three Fiber 3D scene (new dependency — no WebGL library exists in the
frontend today) rendering nodes by `visual_class`, orbit camera controls,
click-to-navigate to the existing concept detail page (Phase 2), a rebuild
trigger button that polls the existing job-status endpoint during a run,
a `Sidebar.tsx` nav entry, and integration with the existing Hearth/Meridian
mode toggle (`useMode()` in `frontend/src/lib/theme.tsx`).

### Plan 4: Planetarium Librarian

Minimal background policy on top of Plans 1–2: a threshold check (e.g. N
new claims/concepts/contradictions accumulated since the user's last
rebuild) that automatically triggers `rebuild_planetarium(user_id)` so users
aren't required to manually rebuild. This is the first of the
`implementation/03_AI_Architecture.md` "Librarian" roles to get a concrete,
shipped responsibility — every other Librarian (Claim, Concept, Revision,
Contradiction, Janitor) remains unscoped and deferred.

## Out of scope (all of Phase 4)

- The other 6 importance-signal factors (frequency, emotional_intensity,
  time_depth, ai_significance, custodian_interaction, recency) — no data
  source exists; a future phase can extend `importance_signals` to the full
  `signal_type`/`value`/`source` schema and add a v2 mass formula.
- Any Librarian role other than Planetarium Librarian.
- Concept-to-concept edges / inferred relationships beyond existing
  claim-to-concept mentions (still deferred, as in Phase 1 Plan 2).
- An in-scene overlay/detail panel — clicking a planet navigates to the
  existing concept page rather than rendering a new inline UI.
- Real-time/streaming updates to the 3D view while a rebuild runs (the view
  polls job status like the existing Jobs page; nodes refresh once the job
  completes, not incrementally).
- Voice/multimodal interaction with the Planetarium.

## Ordering

Plan 1 → Plan 2 → Plan 3 → Plan 4, strictly sequential (each is a
prerequisite for the next: the engine before the API, the API before the
view, and the view before an automated trigger for it makes sense to build).
Each gets its own design doc and implementation plan, written and executed
one at a time — matching Phase 3's pattern.
