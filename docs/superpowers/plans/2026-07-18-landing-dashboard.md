# Landing Page + Dashboard Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public cosmos-forward landing page at `/` and rework `/dashboard` into a substantial overview, backed by a new `/dashboard/trends` endpoint.

**Architecture:** Backend gains one read-only trends endpoint (RLS-scoped daily buckets). Frontend adds a landing route (auth-branched) with a capped R3F starfield hero + story scroll, and replaces the thin dashboard with a widget grid that reuses existing primitives and the planetarium scene (capped). No new runtime deps.

**Tech Stack:** Next.js 14 App Router, React 18, TypeScript, Tailwind, React-Three-Fiber, FastAPI, SQLAlchemy Core, Postgres, Vitest + Testing Library, Playwright, pytest.

## Global Constraints

- Landing commits to a single dark cosmic look (Meridian tokens); it does NOT respond to the app theme toggle.
- Dashboard must render in BOTH Hearth and Meridian modes.
- Secondary 3D surfaces (hero, dashboard mini-planetarium) are capped & calm: reduced node count, no `OrbitControls`, slow/no motion; lazy-loaded via `next/dynamic` so non-3D content paints first. The full `/planetarium` stays the only unbounded 3D view.
- Reuse existing primitives (`Card`, `Button`, `Badge`, `StatusBadge`, `StatCard`, `PlanetariumScene`/`PlanetNode`, `api.ts`, theme tokens). No new npm dependencies.
- Single-password auth model unchanged; the landing's only CTA is "Enter" → `/login`.
- TDD where logic exists; commit per task.

---

## File Structure

**Backend**
- Modify `kernel/db/sources.py`, `kernel/db/claims.py`, `kernel/db/concepts.py`, `kernel/db/contradictions.py` — add `counts_by_day(since)`.
- Modify `backend/app/api/dashboard.py` — add `GET /dashboard/trends`.
- Modify `tests/backend/test_dashboard_api.py` — trends tests.
- Create `tests/kernel/test_dashboard_trends.py` — `counts_by_day` tests.

**Frontend — landing**
- Create `frontend/src/lib/demoGraph.ts` — synthetic planetarium nodes.
- Modify `frontend/src/app/page.tsx` — auth branch → Landing / dashboard.
- Create `frontend/src/components/landing/{Landing,HeroStarfield,StoryBeat,EnterCta}.tsx`.
- Create `frontend/src/test/e2e/landing.spec.ts`.

**Frontend — dashboard**
- Create `frontend/src/lib/dashboard.ts` — aggregator + trends client + zero-fill types.
- Create `frontend/src/components/dashboard/{DashboardGrid,MiniPlanetarium,NeedsAttention,Sparkline,RecentActivity,CustodianCard}.tsx`.
- Create `frontend/src/components/planetarium/CappedStarfield.tsx` — shared capped/calm scene for hero + mini.
- Modify `frontend/src/app/(app)/dashboard/page.tsx` — render `DashboardGrid`.
- Create co-located `*.test.tsx` for widgets with logic.

**Frontend — API client**
- Modify `frontend/src/lib/api.ts` + `frontend/src/lib/types.ts` — `getDashboardTrends`, trend types.

---

## Phase 1 — Backend trends

### Task 1: `counts_by_day` repository method

**Files:**
- Modify: `kernel/db/sources.py`, `kernel/db/claims.py`, `kernel/db/concepts.py`, `kernel/db/contradictions.py`
- Test: `tests/kernel/test_dashboard_trends.py` (create)

**Interfaces:**
- Produces: `async def counts_by_day(self, since: datetime) -> list[tuple[date, int]]` on each of the four repos. Returns rows `(day, count)` ascending, only non-empty days (zero-fill happens in the API layer).

- [ ] **Step 1: Write failing test** (`tests/kernel/test_dashboard_trends.py`): seed a user, insert 2 sources today + 1 yesterday (set `created_at` explicitly), assert `SourceRepository(conn).counts_by_day(now-7d)` returns `[(yesterday, 1), (today, 2)]`. Repeat one case per repo. Run under `session(user_id)`.
- [ ] **Step 2: Run** `pytest tests/kernel/test_dashboard_trends.py -v` → FAIL (method missing).
- [ ] **Step 3: Implement** on each repo:

```python
from datetime import date, datetime

async def counts_by_day(self, since: datetime) -> list[tuple[date, int]]:
    rows = (
        await self.conn.execute(
            text(
                "SELECT date_trunc('day', created_at)::date AS d, count(*) AS c "
                "FROM sources WHERE created_at >= :since GROUP BY d ORDER BY d"
            ),
            {"since": since},
        )
    ).all()
    return [(r[0], int(r[1])) for r in rows]
```
(Swap the table name per repo: `sources`, `claims`, `concepts`, `contradictions`.)
- [ ] **Step 4: Run** the test → PASS.
- [ ] **Step 5: Commit** `feat: add counts_by_day to dashboard repos`.

### Task 2: `GET /dashboard/trends`

**Files:**
- Modify: `backend/app/api/dashboard.py`
- Test: `tests/backend/test_dashboard_api.py`

**Interfaces:**
- Consumes: `counts_by_day` (Task 1).
- Produces: `GET /dashboard/trends?window=<int>` → `{"window_days": int, "series": {"sources": [{"date": "YYYY-MM-DD", "count": int}], "claims": [...], "concepts": [...], "contradictions": [...]}}`. `window` defaults to 30, clamped to `[1, 365]`. Every day in `[today-window+1, today]` present, zero-filled, ascending.

- [ ] **Step 1: Write failing test** in `test_dashboard_api.py`: seed data across a couple days; `GET /dashboard/trends?window=7`; assert 7 entries per series, dates contiguous ascending, counts match seeds, empty days are 0. Add a tenant-isolation assertion (a second user's rows excluded). Add a default-window test (`len == 30`).
- [ ] **Step 2: Run** `pytest tests/backend/test_dashboard_api.py -k trends -v` → FAIL (404).
- [ ] **Step 3: Implement** endpoint (mirror `dashboard_summary`'s auth dep + `session`):

```python
from datetime import date, datetime, timedelta, timezone

@router.get("/dashboard/trends")
async def dashboard_trends(window: int = 30, user_id: str = Depends(current_user_id)):
    window = max(1, min(window, 365))
    since = datetime.now(timezone.utc) - timedelta(days=window - 1)
    start_day = since.date()
    days = [start_day + timedelta(days=i) for i in range(window)]
    async with session(user_id) as conn:
        repos = {
            "sources": SourceRepository(conn),
            "claims": ClaimRepository(conn),
            "concepts": ConceptRepository(conn),
            "contradictions": ContradictionRepository(conn),
        }
        series = {}
        for name, repo in repos.items():
            found = dict(await repo.counts_by_day(since))
            series[name] = [
                {"date": d.isoformat(), "count": found.get(d, 0)} for d in days
            ]
    return {"window_days": window, "series": series}
```
(Match the exact auth dependency + repo import names already used in `dashboard.py`.)
- [ ] **Step 4: Run** trends tests → PASS. Then full `pytest tests/backend/test_dashboard_api.py -v`.
- [ ] **Step 5: Commit** `feat: add /dashboard/trends endpoint`.

---

## Phase 2 — Landing

### Task 3: demo graph fixture

**Files:** Create `frontend/src/lib/demoGraph.ts`; Test `frontend/src/lib/demoGraph.test.ts`

**Interfaces:**
- Produces: `export const DEMO_NODES: PlanetariumNode[]` (~40 items, matching `PlanetariumNode` in `src/lib/types.ts`): synthetic `id`, plausible concept `label`, spread `x/y/z`, varied `mass`/`brightness`, a handful `visualClass: "black_hole"` and the rest `"planet"`. No real archive data.

- [ ] **Step 1: Test** — assert `DEMO_NODES.length >= 30`, every node satisfies the `PlanetariumNode` shape (keys present, numeric coords), and at least 2 are `black_hole`.
- [ ] **Step 2: Run** `npx vitest run src/lib/demoGraph.test.ts` → FAIL.
- [ ] **Step 3: Implement** the fixture (hand-authored array; deterministic coords, no `Math.random` at import).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: add synthetic demo graph for landing hero`.

### Task 4: landing route + static composition

**Files:**
- Modify `frontend/src/app/page.tsx`
- Create `frontend/src/components/landing/{Landing,StoryBeat,EnterCta}.tsx`

**Interfaces:**
- Consumes: `me()` from `api.ts`.
- Produces: `<Landing/>` default export (composition); `<StoryBeat heading title body imageSrc?>`; `<EnterCta/>` (link to `/login`, styled button).

- [ ] **Step 1:** Rewrite `page.tsx` as a client component: on mount call `me()`; if authed `router.replace('/dashboard')`; else render `<Landing/>`. Render `<Landing/>` immediately (no login-flash); only redirect on confirmed auth. Wrap body in a fixed `data-mode="meridian"` container so landing uses dark tokens regardless of stored theme.
- [ ] **Step 2:** `Landing.tsx` composes: `<HeroStarfield/>` placeholder (real in Task 5) + hero overlay copy + 4 `<StoryBeat/>` (Capture / Distill / Reconcile / Explore, copy from spec) + closing `<EnterCta/>` footer. Use `font-heading`, muted Meridian tokens.
- [ ] **Step 3:** `EnterCta.tsx` = `Button` variant primary wrapped in `next/link` → `/login`. `StoryBeat.tsx` = heading + one-line body + optional screenshot `<img>`.
- [ ] **Step 4:** Manual check: `npm run dev`, visit `/` logged out → landing renders dark; logged in → redirects to `/dashboard`. (Browser verification in Task 13.)
- [ ] **Step 5: Commit** `feat: landing page route + story scroll`.

### Task 5: hero starfield (capped R3F)

**Files:** Create `frontend/src/components/planetarium/CappedStarfield.tsx`, `frontend/src/components/landing/HeroStarfield.tsx`; modify `Landing.tsx`

**Interfaces:**
- Consumes: `DEMO_NODES` (Task 3), `PlanetNode`.
- Produces:
  - `<CappedStarfield nodes={PlanetariumNode[]} drift?: boolean />` — a self-contained `<Canvas>` rendering `PlanetNode`s, no `OrbitControls`, slow group auto-rotate via `useFrame` when `drift`. Shared by hero + mini (Task 12).
  - `<HeroStarfield/>` — full-bleed `<CappedStarfield nodes={DEMO_NODES} drift/>`, loaded via `next/dynamic({ ssr: false })`.

- [ ] **Step 1:** Implement `CappedStarfield` (own `<Canvas>`, do not modify the shared `PlanetariumScene`). Reuse `PlanetNode` for node rendering.
- [ ] **Step 2:** Implement `HeroStarfield` wrapping it; in `Landing.tsx` replace the placeholder with `const HeroStarfield = dynamic(() => import('./HeroStarfield'), { ssr: false })`.
- [ ] **Step 3: Test** (`CappedStarfield.test.tsx`): mock R3F (`vi.mock('@react-three/fiber')`) and assert it mounts with `DEMO_NODES` without throwing. (Headless WebGL out of scope; assert wiring.)
- [ ] **Step 4: Run** `npx vitest run src/components/landing src/components/planetarium/CappedStarfield.test.tsx` → PASS.
- [ ] **Step 5: Commit** `feat: live capped starfield hero`.

---

## Phase 3 — Dashboard data + widgets

### Task 6: trends client + dashboard aggregator

**Files:** Modify `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`; create `frontend/src/lib/dashboard.ts` + `dashboard.test.ts`

**Interfaces:**
- Produces:
  - `types.ts`: `interface TrendPoint { date: string; count: number }`, `interface DashboardTrends { window_days: number; series: Record<'sources'|'claims'|'concepts'|'contradictions', TrendPoint[]> }`.
  - `api.ts`: `getDashboardTrends(window?: number): Promise<DashboardTrends>` (GET `/api/dashboard/trends`, `credentials: 'include'`).
  - `dashboard.ts`: `deltaThisWeek(points: TrendPoint[]): number` (sum of last 7 counts); `loadDashboard(): Promise<DashboardData>` composing summary + trends + recent lists + jobs + candidates via `Promise.all`, returning a typed `DashboardData`.

- [ ] **Step 1: Test** `dashboard.test.ts`: `deltaThisWeek` sums the last 7 points (and handles <7). Mock `api` calls; assert `loadDashboard` returns merged shape.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the types, `getDashboardTrends`, `deltaThisWeek`, `loadDashboard`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: dashboard trends client + aggregator`.

### Task 7: NeedsAttention widget

**Files:** Create `frontend/src/components/dashboard/NeedsAttention.tsx` + test

**Interfaces:** Consumes counts (open contradictions, failed+in-flight jobs, unreviewed candidates). Produces `<NeedsAttention items={{contradictions,jobs,candidates}}>` — a row of `Card`s, each a count + label + link to its route; "All clear" state when all zero.

- [ ] **Step 1: Test:** given nonzero counts renders the numbers + correct hrefs; given all-zero renders an "All clear" state.
- [ ] **Step 2: Run** → FAIL. **Step 3:** implement with `Card`/`Badge`/`StatusBadge` + `next/link`. **Step 4:** PASS. **Step 5: Commit** `feat: dashboard needs-attention strip`.

### Task 8: Sparkline + contextual stat tiles

**Files:** Create `frontend/src/components/dashboard/Sparkline.tsx` + test; the tiles row lives in `DashboardGrid` (Task 11).

**Interfaces:** Produces `<Sparkline points={TrendPoint[]} />` — a pure inline-SVG polyline scaled to min/max, `currentColor`, no deps, `aria-hidden`. Exports `sparklinePath(points, w, h): string` for testability.

- [ ] **Step 1: Test:** `sparklinePath` maps N points to N SVG coords within bounds; flat series → horizontal line; empty → empty path.
- [ ] **Step 2:** FAIL. **Step 3:** implement path math + component. **Step 4:** PASS. **Step 5: Commit** `feat: sparkline component`.

### Task 9: RecentActivity widget

**Files:** Create `frontend/src/components/dashboard/RecentActivity.tsx` + test

**Interfaces:** Produces `<RecentActivity items={ActivityItem[]}>`; `ActivityItem = {kind:'source'|'claim'|'contradiction'; label:string; at:string; href:string}`. Merge + sort-desc-by-`at` via a pure helper `mergeActivity(...)` here (unit-tested), capped at 8.

- [ ] **Step 1: Test:** `mergeActivity` interleaves and sorts by `at` desc, caps at 8. **Step 2:** FAIL. **Step 3:** implement helper + list UI (icon per kind via existing `NavIcon`). **Step 4:** PASS. **Step 5: Commit** `feat: dashboard recent activity`.

### Task 10: CustodianCard

**Files:** Create `frontend/src/components/dashboard/CustodianCard.tsx` + test

**Interfaces:** Produces `<CustodianCard pendingProposals={number} onAsk={() => void}>` — shows pending-proposal count (or "no open proposals") + an "Ask the Custodian" button. Reuse the existing Custodian open mechanism (inspect `Orb.tsx`/`CustodianPanel.tsx`; if the open state is local, lift/expose via the existing context — do NOT fork the panel).

- [ ] **Step 1: Test:** renders count; button fires `onAsk`. **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS. **Step 5: Commit** `feat: dashboard custodian card`.

### Task 11: DashboardGrid + page swap

**Files:** Create `frontend/src/components/dashboard/DashboardGrid.tsx`; modify `frontend/src/app/(app)/dashboard/page.tsx`

**Interfaces:** Consumes `loadDashboard()` (Task 6) + all widgets. Produces `<DashboardGrid data={DashboardData}>` laying out: heading, NeedsAttention strip, stat tiles (each `StatCard` + `Sparkline` + `deltaThisWeek`), MiniPlanetarium slot (Task 12), RecentActivity, CustodianCard. Responsive grid; verified in both modes.

- [ ] **Step 1:** Build `DashboardGrid` composing widgets; keep the existing loading skeleton + error patterns from the current page.
- [ ] **Step 2:** Rewrite `dashboard/page.tsx` to call `loadDashboard()` and render `<DashboardGrid/>` (replacing tiles+table).
- [ ] **Step 3: Test:** `DashboardGrid.test.tsx` renders with a mocked `DashboardData`, shows tiles, activity, needs-attention.
- [ ] **Step 4: Run** `npx vitest run src/components/dashboard` → PASS.
- [ ] **Step 5: Commit** `feat: dashboard grid overview`.

---

## Phase 4 — Mini-planetarium

### Task 12: MiniPlanetarium panel

**Files:** Create `frontend/src/components/dashboard/MiniPlanetarium.tsx`; wire into `DashboardGrid`

**Interfaces:** Consumes `listPlanetariumNodes()` + `CappedStarfield` (Task 5). Produces `<MiniPlanetarium/>` — fetches nodes, caps to top ~40 by `mass`, renders `<CappedStarfield nodes drift/>`, lazy-loaded via `next/dynamic`, links to `/planetarium`. Empty state when no nodes.

- [ ] **Step 1:** Implement using the shared `CappedStarfield` from Task 5.
- [ ] **Step 2:** Wire into `DashboardGrid` via `next/dynamic`.
- [ ] **Step 3: Test:** mounts with mocked nodes (R3F mocked) + empty state.
- [ ] **Step 4: Run** vitest → PASS.
- [ ] **Step 5: Commit** `feat: dashboard mini-planetarium`.

---

## Phase 5 — Verification

### Task 13: e2e smoke + both-theme check

**Files:** Create `frontend/src/test/e2e/landing.spec.ts`

- [ ] **Step 1:** Playwright: unauth `/` shows hero + "Enter" linking `/login`; authed context `/` redirects `/dashboard`.
- [ ] **Step 2:** Run the project's e2e command → PASS.
- [ ] **Step 3:** Browser: dashboard in Hearth AND Meridian (toggle) — no broken layout; landing dark. (Use the browser preview tools.)
- [ ] **Step 4:** Run full suites: `npx vitest run`, `pytest`, and `next build` (catches type/RSC errors).
- [ ] **Step 5: Commit** `test: landing/dashboard e2e + verification`.

---

## Self-Review

- **Spec coverage:** landing route/hero/story/look → Tasks 3–5; dashboard widgets → Tasks 6–12; `/dashboard/trends` → Tasks 1–2; perf caps → Tasks 5/12 (`CappedStarfield`, dynamic import); testing → per-task + Task 13. All spec sections mapped.
- **Types:** `TrendPoint`/`DashboardTrends` defined Task 6 and consumed consistently (Tasks 8, 11); `counts_by_day` signature stable Tasks 1→2; `CappedStarfield` signature stable Tasks 5→12; `PlanetariumNode` reused from existing `types.ts`.
- **No placeholders:** logic-heavy steps carry real code (queries, zero-fill, path math, auth branch); presentational components specify exact props/tests. `CappedStarfield` extracted to keep hero + mini DRY.
