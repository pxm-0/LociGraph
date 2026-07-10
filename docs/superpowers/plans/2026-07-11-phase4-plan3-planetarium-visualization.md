# Planetarium Visualization (Phase 4 Plan 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the frontend 3D Planetarium view: a low-poly faceted-sphere scene over `GET /planetarium/nodes`, a rebuild trigger over `POST /planetarium/rebuild` + `GET /jobs/{id}` polling, click-to-navigate to the existing concept page, and a new full-bleed nav route.

**Architecture:** New API client functions + types (Task 1), a full-bleed layout mechanism in `AppChrome` plus a new nav icon/entry (Task 2), a React Three Fiber scene split into `PlanetariumScene`/`PlanetNode` components (Task 3), a `RebuildButton` component following the codebase's existing single-job-poll pattern (Task 4), and the page tying it together (Task 5).

**Tech Stack:** Next.js 14 (App Router), React 18, TypeScript 5.5, Tailwind, Vitest + React Testing Library, `three` + `@react-three/fiber` + `@react-three/drei` (new dependencies).

## Global Constraints

- New deps in `frontend/package.json`: `"three": "^0.164.0"`,
  `"@react-three/fiber": "^8.17.0"`, `"@react-three/drei": "^9.111.0"` (all
  React-18-compatible versions — `@react-three/fiber` v9 and `drei` v10+
  require React 19, which this project doesn't use).
- Low-poly faceted style, locked via brainstorming: `icosahedronGeometry`
  with detail `1`, `flatShading: true` on `MeshStandardMaterial`, one base
  `color` per node (no per-facet variation), one ambient + one directional
  light for the whole scene, `@react-three/drei`'s `<Stars>` for the
  backdrop. No glow/bloom, no distinct rendering for `moon`/`star`/
  `constellation_anchor` (Plan 1 never produces those visual classes).
- Camera: `@react-three/drei`'s `OrbitControls`, no custom camera code.
- Full-bleed layout: `AppChrome` gets a `FULL_BLEED_ROUTES` constant array
  checked against `usePathname()` (already imported in `AppChrome.tsx`) —
  no prop threading, since `layout.tsx` wraps every route in the same
  `<AppChrome>{children}</AppChrome>` with `children` opaque to it.
- Nav: existing `IconName` union has no free icon (`orbit` is taken by
  Jobs) — add one new icon, `"planet"`.
- Click-to-navigate: extracted as a plain `buildConceptHref(conceptId):
  string` function so it's unit-testable without rendering a WebGL canvas.
- Rebuild trigger/poll: follows `frontend/src/app/(app)/sources/page.tsx`'s
  established `watchJobs`-style pattern — a recursive `setTimeout` loop at
  `1200`ms polling a single job id via `getJob`, checking against
  `TERMINAL_JOB_STATUSES = new Set(["completed", "failed"])` — NOT the
  Jobs page's `setInterval`-over-a-list pattern (that one polls many jobs
  at once; this is a single triggered job, same shape as `sources.tsx`'s
  embed-claims flow).
- No 3D canvas is unit-tested (jsdom has no WebGL) — `PlanetariumScene` is
  mocked out in the page's tests; its actual rendering is verified via the
  browser preview.

---

### Task 1: Dependencies, types, and API client

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/lib/api.test.ts`

**Interfaces:**
- Produces: `PlanetariumNode` type (`frontend/src/lib/types.ts`), matching
  the backend's serialized `planetary_nodes` row exactly. `listPlanetariumNodes(): Promise<PlanetariumNode[]>` and
  `rebuildPlanetarium(): Promise<{ jobId: string; status: string }>`
  (`frontend/src/lib/api.ts`) — Tasks 4 and 5 call these directly.

- [ ] **Step 1: Add the new dependencies**

In `frontend/package.json`, in `"dependencies"`, after `"geist": "1.3.1"`, add:

```json
    "three": "^0.164.0",
    "@react-three/fiber": "^8.17.0",
    "@react-three/drei": "^9.111.0"
```

Run: `cd frontend && npm install`
Expected: install succeeds, `node_modules/three`, `node_modules/@react-three/fiber`, `node_modules/@react-three/drei` present.

- [ ] **Step 2: Add the `PlanetariumNode` type**

In `frontend/src/lib/types.ts`, after the `Job` interface, add:

```typescript
export interface PlanetariumNode {
  id: string
  conceptId: string
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
```

- [ ] **Step 3: Write the failing API client tests**

In `frontend/src/lib/api.test.ts`, add `listPlanetariumNodes` and
`rebuildPlanetarium` to the existing `import { ... } from "./api"` block
(alphabetically), then append at the end of the file:

```typescript
test("listPlanetariumNodes maps snake_case fields to camelCase", async () => {
  const f = mockFetch(200, [
    {
      id: "n1",
      concept_id: "c1",
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

test("rebuildPlanetarium posts to /planetarium/rebuild and returns jobId/status", async () => {
  const f = mockFetch(202, { job_id: "j1", status: "pending" })
  vi.stubGlobal("fetch", f)
  const result = await rebuildPlanetarium()
  expect(result).toEqual({ jobId: "j1", status: "pending" })
  const [url, init] = f.mock.calls[0]
  expect(url).toBe("/api/planetarium/rebuild")
  expect(init.method).toBe("POST")
})
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: FAIL — `listPlanetariumNodes`/`rebuildPlanetarium` not exported from `./api`

- [ ] **Step 5: Implement the API client functions**

In `frontend/src/lib/api.ts`, add `PlanetariumNode` to the `import type { ... } from "./types"` block (alphabetically, after `Observation`), then add, after the `embedClaims` function:

```typescript
function toPlanetariumNode(d: Record<string, unknown>): PlanetariumNode {
  return {
    id: String(d.id),
    conceptId: String(d.concept_id),
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

export async function listPlanetariumNodes(): Promise<PlanetariumNode[]> {
  const r = await req("/planetarium/nodes")
  if (!r.ok) throw await readError(r, "listPlanetariumNodes failed")
  return (await r.json()).map(toPlanetariumNode)
}

export async function rebuildPlanetarium(): Promise<{ jobId: string; status: string }> {
  const r = await req("/planetarium/rebuild", { method: "POST" })
  if (!r.ok) throw await readError(r, "rebuildPlanetarium failed")
  const d = await r.json()
  return { jobId: d.job_id, status: d.status }
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: all tests in the file pass (existing + 2 new)

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/lib/api.test.ts
git commit -m "feat: add three/@react-three/fiber/@react-three/drei and Planetarium API client"
```

---

### Task 2: Full-bleed layout, nav icon, and nav entry

**Files:**
- Modify: `frontend/src/components/layout/AppChrome.tsx`
- Modify: `frontend/src/components/layout/NavIcon.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Test: `frontend/src/components/layout/AppChrome.test.tsx`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `AppChrome` renders `<main>` with no padding on
  `/planetarium`; `"planet"` is a valid `IconName`; `NAV_ITEMS` includes a
  `Planetarium` entry. Task 5's page relies on the full-bleed behavior for
  its layout.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/layout/AppChrome.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react"
import { expect, test, vi } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import { AppChrome } from "./AppChrome"

vi.mock("next/navigation", () => ({ usePathname: () => mockPathname }))
let mockPathname = "/dashboard"

function renderChrome() {
  return render(
    <ThemeProvider>
      <AppChrome>
        <div data-testid="page-content">content</div>
      </AppChrome>
    </ThemeProvider>
  )
}

test("pads the main content area on a normal route", () => {
  mockPathname = "/dashboard"
  renderChrome()
  const main = screen.getByTestId("page-content").closest("main")
  expect(main?.className).toMatch(/p-8/)
})

test("skips padding on the Planetarium route", () => {
  mockPathname = "/planetarium"
  renderChrome()
  const main = screen.getByTestId("page-content").closest("main")
  expect(main?.className).not.toMatch(/p-8/)
  expect(main?.className).not.toMatch(/p-3/)
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/layout/AppChrome.test.tsx`
Expected: FAIL — the `/planetarium` case still has `p-8` (no full-bleed logic yet)

- [ ] **Step 3: Add the full-bleed check to `AppChrome`**

In `frontend/src/components/layout/AppChrome.tsx`, after the `currentPageTitle` function, add:

```typescript
const FULL_BLEED_ROUTES = ["/planetarium"]
```

Change the `AppChrome` function body: after `const isHearth = mode === "hearth"`, add:

```typescript
  const isFullBleed = FULL_BLEED_ROUTES.includes(pathname)
```

Replace the `<main>` element's `className`:

```tsx
        <main
          className={
            isFullBleed
              ? "w-full"
              : ["w-full", isHearth ? "p-8 max-w-[1400px] mx-auto" : "p-3"].join(" ")
          }
        >
          {children}
        </main>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/layout/AppChrome.test.tsx`
Expected: `2 passed`

- [ ] **Step 5: Add the `"planet"` nav icon**

In `frontend/src/components/layout/NavIcon.tsx`, add `"planet"` to the `IconName` union (after `"orbit"`):

```typescript
  | "orbit"
  | "planet"
  | "toggle_off"
```

Add to the `ICONS` map, after the `orbit` entry:

```typescript
  planet: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="6" />
      <ellipse cx="12" cy="12" rx="10" ry="3" transform="rotate(-15 12 12)" />
    </svg>
  ),
```

- [ ] **Step 6: Add the Sidebar nav entry**

In `frontend/src/components/layout/Sidebar.tsx`, in `NAV_ITEMS`, after the `Jobs` entry:

```typescript
  { label: "Jobs", href: "/jobs", icon: "orbit" },
  { label: "Planetarium", href: "/planetarium", icon: "planet" },
```

- [ ] **Step 7: Run the full frontend test suite and typecheck**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass, no type errors

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/layout/AppChrome.tsx frontend/src/components/layout/AppChrome.test.tsx frontend/src/components/layout/NavIcon.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: add full-bleed layout support and Planetarium nav entry"
```

---

### Task 3: 3D scene components

**Files:**
- Create: `frontend/src/components/planetarium/PlanetNode.tsx`
- Create: `frontend/src/components/planetarium/PlanetariumScene.tsx`
- Test: `frontend/src/components/planetarium/PlanetNode.test.tsx`

**Interfaces:**
- Consumes: `PlanetariumNode` type (Task 1).
- Produces: `buildConceptHref(conceptId: string): string`, `PlanetNode({
  node }: { node: PlanetariumNode })`, `PlanetariumScene({ nodes }: {
  nodes: PlanetariumNode[] })` — Task 5's page renders `<PlanetariumScene
  nodes={nodes} />` directly.

- [ ] **Step 1: Write the failing test for the pure navigation function**

Create `frontend/src/components/planetarium/PlanetNode.test.tsx`:

```typescript
import { expect, test } from "vitest"
import { buildConceptHref } from "./PlanetNode"

test("buildConceptHref routes to the concept detail page", () => {
  expect(buildConceptHref("c-123")).toBe("/concepts/c-123")
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/planetarium/PlanetNode.test.tsx`
Expected: FAIL — `./PlanetNode` doesn't exist yet

- [ ] **Step 3: Implement `PlanetNode`**

Create `frontend/src/components/planetarium/PlanetNode.tsx`:

```tsx
"use client"

import { useRouter } from "next/navigation"
import type { ThreeEvent } from "@react-three/fiber"
import type { PlanetariumNode } from "@/lib/types"

export function buildConceptHref(conceptId: string): string {
  return `/concepts/${conceptId}`
}

interface PlanetNodeProps {
  node: PlanetariumNode
}

export function PlanetNode({ node }: PlanetNodeProps) {
  const router = useRouter()

  function handleClick(event: ThreeEvent<MouseEvent>) {
    event.stopPropagation()
    router.push(buildConceptHref(node.conceptId))
  }

  return (
    <mesh position={[node.x, node.y, node.z]} onClick={handleClick}>
      <icosahedronGeometry args={[node.radius, 1]} />
      <meshStandardMaterial color={node.color} flatShading />
    </mesh>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/planetarium/PlanetNode.test.tsx`
Expected: `1 passed`

- [ ] **Step 5: Implement `PlanetariumScene`**

Create `frontend/src/components/planetarium/PlanetariumScene.tsx`:

```tsx
"use client"

import { Canvas } from "@react-three/fiber"
import { OrbitControls, Stars } from "@react-three/drei"
import type { PlanetariumNode } from "@/lib/types"
import { PlanetNode } from "./PlanetNode"

interface PlanetariumSceneProps {
  nodes: PlanetariumNode[]
}

export function PlanetariumScene({ nodes }: PlanetariumSceneProps) {
  return (
    <Canvas camera={{ position: [0, 0, 30], fov: 60 }} style={{ width: "100%", height: "100%" }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[10, 10, 10]} intensity={1} />
      <Stars radius={100} depth={50} count={2000} factor={4} fade />
      {nodes.map((node) => (
        <PlanetNode key={node.id} node={node} />
      ))}
      <OrbitControls />
    </Canvas>
  )
}
```

`PlanetariumScene` itself has no unit test — it requires a real WebGL
context that jsdom doesn't provide. Task 5's page test mocks this module
entirely; its actual rendering is verified via the browser preview at the
end of Task 5.

- [ ] **Step 6: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (confirms the R3F/drei JSX intrinsics — `mesh`,
`icosahedronGeometry`, `meshStandardMaterial`, `ambientLight`,
`directionalLight` — typecheck correctly against `@react-three/fiber`'s
type augmentation)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/planetarium/PlanetNode.tsx frontend/src/components/planetarium/PlanetNode.test.tsx frontend/src/components/planetarium/PlanetariumScene.tsx
git commit -m "feat: add low-poly faceted 3D scene components"
```

---

### Task 4: Rebuild trigger + job polling

**Files:**
- Create: `frontend/src/components/planetarium/RebuildButton.tsx`
- Test: `frontend/src/components/planetarium/RebuildButton.test.tsx`

**Interfaces:**
- Consumes: `rebuildPlanetarium`, `getJob` (Task 1 / pre-existing).
- Produces: `RebuildButton({ onRebuildComplete }: { onRebuildComplete: ()
  => void })` — Task 5's page passes its own node-refetch function as
  `onRebuildComplete`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/planetarium/RebuildButton.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import type { Job } from "@/lib/types"

vi.mock("@/lib/api", () => ({ rebuildPlanetarium: vi.fn(), getJob: vi.fn() }))

import { getJob, rebuildPlanetarium } from "@/lib/api"
import { RebuildButton } from "./RebuildButton"

const mockRebuild = vi.mocked(rebuildPlanetarium)
const mockGetJob = vi.mocked(getJob)

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    jobType: "project_planetarium",
    status: "running",
    attempts: 0,
    error: null,
    createdAt: null,
    startedAt: null,
    completedAt: null,
    itemsCompleted: null,
    itemsTotal: null,
    sourceId: null,
    ...overrides,
  }
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.useRealTimers())

test("triggers a rebuild and calls onRebuildComplete once the job completes", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  mockRebuild.mockResolvedValueOnce({ jobId: "job-1", status: "pending" })
  mockGetJob.mockResolvedValueOnce(makeJob({ status: "completed" }))
  const onRebuildComplete = vi.fn()

  render(<RebuildButton onRebuildComplete={onRebuildComplete} />)
  await userEvent.click(screen.getByRole("button", { name: /rebuild planetarium/i }), {
    delay: null,
  })
  await vi.waitFor(() => expect(mockRebuild).toHaveBeenCalled())

  await vi.advanceTimersByTimeAsync(1200)
  await vi.waitFor(() => expect(onRebuildComplete).toHaveBeenCalled())
})

test("shows the job's error message when the rebuild job fails", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  mockRebuild.mockResolvedValueOnce({ jobId: "job-1", status: "pending" })
  mockGetJob.mockResolvedValueOnce(makeJob({ status: "failed", error: "boom" }))

  render(<RebuildButton onRebuildComplete={vi.fn()} />)
  await userEvent.click(screen.getByRole("button", { name: /rebuild planetarium/i }), {
    delay: null,
  })
  await vi.advanceTimersByTimeAsync(1200)

  expect(await screen.findByRole("alert")).toHaveTextContent("boom")
})

test("disables the button while a rebuild is running", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  mockRebuild.mockResolvedValueOnce({ jobId: "job-1", status: "pending" })
  mockGetJob.mockResolvedValueOnce(makeJob({ status: "completed" }))

  render(<RebuildButton onRebuildComplete={vi.fn()} />)
  const button = screen.getByRole("button", { name: /rebuild planetarium/i })
  await userEvent.click(button, { delay: null })

  expect(button).toBeDisabled()
  await vi.advanceTimersByTimeAsync(1200)
  await vi.waitFor(() => expect(button).not.toBeDisabled())
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/planetarium/RebuildButton.test.tsx`
Expected: FAIL — `./RebuildButton` doesn't exist yet

- [ ] **Step 3: Implement `RebuildButton`**

Create `frontend/src/components/planetarium/RebuildButton.tsx`:

```tsx
"use client"

import { useCallback, useState } from "react"
import { getJob, rebuildPlanetarium } from "@/lib/api"

const TERMINAL_JOB_STATUSES = new Set(["completed", "failed"])
const POLL_INTERVAL_MS = 1200

interface RebuildButtonProps {
  onRebuildComplete: () => void
}

export function RebuildButton({ onRebuildComplete }: RebuildButtonProps) {
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const watchJob = useCallback(
    async (jobId: string) => {
      let active = true
      while (active) {
        await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS))
        const job = await getJob(jobId)
        if (TERMINAL_JOB_STATUSES.has(job.status)) {
          active = false
          if (job.status === "failed") {
            setError(job.error ?? "Planetarium rebuild failed")
          } else {
            onRebuildComplete()
          }
        }
      }
    },
    [onRebuildComplete]
  )

  async function startRebuild() {
    setError(null)
    setIsRunning(true)
    try {
      const result = await rebuildPlanetarium()
      await watchJob(result.jobId)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to trigger rebuild")
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="space-y-2">
      <button
        onClick={startRebuild}
        disabled={isRunning}
        className="rounded-hearth border border-hairline bg-surface px-4 py-2 text-sm text-ink hover:bg-surface-hover disabled:opacity-50"
      >
        {isRunning ? "Rebuilding…" : "Rebuild Planetarium"}
      </button>
      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-4 py-2 text-sm text-muted"
        >
          {error}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/planetarium/RebuildButton.test.tsx`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/planetarium/RebuildButton.tsx frontend/src/components/planetarium/RebuildButton.test.tsx
git commit -m "feat: add Planetarium rebuild trigger with job-status polling"
```

---

### Task 5: The Planetarium page

**Files:**
- Create: `frontend/src/app/(app)/planetarium/page.tsx`
- Test: `frontend/src/app/(app)/planetarium/planetarium.test.tsx`

**Interfaces:**
- Consumes: `listPlanetariumNodes` (Task 1), `PlanetariumScene` (Task 3),
  `RebuildButton` (Task 4).
- Produces: the `/planetarium` route — nothing later depends on this
  file's internals.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/(app)/planetarium/planetarium.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { beforeEach, expect, test, vi } from "vitest"
import type { PlanetariumNode } from "@/lib/types"

vi.mock("@/lib/api", () => ({ listPlanetariumNodes: vi.fn() }))
vi.mock("@/components/planetarium/PlanetariumScene", () => ({
  PlanetariumScene: ({ nodes }: { nodes: PlanetariumNode[] }) => (
    <div data-testid="scene">{nodes.length} nodes</div>
  ),
}))
vi.mock("@/components/planetarium/RebuildButton", () => ({
  RebuildButton: () => <button>Rebuild Planetarium</button>,
}))

import { listPlanetariumNodes } from "@/lib/api"
import PlanetariumPage from "./page"

const mockListPlanetariumNodes = vi.mocked(listPlanetariumNodes)

beforeEach(() => vi.clearAllMocks())

test("shows an empty-state message when there are no nodes yet", async () => {
  mockListPlanetariumNodes.mockResolvedValue([])
  render(<PlanetariumPage />)
  expect(await screen.findByText(/nothing to show yet/i)).toBeInTheDocument()
})

test("renders the scene once nodes load", async () => {
  mockListPlanetariumNodes.mockResolvedValue([{ id: "n1" } as PlanetariumNode])
  render(<PlanetariumPage />)
  expect(await screen.findByTestId("scene")).toHaveTextContent("1 nodes")
})

test("shows an error message on fetch failure", async () => {
  mockListPlanetariumNodes.mockRejectedValue(new Error("boom"))
  render(<PlanetariumPage />)
  expect(await screen.findByRole("alert")).toHaveTextContent("boom")
})

test("always renders the rebuild button", async () => {
  mockListPlanetariumNodes.mockResolvedValue([])
  render(<PlanetariumPage />)
  expect(await screen.findByRole("button", { name: /rebuild planetarium/i })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run "src/app/(app)/planetarium/planetarium.test.tsx"`
Expected: FAIL — `./page` doesn't exist yet

- [ ] **Step 3: Implement the page**

Create `frontend/src/app/(app)/planetarium/page.tsx`:

```tsx
"use client"

import { useCallback, useEffect, useState } from "react"
import { listPlanetariumNodes } from "@/lib/api"
import type { PlanetariumNode } from "@/lib/types"
import { PlanetariumScene } from "@/components/planetarium/PlanetariumScene"
import { RebuildButton } from "@/components/planetarium/RebuildButton"

export default function PlanetariumPage() {
  const [nodes, setNodes] = useState<PlanetariumNode[] | null>(null)
  const [error, setError] = useState<string | null>(null)

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

      {error !== null && (
        <div
          role="alert"
          className="absolute left-4 top-4 z-10 rounded-hearth border border-hairline bg-surface px-4 py-2 text-sm text-muted"
        >
          {error}
        </div>
      )}

      {isLoading && <p className="absolute left-4 top-4 z-10 text-sm text-muted">Loading…</p>}

      {!isLoading && nodes !== null && nodes.length === 0 && (
        <p className="absolute left-4 top-4 z-10 text-sm text-muted">
          Nothing to show yet — trigger a rebuild.
        </p>
      )}

      {nodes !== null && nodes.length > 0 && <PlanetariumScene nodes={nodes} />}
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run "src/app/(app)/planetarium/planetarium.test.tsx"`
Expected: `4 passed`

- [ ] **Step 5: Run the full frontend suite and typecheck**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass, no type errors

- [ ] **Step 6: Commit**

```bash
git add "frontend/src/app/(app)/planetarium/page.tsx" "frontend/src/app/(app)/planetarium/planetarium.test.tsx"
git commit -m "feat: add the Planetarium page"
```

- [ ] **Step 7: Manual browser verification**

Start the frontend dev server and the backend (per this project's existing
local dev setup), log in, navigate to `/planetarium`:
- With no prior rebuild: confirm the empty-state message and the Rebuild
  button both render, full-bleed (no page padding, canvas/content fills
  the viewport under the top app bar).
- Click Rebuild: confirm the button shows "Rebuilding…" and disables,
  then re-enables and the scene populates once the job completes.
- Confirm low-poly faceted spheres render with visible flat facets, a
  starfield background, and mouse-drag orbits the camera
  (`OrbitControls`).
- Click a node: confirm navigation to `/concepts/{id}`.
- Toggle Hearth/Meridian mode: confirm the page remains full-bleed in both
  (the sidebar width differs, but the canvas itself isn't padded either
  way).

---

### Task 6: Docs

**Files:**
- Modify: `README.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add the README section**

In `README.md`, immediately after the "Phase 4 Planetarium API" section
and before "## Project Layout", add:

```markdown
## Phase 4 Planetarium Visualization

`/planetarium` renders each concept as a low-poly faceted sphere
(React Three Fiber + `@react-three/drei`), positioned by the Planetarium
Engine's UMAP projection and colored/sized by its computed
mass/visual_class. Orbit the scene with the mouse
(`OrbitControls`), click a node to jump to its concept detail page, or hit
Rebuild to trigger a fresh projection and watch it complete (same
job-polling pattern used elsewhere in the app). This is the first
full-bleed page in the app — `AppChrome` skips its usual content padding
for this one route.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document the Planetarium Visualization"
```

---

## Final Verification

- [ ] Run the full frontend suite: `cd frontend && npx vitest run && npx tsc --noEmit`
- [ ] Run the full backend suite (unaffected by this plan, but confirm no accidental breakage): `pytest -q`
- [ ] Manually smoke-test `/planetarium` in both Hearth and Meridian mode per Task 5 Step 7.
