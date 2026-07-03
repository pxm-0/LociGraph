# Multi-File Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Import page accept and upload multiple files in one action, with per-file type detection, sequential upload, live per-row status, and a progress bar.

**Architecture:** Frontend-only. No backend, API, or database changes — the existing single-file `POST /sources/upload` endpoint and `uploadSource(sourceType, file)` client function are reused unmodified, called once per file from a client-side sequential loop in `import-form.tsx`.

**Tech Stack:** Next.js / React / TypeScript, Vitest + Testing Library (existing conventions in `frontend/src/app/(app)/import/import-form.test.tsx`).

## Global Constraints

- No changes to `backend/app/api/sources.py` or `frontend/src/lib/api.ts`'s `uploadSource` signature — both are reused exactly as they are today.
- Uploads run sequentially, never `Promise.all` / concurrent — see spec's "Out of Scope" (simpler progress reporting, avoids bursting the job queue).
- Preserve the accepted `DESIGN.md` Hearth/Meridian visual language; the progress bar reuses the "2px amber progress bar" pattern already described there for background job panels.
- Spec: `docs/superpowers/specs/2026-07-03-multi-file-upload-design.md` — read it first for full rationale; this plan implements it as-is.

---

## Task Briefs

### Task 1: type detection + staged file list
- Add `detectSourceType(filename: string): SourceType | "ambiguous"` to `frontend/src/lib/types.ts`. Maps extension → type: `.md` → `markdown`, `.html` → `html`, `.pdf` → `pdf`, `.zip` → `chatgpt`. `.json` and any unrecognized extension → `"ambiguous"`. Case-insensitive on the extension.
- In `frontend/src/app/(app)/import/import-form.tsx`:
  - Replace the `file: File | null` state with a `StagedFile[]` list:
    ```ts
    interface StagedFile {
      id: string
      file: File
      sourceType: SourceType
      status: "pending" | "uploading" | "done" | "duplicate" | "error"
      error?: string
      sourceId?: string
    }
    ```
    (`id` via `crypto.randomUUID()`.)
  - Add `multiple` to the hidden `<input type="file">`.
  - `handleFileChange`/`onInputChange`/`onDrop` **append** newly selected/dropped files to the existing staged list (don't replace it) — for each new `File`, call `detectSourceType`, defaulting `"ambiguous"` to `json`, and push a new `StagedFile` with `status: "pending"`.
  - Render the staged list below the drop zone: one row per file — filename, a `<select>` bound to `sourceType` (always editable, using the existing `SOURCE_TYPES`/`FORMAT_META` options, not just for ambiguous ones), a status indicator, and a remove button (`disabled` unless `status === "pending"`) that filters the row out of state.
  - The existing single-file "Import File" submit button becomes "Upload All", disabled when there are zero rows with `status === "pending"` (not just zero rows total, so it stays disabled mid-upload).
- No upload logic yet — this task only builds and tests the staging UI.

**Tests** (`frontend/src/app/(app)/import/import-form.test.tsx`):
- One assertion per extension case for `detectSourceType`: `.md`→markdown, `.html`→html, `.pdf`→pdf, `.zip`→chatgpt, `.json`→ambiguous, `.xyz`→ambiguous.
- Selecting 2 files via the file input renders 2 staged rows with the correct pre-filled types (including a `.json` file defaulting its dropdown to `json` while remaining editable).
- Dropping an additional file after an initial selection results in 3 staged rows total (append, not replace).
- Clicking a row's remove button while `status === "pending"` removes only that row.
- "Upload All" is disabled when the staged list is empty.

---

### Task 2: sequential upload, error handling, progress bar
- In `import-form.tsx`, wire "Upload All" to walk the staged list's `"pending"` rows **sequentially** (a `for` loop with `await`, not `Promise.all`):
  1. Set that row's `status` to `"uploading"`.
  2. Call the existing `uploadSource(row.sourceType, row.file)` (already imported from `@/lib/api`; signature unchanged).
  3. On success: set `status: "done"`, `sourceId: result.sourceId`.
  4. On `ApiError` with `status === 409`: set `status: "duplicate"`, `error: "Duplicate source (already imported)."` (or the server's message if more specific — check `ApiError`'s shape in `frontend/src/lib/api.ts` for what's available).
  5. On `ApiError` with `status === 401`: stop the loop immediately without touching any remaining `"pending"` rows, and set a page-level error state (reuse the existing `error`/`setError` pattern already in this file) to something like `"Session expired — please sign in again."` Do not mark remaining rows `"error"`.
  6. On any other error (including non-`ApiError` exceptions): set `status: "error"`, `error: err instanceof Error ? err.message : "Upload failed."`, and continue to the next row.
- Add a progress bar above the staged list, visible once uploading has started (i.e. at least one row is or has been `"uploading"`/terminal): a 2px-tall bar using the accent color (`bg-ember`, matching the existing single-file page's ember usage — see `DESIGN.md`'s Meridian job-queue-panel spec for the "2px amber progress bar" precedent), width `${(settledCount / totalCount) * 100}%` where `settledCount` is the count of rows with `status` in `("done", "duplicate", "error")` and `totalCount` is the full staged list length. A text line above it reads `"{settledCount} of {totalCount} uploaded"` while `settledCount < totalCount`, and a final summary once `settledCount === totalCount`: `"{doneCount} uploaded, {duplicateCount} duplicate, {errorCount} failed"` (omit any clause whose count is 0).

**Tests** (`frontend/src/app/(app)/import/import-form.test.tsx`, extending Task 1's fixtures):
- "Upload All" with 3 staged files calls the mocked `uploadSource` exactly 3 times, in the same order the files were staged, each with that row's `sourceType`.
- A `409` `ApiError` on the second of three files marks that row `"duplicate"` and still uploads the third file (i.e. `uploadSource` is called 3 times, not 2).
- A `401` `ApiError` on the first of three files stops the loop: `uploadSource` is called exactly once, the remaining two rows stay `"pending"`, and one page-level error message is shown (not per-row).
- After all rows settle, the summary text matches counts, e.g. 2 done + 1 duplicate → `"2 uploaded, 1 duplicate"`.
- The progress bar's inline width style reflects `settledCount / totalCount` at each step (e.g. assert the style/attribute after the first of three resolves, then after all three).

---

### Task 3: docs, review, publish
- No README changes needed — the current README has no section documenting the import UI's specifics (checked: only high-level architecture/phase sections exist), so there's nothing established to update for a UI-only change.
- Run frontend gates: `npx tsc --noEmit`, `npx eslint .`, `npx vitest run` (from `frontend/`) — all must pass clean.
- Browser QA via the running dev server or docker stack: stage 3+ files of different types (including a `.json` file to confirm the ambiguous-default-editable behavior), remove one before uploading, click "Upload All", confirm the progress bar fills and the summary line matches what actually happened; re-upload one already-imported file in a batch to confirm it shows `"duplicate"` while the rest still succeed.
- Commit. Do not push or open a PR — that's the controller's/human's call, same convention as prior plans in this repo.

## Out of Scope
(carried over from the spec, unchanged)
- Any backend/API changes.
- Parallel/concurrent uploads.
- A full manual per-file type picker with no auto-detection.
