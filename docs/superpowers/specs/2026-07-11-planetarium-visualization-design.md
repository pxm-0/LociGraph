# Planetarium Visualization Design (Phase 4 Plan 3)

## Purpose

The frontend 3D scene consuming the merged Planetarium Engine + API
(`GET /planetarium/nodes`, `POST /planetarium/rebuild`, `GET /jobs/{id}`).
Renders each `PlanetaryNode` as a low-poly faceted sphere positioned in 3D
space, lets the user navigate the scene with a mouse-driven camera, and
click a node to jump to its concept's existing detail page.

## Layout: full-bleed page

No existing page skips `AppChrome`'s padding (`p-8` hearth / `p-3`
meridian) — this is the first one that needs to, for an immersive 3D
canvas. `frontend/src/app/(app)/layout.tsx` wraps every route in the same
shared `<AppChrome>{children}</AppChrome>` with no per-route prop passed
in (`children` is opaque to `layout.tsx`), so a prop can't be threaded in
from the route itself. `AppChrome` is already a client component (it reads
`useMode()`), so it gets a `usePathname()` call (from `next/navigation`)
and a small constant, `FULL_BLEED_ROUTES = ["/planetarium"]`; when
`FULL_BLEED_ROUTES.includes(pathname)`, it renders `<main>{children}</main>`
with no padding/max-width wrapper instead of its normal one. Adding a
second full-bleed route later is a one-line addition to the constant, not
a new mechanism.

## Visual style: low-poly faceted

Locked via visual brainstorming (four directions compared: realistic,
low-poly faceted, toon/cel-shaded, glowing-orb/abstract) — low-poly won.
Kept intentionally simple for this first version, not over-engineered:

- Each node is a low-detail icosahedron (`IcosahedronGeometry` with detail
  `0` or `1` — Three.js's standard "faceted sphere" primitive) with
  `flatShading: true` on a `MeshStandardMaterial`, so Three.js's own
  lighting naturally produces the visible flat facets — no custom shader,
  no hand-authored geometry.
- One base color per node, taken directly from the node's `color` field
  (already computed server-side by `color_for_visual_class` in Plan 1) —
  no per-facet color variation for this version. That's a real embellishment
  with no clear payoff yet (flagged during brainstorming, deliberately cut).
- Sphere radius from the node's `radius` field, position from `x`/`y`/`z`.
- A single ambient + one directional light for the whole scene (not
  per-node) — flat shading only needs one light direction to read as
  faceted; no per-node lighting rigs.
- `black_hole` nodes use the same faceted-sphere treatment with their own
  `color` (`#1a1a2e`, already dark) — no distinct geometry or effect yet.
  A future plan can special-case visual_class rendering once `moon`/`star`/
  `constellation_anchor` actually exist as real, computed classes (Plan 1
  currently only ever produces `planet` or `black_hole`).
- Backdrop: `@react-three/drei`'s `<Stars>` component (a few lines,
  standard starfield helper) rather than a custom skybox.
- Brightness is NOT rendered as a glow/bloom effect in this version — that
  was part of the "atmospheric" direction that got superseded by low-poly.
  Brightness data still exists on every node (Plan 1 computed it) and
  remains available for a future refinement; this plan doesn't consume it
  visually yet, to keep the first version's rendering surface small.

## Components

Small, focused files (not one giant page component):

- **`frontend/src/components/planetarium/PlanetariumScene.tsx`** — the
  `<Canvas>`, ambient + directional light, `<Stars>`, and `OrbitControls`
  (`@react-three/drei`). Receives `nodes: PlanetariumNode[]` as a prop —
  no data-fetching of its own. Maps `nodes` to one `<PlanetNode>` per
  entry.
- **`frontend/src/components/planetarium/PlanetNode.tsx`** — one
  low-poly faceted mesh: `<mesh position={[x,y,z]} onClick={...}>` wrapping
  `<icosahedronGeometry args={[radius, 1]} />` and
  `<meshStandardMaterial color={color} flatShading />`. `onClick` calls
  `router.push(`/concepts/${conceptId}`)` (Next.js `useRouter`).
- **`frontend/src/components/planetarium/RebuildButton.tsx`** — trigger
  button + job-status polling, mirroring the existing Jobs page's
  `useEffect`/`window.setInterval(load, 3000)` pattern exactly. Calls
  `onRebuildComplete()` (a prop) when the polled job reaches `completed`,
  so the parent page knows to re-fetch nodes.
- **`frontend/src/app/(app)/planetarium/page.tsx`** — thin: fetches nodes
  on mount via `listPlanetariumNodes()`, holds three states (loading /
  error / data, matching the Jobs page's `null`-data-and-no-error =
  loading convention), renders an empty-state message when `nodes.length
  === 0` ("Nothing to show yet — trigger a rebuild"), otherwise renders
  `<PlanetariumScene nodes={nodes} />` plus `<RebuildButton
  onRebuildComplete={refetch} />`.

## API client additions

`frontend/src/lib/api.ts`, following existing naming/shape conventions:

- `toPlanetariumNode()` — snake_case → camelCase converter (matches every
  other `toX()` in the file).
- `listPlanetariumNodes(): Promise<PlanetariumNode[]>` → `GET
  /planetarium/nodes`.
- `rebuildPlanetarium(): Promise<{ jobId: string; status: string }>` →
  `POST /planetarium/rebuild` (same return shape as the existing
  `embedClaims()`).

`PlanetariumNode` TypeScript type mirrors the backend's serialized fields:
`id, conceptId, x, y, z, theta, phi, radius, mass, brightness, color,
visualClass, projectionVersion, projectionAlgorithm, createdAt`.

## Navigation

`NavIcon.tsx`'s existing `IconName` union (`dashboard, inventory_2,
database, visibility, analytics, hub, balance, search, orbit, toggle_off,
toggle_on`) has no free icon — `orbit` is already used by the Jobs nav
item. This plan adds one new icon, `"planet"`, to the union: a simple
24x24 line-art SVG (a circle plus a tilted ellipse ring, matching the
existing icons' `stroke="currentColor" strokeWidth="1.5"` style). New
`Sidebar.tsx` `NAV_ITEMS` entry: `{ label: "Planetarium", href:
"/planetarium", icon: "planet" }`.

## Data flow

Page mounts → `listPlanetariumNodes()` → empty-state if `[]` → user clicks
rebuild → `rebuildPlanetarium()` → `job_id` → `RebuildButton` polls `GET
/jobs/{job_id}` every 3s (same interval as the Jobs page) → on `completed`,
calls `onRebuildComplete` → page re-fetches nodes → `PlanetariumScene`
re-renders with the new node set.

## Error handling

Matches the Jobs page's existing convention exactly: a string error state
rendered in a `role="alert"` box on fetch failure; a failed rebuild job's
`error` field surfaced the same way once polling detects `status ===
"failed"`.

## Testing

- Vitest + React Testing Library for the page's loading/empty/error/data
  states (mocking `api.ts`), following the existing Custodian panel test
  file's mocking conventions.
- `RebuildButton`: trigger click → mocked `rebuildPlanetarium` call →
  polling behavior → `onRebuildComplete` fires on a mocked `completed` job
  response.
- `PlanetNode`: since `@react-three/fiber`'s `<Canvas>` needs a real WebGL
  context that jsdom (this project's existing Vitest environment) doesn't
  provide, this component is not rendered in a unit test. Instead,
  `PlanetNode`'s click-to-navigate logic is extracted as a plain,
  independently-testable function (`buildConceptHref(conceptId): string`,
  or equivalent) that the component calls — that function gets a normal
  unit test, and the component itself is covered by the browser-preview
  visual check below. No new testing dependency (no
  `@react-three/test-renderer`) is added for this.
- The 3D canvas's actual visual rendering is verified via the browser
  preview (`preview_*` tools), not unit tests — same as any canvas-based
  feature.

## Out of scope (this plan)

- Per-facet color variation, brightness-driven glow/bloom, distinct
  rendering for `moon`/`star`/`constellation_anchor` visual classes (none
  are produced by Plan 1 yet).
- Any in-scene overlay/detail panel — clicking navigates away to the
  existing concept page (decided back in the Phase 4 roadmap).
- Real-time/incremental updates while a rebuild runs — the scene only
  refreshes once the polled job completes.
- Automatic/scheduled rebuild triggering (Plan 4, Librarian).
