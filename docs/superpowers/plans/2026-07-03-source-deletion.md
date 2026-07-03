# Phase 1 - Source Deletion (Before Extraction)

## Summary
Let a source be deleted once it has zero claims — i.e. before extraction
has produced anything from it. Once claims exist, deletion is blocked
(409) rather than cascading, to avoid orphaning downstream claims/concepts
data. Adds `SourceRepository.purge`, a `delete_raw` storage helper, a
`POST /sources/{source_id}/purge` endpoint, and a Delete button on
`SourceRow`. Spec: `docs/superpowers/specs/2026-07-03-source-deletion-design.md`.

## Task Briefs

### Task 1: repository + storage helper
- Add `delete_raw(path: str) -> None` to `kernel/storage.py`, mirroring
  the existing `save_raw`: removes the file at `path` if present
  (`Path(path).unlink(missing_ok=True)` — must not raise if the file is
  already gone or was never written).
- Add `purge(source_id: str | UUID) -> bool` to `kernel/db/sources.py`'s
  `SourceRepository`: `UPDATE sources SET import_status = 'PURGED',
  purged_at = now(), raw_storage_path = NULL WHERE id = :id RETURNING
  id`, matching this file's existing `_COLUMNS`/`text()`/`.mappings()`
  style. Returns `True` if a row was updated, `False` if not found (RLS
  already scopes visibility, same as every other method here — no
  explicit `user_id` filter needed beyond what RLS enforces).
- Tests: `delete_raw` removes an existing file and is a silent no-op on a
  missing path (both need a real temp file/dir, not a mock — this is a
  filesystem operation). `SourceRepository.purge` transitions a real
  source's status/purged_at/raw_storage_path correctly against the real
  dockerized Postgres, returns `False` for a nonexistent id, and (mirror
  the tenant-isolation pattern already used throughout this codebase,
  e.g. `tests/kernel/test_tenant_isolation.py`) returns `False` — not an
  error, RLS makes the row invisible — when called against another
  tenant's source id.

### Task 2: API
- Add `POST /sources/{source_id}/purge` to `backend/app/api/sources.py`:
  - 404 if `SourceRepository.get(source_id)` returns `None`.
  - 409 if `ClaimRepository.count_for_source(source_id) > 0`, with
    `detail="source has claims — cannot delete after extraction"`.
  - Otherwise: if `source.raw_storage_path` is set, call
    `delete_raw(source.raw_storage_path)`; then call
    `SourceRepository(conn).purge(source_id)`; return
    `{"status": "purged"}`.
- Tests (`tests/backend/test_sources_api.py`, following its existing
  `client`/`seeded_user` HTTP-level conventions): purging a
  zero-claim source returns 200 and the source's subsequent `GET
  /sources/{id}` shows `import_status: "PURGED"`; purging a source with
  at least one claim returns 409 and the source is unchanged; purging a
  nonexistent/foreign source id returns 404; purging removes the raw file
  from disk (assert the file no longer exists at the path returned by
  the earlier upload, using the same `RAW_STORAGE_PATH` test fixture
  pattern already used by the upload tests in this file).

### Task 3: frontend
- Add `purgeSource(sourceId: string): Promise<void>` to
  `frontend/src/lib/api.ts`, following the existing `extractClaims`-style
  POST-with-no-body pattern (`readError`/`ApiError` conventions
  unchanged).
- Add a "Delete" button to `frontend/src/components/domain/SourceRow.tsx`
  (ghost variant, placed after the existing Extract/Retry button),
  enabled only when `source.claimCount === 0 && source.importStatus !==
  "PURGED"`. On click: `window.confirm(...)` first (a destructive action
  needs a confirmation step; skip building a custom modal component for
  this — `window.confirm` is sufficient for a single-user local tool),
  then call `purgeSource`, then trigger the list refresh already used by
  `sources/page.tsx` for the extract flow. A `409` from a race (claims
  landed between page load and click) surfaces via the page's existing
  error-banner state, not a silent failure.
- Tests (`frontend/src/app/(app)/sources/sources.test.tsx`, extending its
  existing conventions): Delete button is disabled when `claimCount > 0`
  or status is already `PURGED`; clicking Delete without confirming
  (mock `window.confirm` returning `false`) does not call `purgeSource`;
  confirming calls `purgeSource` and refreshes the list; a `409` response
  shows the error banner without navigating away or crashing.

### Task 4: docs, review, publish
- No README changes needed (same reasoning as the multi-file-upload
  plan — no existing section documents per-row source actions in enough
  detail to need updating for one more button).
- Run backend/frontend gates: `pytest -q`, `ruff check backend kernel
  tests`, `mypy backend kernel`, and from `frontend/`: `npx tsc --noEmit`,
  `npx eslint .`, `npx vitest run`.
- Browser QA: upload a source, confirm Delete is enabled and purging it
  updates the row to `PURGED` with strikethrough; extract claims from a
  different source, confirm Delete becomes disabled once claims exist;
  attempt a purge via a stale/cached page state on a since-extracted
  source to confirm the 409 path surfaces cleanly.
- Commit. Do not push or open a PR — that decision is made once this
  plan's branch is ready to fold into the parallel work happening
  alongside it (see the top-level goal's "keep them in separate branches
  ... try to make them not hinder one another").

## Out of Scope
(carried over from the spec, unchanged)
- Cascade-delete of a source that already has claims.
- Undo/trash/restore.
- Bulk delete.
- A general automated retention/purge job (Phase 0's originally-deferred
  concept) — this is a direct, user-triggered action only.
