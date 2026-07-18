# Landing Page + Dashboard Redesign — Design

- **Date:** 2026-07-18
- **Status:** Direction approved; pending spec review
- **Topic:** Public landing page at `/` + a substantial dashboard rework

## Context

LociGraph is a single-user personal knowledge-graph engine: ingested exports
(e.g. ChatGPT) → observations → extracted claims → concepts → contradictions,
explored via a 3D "planetarium" concept map and a floating "Custodian" AI
assistant. Frontend: Next.js 14 App Router, Tailwind, two full design languages
(Hearth light / Meridian dark), React-Three-Fiber for the planetarium. Auth is a
single shared password, cookie-based.

Two gaps motivate this work:

1. **No landing page.** `/` (`src/app/page.tsx`) is a bare client redirect —
   authed → `/dashboard`, else → `/login`. An unauthenticated visitor lands on a
   password box with zero context about what LociGraph is.
2. **Underwhelming dashboard.** `/dashboard`
   (`src/app/(app)/dashboard/page.tsx`) is one screen: 6 stat tiles + a "recent
   ingestions" table. The distinctive features (planetarium, Custodian) never
   appear on it.

## Goals

- A landing page at `/` that explains and shows off LociGraph and offers a clean
  way in — tasteful, substance-first, no growth-hacky patterns.
- A dashboard that feels substantial and surfaces the signature features plus
  actionable state.
- Maximize reuse of existing components; keep new 3D surfaces perf-safe.

## Non-goals

- No multi-user / signup / marketing funnel — the single-password model stays.
- No redesign of other routes (import, sources, claims, concepts, etc.).
- No changes to the planetarium engine itself beyond adding a capped render mode.

## Audience & tone

"All of the above, not obnoxious": serves first-time visitors, peers, and the
owner at once. Confident, substance-first (let the real planetarium be the flex),
restrained motion.

## Confirmed decisions

- **Direction: Cosmos-forward.** The planetarium is the identity anchor for both
  surfaces.
- **Secondary 3D surfaces are capped & calm.** The landing hero and the dashboard
  planetarium use a reduced node count and slow/no interaction, tuned for smooth
  load. The full `/planetarium` remains the only unbounded 3D view.
- **Trends are in scope.** A new `/dashboard/trends` backend endpoint powers real
  sparklines (not just "new this week" deltas).
- **Landing commits to one dark cosmic look** (Meridian tokens), independent of
  the in-app Hearth/Meridian toggle — landing pages should not theme-flip.

## Landing page (`/`)

### Route behavior

`src/app/page.tsx` changes from "redirect both ways" to:

- On mount, check auth via `me()`.
- Authed → `router.replace('/dashboard')` (unchanged for the owner).
- Unauthed → render `<Landing/>` (previously this branch redirected to `/login`).

Login stays at `/login`. The landing renders by default so the target audience
sees no flash; only authed users redirect away. The landing's single primary CTA
is **"Enter"** → `/login`.

### Hero

- Full-bleed live R3F starfield reusing `PlanetariumScene` / `PlanetNode`, fed a
  **canned demo graph** (`src/lib/demoGraph.ts`, ~40 synthetic `PlanetariumNode`s
  matching `src/lib/types.ts`) — real archive data stays private.
- `OrbitControls` disabled; slow automatic drift; muted palette; capped node
  count.
- Overlay: product name, one-line value proposition, subtitle, "Enter" button,
  and a scroll cue.

### Story scroll (4 beats)

Each beat = short heading + one sentence + a real UI screenshot or snippet:

1. **Capture** — bring in exports / conversations.
2. **Distill** — claims and concepts extracted automatically.
3. **Reconcile** — contradictions surfaced across the archive.
4. **Explore** — the planetarium and the Custodian assistant.

Closes with a quiet "Enter" footer. Deliberately short — four beats, not a
brochure.

### Look

Fixed dark cosmic (Meridian tokens); does not respond to the app theme toggle.
Fonts and tokens reused from the existing design system.

### New components (`src/components/landing/`)

`Landing.tsx` (composition), `HeroStarfield.tsx` (R3F + demo graph),
`StoryBeat.tsx` (reusable beat), `EnterCta.tsx`.

## Dashboard (`/dashboard`)

Replace the single-column "tiles + table" with a purposeful overview grid. Must
render correctly in both Hearth and Meridian (chrome branches hard on mode).

### Widgets

1. **Live mini-planetarium** — `PlanetariumScene` on real `listPlanetariumNodes()`,
   capped (top N by mass) and calm; links to `/planetarium`.
2. **Needs-attention strip** — open contradictions, failed + in-flight jobs,
   unreviewed concept candidates. All existing endpoints; each links to its page.
3. **Stat tiles (kept, contextual)** — sources / observations / claims / concepts
   from `/dashboard/summary`, each annotated with a "new this week" delta derived
   from `/dashboard/trends`.
4. **Trends sparklines** — a small sparkline per entity from `/dashboard/trends`.
5. **Recent activity** — merged recent sources + claims + contradictions (existing
   list endpoints), replacing the lone ingestions table.
6. **Custodian card** — pending Custodian proposals awaiting review + a quick
   "ask" entry that opens the existing Custodian panel.

### Data

- Existing: `/dashboard/summary`; sources / claims / concepts / contradictions /
  jobs / concept-candidate list endpoints; `listPlanetariumNodes()`.
- New: `/dashboard/trends`.
- A dashboard aggregator in `src/lib/` composes the calls in parallel, mirroring
  the current `Promise.all` pattern in `dashboard/page.tsx`.

### New components (`src/components/dashboard/`)

`DashboardGrid.tsx`, `MiniPlanetarium.tsx`, `NeedsAttention.tsx`, `Sparkline.tsx`,
`RecentActivity.tsx`, `CustodianCard.tsx`. Reuse `StatCard`, `Card`, `Badge`,
`StatusBadge`.

## Backend: `/dashboard/trends`

- **Endpoint:** `GET /dashboard/trends?window=30` (days; default 30), added to
  `backend/app/api/dashboard.py` beside `dashboard_summary`, using the same auth
  dependency.
- **Response** — daily new-item counts per entity over the window, zero-filled so
  sparklines are continuous:
  ```json
  {
    "window_days": 30,
    "series": {
      "sources":        [{"date": "2026-06-19", "count": 3}, "..."],
      "claims":         ["..."],
      "concepts":       ["..."],
      "contradictions": ["..."]
    }
  }
  ```
- **Kernel:** add a `counts_by_day(since)` method to the sources / claims /
  concepts / contradictions repositories (or one shared helper), each running
  `SELECT date_trunc('day', created_at)::date AS d, count(*) FROM <table>
  WHERE created_at >= :since GROUP BY d ORDER BY d` under the RLS `session(user_id)`
  transaction. All four tables have `created_at TIMESTAMPTZ` and RLS enabled.
  Zero-fill missing days in Python.

## Perf

Both new 3D surfaces use a capped node count and disabled/slow interaction. Do not
mount an uncapped `<Canvas>` on either surface. Lazy-load the R3F bundle on both
via dynamic import so non-3D content paints first. (Planetarium perf is a known
open pain; this avoids worsening it on two more surfaces.)

## Testing

- **Vitest (frontend):** `HeroStarfield` renders with the demo graph; each
  dashboard widget renders with mocked data and its empty state; `NeedsAttention`
  reflects counts; the `src/lib` aggregator + trends zero-fill logic.
- **Backend:** extend `test_dashboard_api` for `/dashboard/trends` — bucketing,
  zero-fill, `window` param, and tenant isolation / RLS scoping.
- **Playwright smoke:** logged-out `/` renders the landing (hero present, "Enter"
  links to `/login`); logged-in `/` redirects to `/dashboard`.

## Scope / phasing (suggested build order)

1. Backend `/dashboard/trends` (endpoint + kernel `counts_by_day` + tests).
2. Landing (`page.tsx` auth branch, `demoGraph.ts`, hero, story beats) —
   greenfield, low risk.
3. Dashboard shell + non-3D widgets (needs-attention, stats + deltas, sparklines,
   recent activity, Custodian card).
4. Capped mini-planetarium panels on the hero and the dashboard.
5. Tests + both-theme verification + Playwright smoke.

## Open questions

None outstanding — direction and the two scope forks (3D fidelity, trends) are
settled.
