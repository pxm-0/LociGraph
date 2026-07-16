# Planetarium Legibility Design

## Purpose

The Planetarium (Phase 4 Plan 3) renders every concept as a node whose
position, size, color, and glow each encode something — but none of that
encoding is visible anywhere in the UI, and clicking a node navigates away
immediately with no on-map identity shown first. A user looking at the
scene can tell that clumped nodes are "similar" and spread-out ones aren't,
but has no way to answer "what is this node" or "why does it look/sit like
this." This plan adds a legend, a hover label, and an in-place detail panel
so the map is legible without leaving it.

This reverses one call from the original visualization plan ("Any in-scene
overlay/detail panel — clicking navigates away... decided back in the
Phase 4 roadmap") — that was the right call for a first version with zero
polish; legibility is now the actual complaint.

## What each encoding means (context for the rest of this doc)

Computed in `kernel/planetarium.py` / `kernel/planetarium_physics.py`:

- **Position** (`x/y/z`, `theta/phi`): UMAP projection of the concept's mean
  claim embedding — clustering reflects real semantic similarity, *but
  only for concepts that have an embedding*. Concepts with none (no claim
  embedded yet) are scattered on a fallback Fibonacci-sphere shell purely to
  avoid piling onto the origin — that placement carries no meaning at all.
  There is currently no signal anywhere telling the user which case they're
  looking at.
- **Size** (`radius`, from `mass`): a blended, normalized 0–1 score across
  the user's own concepts — 25% each of revision count, edge count,
  contradiction count, and importance-pin count. Bigger = more
  revised/connected/contradicted/pinned, not "more true" or "more central."
- **Color** (`visual_class`): `black_hole` if in the top 10% of mass
  percentile (and at least 5 concepts exist total), else `planet`.
- **Glow** (`brightness`): `exp(-days_since_last_activity / 30)` — recency
  of any revision/edge/contradiction/pin/vector touching the concept.

None of this is new data to compute — it's all already stored on
`planetary_nodes` (`mass`, `brightness`, `color`, `visual_class`) except
the raw per-factor counts and the embedded-vs-fallback flag, which don't
exist as stored/exposed values today.

## API changes

**`GET /planetarium/nodes`** (existing bulk list, unchanged shape otherwise):
adds `concept_name` and `concept_type` via a join against `concepts` in
`PlanetaryNodeRepository.list_for_user` (or a thin wrapper in the API layer
— implementation detail for the plan). One extra join column, no N+1 risk,
powers the hover label without a per-node network call.

**`GET /planetarium/nodes/{concept_id}/detail`** (new, called only when a
node is clicked — lazy, one concept at a time): returns

```json
{
  "concept_id": "...",
  "concept_name": "...",
  "concept_type": "...",
  "description": "...",
  "mass": 0.72,
  "brightness": 0.82,
  "visual_class": "black_hole",
  "revision_count": 4,
  "edge_count": 7,
  "contradiction_count": 1,
  "pin_count": 2,
  "is_embedded": true
}
```

`mass`/`brightness`/`visual_class` come straight from the existing
`planetary_nodes` row for that concept (already computed at rebuild time —
no recomputation). `revision_count`/`edge_count`/`contradiction_count`/
`pin_count` are fetched fresh via the same single-concept repository
methods the old (pre-fix) `rebuild_planetarium` used per concept
(`RevisionRepository.list`, `ClaimConceptEdgeRepository.list_for_concept`,
`ContradictionRepository.list`, `ImportanceSignalRepository.list_for_target`)
— fine here because this is one concept, on a user click, not N concepts
in a rebuild loop. `is_embedded` is `bool(SemanticVectorRepository
.list_for_concept(concept_id))` — true iff the concept has at least one
claim embedding, which is exactly the condition `rebuild_planetarium`
already uses to decide UMAP-placement vs. fallback-shell.

Rejected alternative: denormalizing all of this onto `planetary_nodes` via
a migration at rebuild time. Rejected because it duplicates data that
already lives on `Concept` (name/type/description could drift stale
between rebuilds) and bloats every node's stored payload for detail that's
only ever read for the handful of nodes a user actually clicks.

## Frontend components

- **`frontend/src/components/planetarium/PlanetariumLegend.tsx`** (new): a
  small dismissible corner panel, shown by default, opposite the existing
  `RebuildButton`. Static plain-language key for the four encodings
  (position/size/color/glow), including the "some nodes aren't
  semantically positioned" caveat. No data fetching — pure static content
  plus open/closed state.
- **`PlanetNode.tsx`** (modified): adds hover state
  (`onPointerOver`/`onPointerOut`) rendering a `@react-three/drei` `<Html>`
  label near the node showing `concept_name` (from the now-enriched
  `PlanetariumNode` prop — no fetch). Click no longer calls
  `router.push` directly; instead it calls an `onSelect(conceptId)` prop
  supplied by `PlanetariumScene`, which the page uses to open the detail
  panel.
- **`frontend/src/components/planetarium/ConceptDetailPanel.tsx`** (new):
  same shape as the existing `CustodianPanel` (slide-in panel, `onClose`
  prop). On mount, fetches `GET /planetarium/nodes/{concept_id}/detail`.
  Renders name + type header, a plain-language summary sentence built from
  `visual_class`/`brightness`/`mass` (e.g. "Large, glowing planet — heavily
  connected and recently active"), the raw factor breakdown, the
  position-basis line (from `is_embedded`), a "View full concept →" link
  (`/concepts/{id}`, the previous click behavior) and a close button.
  Loading/error states follow the same convention as the page-level
  loading/error states already in `planetarium/page.tsx`.
- **`frontend/src/app/(app)/planetarium/page.tsx`** (modified): holds
  `selectedConceptId: string | null` state; passes `onSelect` down to
  `PlanetariumScene`; renders `<ConceptDetailPanel>` when set, `<
  PlanetariumLegend>` always (subject to its own dismiss state).
- **`frontend/src/lib/api.ts`** / **`types.ts`**: `PlanetariumNode` gains
  `conceptName`/`conceptType`; new `getPlanetariumNodeDetail(conceptId)`
  function and `PlanetariumNodeDetail` type, following the existing
  `toX()` snake→camel conversion convention.

## Plain-language summary generation

A pure, independently-testable function (e.g. `describeNode(detail):
string` in a small new module, not inlined in the panel component) maps
`visual_class` + `brightness` + `mass` to a sentence. Kept simple —
a handful of threshold-based sentence fragments (e.g. size adjective from
`mass` tercile, "glowing"/"dim" from a `brightness` threshold,
"black hole"/"planet" from `visual_class`), not a template system or
anything data-driven beyond what's already computed. This mirrors the
`buildConceptHref`-style extraction from the original visualization plan —
logic that can be unit-tested lives outside the Three.js/JSX tree.

## Testing

Same split as the original visualization plan, since the constraint (no
WebGL in jsdom) hasn't changed:

- `describeNode()` and any other pure formatting helpers: plain Vitest unit
  tests (thresholds, edge cases like zero counts, `is_embedded: false`).
- `ConceptDetailPanel`: Vitest + RTL for loading/error/data states, mocking
  `getPlanetariumNodeDetail` — same mocking convention as
  `CustodianPanel`'s existing tests.
- `PlanetariumLegend`: Vitest + RTL for open/dismiss state.
- Hover label and click-opens-panel wiring inside the 3D canvas: verified
  via the browser preview tools (`preview_*`), not unit tests — matches
  the existing project convention for anything inside `<Canvas>`.
- Backend: a test for the new detail endpoint (real test DB, no mocking,
  matching every other backend test in this repo) covering an embedded
  concept, a non-embedded concept, and a 404 for an unknown concept id;
  a test confirming `concept_name`/`concept_type` appear in the bulk list
  response.

## Out of scope (this plan)

- Listing nearby/similar concepts in the panel (considered, explicitly
  deferred — needs a nearest-neighbor query this plan doesn't add).
- Any change to the underlying mass formula, visual classification
  thresholds, or projection algorithm — this plan only makes the existing
  encoding legible, it doesn't change what's encoded.
- Editing a concept from the panel — the "View full concept" link is the
  only escape hatch; editing still happens on the concept page.
- Persisting legend dismiss-state across sessions (localStorage etc.) —
  it resets on reload; add later if it's annoying in practice.
