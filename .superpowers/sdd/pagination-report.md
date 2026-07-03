# Pagination report: Claims and Observations pages

## What was built

Added "Load more" pagination to both list pages using the pagination the backend
and `frontend/src/lib/api.ts` already supported. No backend or `api.ts` changes.

### Claims page (`frontend/src/app/(app)/claims/page.tsx`)

- Added `PAGE_SIZE = 100` constant.
- Added `hasMore` (starts `true`) and `loadingMore` (starts `false`) state alongside
  the existing `claims` state.
- Initial `useEffect` now calls `listClaims({ limit: PAGE_SIZE, offset: 0 })` and sets
  `hasMore = data.length === PAGE_SIZE` on success.
- Added `loadMore()`: guards on `!loadingMore && hasMore && claims !== null`, fetches
  `listClaims({ limit: PAGE_SIZE, offset: claims.length })`, appends to `claims` via
  `setClaims((prev) => [...(prev ?? []), ...data])`, updates `hasMore`, and always
  resets `loadingMore` in a `finally`. Errors reuse the existing `error` state.
- Rendered a "Load more" button below the claims list, visible when
  `hasMore && claims !== null && error === null`, disabled while `loadingMore`
  ("Loading…" vs "Load more" text).
- Left client-side `claimType`/`query` filtering untouched — it still filters only
  what's currently loaded (pre-existing, acceptable limitation, out of scope to fix).
- Claim-count badge still shows `claims.length` (count of loaded claims, not a
  server-side total).

### Observations page (`frontend/src/app/(app)/observations/page.tsx`)

- Added the same `PAGE_SIZE`, `hasMore`, `loadingMore` state.
- `fetchObservations` (the existing filter-triggered fetch, called from the
  `useEffect` keyed on `[activeSource, activeSpeaker, activeStatus, fetchObservations]`)
  now always requests `{ ...filters, limit: PAGE_SIZE, offset: 0 }` and sets `hasMore`
  from the response length. Because this fetch already re-runs whenever
  `activeSource`/`activeSpeaker`/`activeStatus` change (i.e. on "Apply"), pagination
  naturally resets to a fresh page 0 whenever filters change.
- Added `loadMore` as a `useCallback` depending on
  `[activeSource, activeSpeaker, activeStatus, hasMore, loadingMore, observations]` —
  mirrors `fetchObservations`'s own dependency pattern so it always reads the current
  committed filters, not a stale closure. Fetches
  `{ ...activeFilters, limit: PAGE_SIZE, offset: observations.length }`, appends
  results, updates `hasMore`.
- Rendered the same "Load more" button (same visibility/disabled/label rules) after
  the observations `.map(...)` block, still inside the
  `!isLoading && error === null && observations !== null` guard.

## Key decision: button styling

The task allowed picking between the Claims page's filter-pill style
(`font-mono text-xs uppercase tracking-widest`, unfilled) and the Observations page's
"Apply" button style (`rounded-meridian bg-ember px-4 py-1.5 font-mono text-xs
uppercase tracking-widest text-void transition-colors hover:opacity-90`, filled).

Chose the **filled "Apply" button style** for both pages' "Load more" buttons:
- It's already a real, working button element in this codebase (not a toggle/pill),
  so its states map cleanly onto Load more's own button semantics.
- Using the identical class string on both pages keeps the new affordance visually
  consistent between the two list pages, even though the pages differ elsewhere.
- Added `disabled:opacity-50` on top of the existing classes for the loading state,
  since neither existing button style had a disabled treatment to copy.

## Self-reported concerns

- None blocking. The only wrinkle during implementation: my first pass at the
  Observations "Load more with filters" test forgot to queue a mock response for the
  Apply-triggered refetch (since `fetchObservations` re-runs via the existing
  `useEffect` on committed filter change), which surfaced as a `Cannot read
  properties of undefined (reading 'then')` failure. Fixed by queuing the mock
  before clicking Apply. This was a test bug, not a production code bug — worth
  flagging since it's an easy trap for future tests against this file's Apply flow.
- Client-side text/type filtering on the Claims page still only filters whatever is
  currently loaded (pages loaded via "Load more"). This is explicitly called out as
  acceptable/out-of-scope in the task, not something this change attempts to fix.

## Verification

All run from `frontend/`:

```
npx tsc --noEmit
```
Clean, no output.

```
npx eslint .
```
Clean, no output.

```
npx vitest run 'src/app/(app)/claims/claims.test.tsx' 'src/app/(app)/observations/observations.test.tsx'
```
```
 ✓ src/app/(app)/claims/claims.test.tsx  (5 tests) 742ms
 ✓ src/app/(app)/observations/observations.test.tsx  (9 tests) 2301ms

 Test Files  2 passed (2)
      Tests  14 passed (14)
```

```
npx vitest run
```
```
 Test Files  13 passed (13)
      Tests  82 passed (82)
```
