# Multi-File Upload — Design

## Summary
Let the Import page accept multiple files in one action instead of exactly
one. Frontend-only change: no backend, API, or database changes. The
existing single-file `POST /sources/upload` endpoint is reused unmodified,
called once per file from a client-side loop.

## Background
Today, `import-form.tsx` holds a single `File | null` and one global
"Source Type" dropdown that applies to that one file. The hidden
`<input type="file">` has no `multiple` attribute. `uploadSource(sourceType,
file)` in `frontend/src/lib/api.ts` posts one file per call to
`POST /sources/upload`, which enforces per-user checksum de-duplication
before writing to disk.

## Design

### Type detection
A new `detectSourceType(filename): SourceType | "ambiguous"` helper in
`frontend/src/lib/types.ts` maps file extension to source type:
- `.md` → `markdown`
- `.html` → `html`
- `.pdf` → `pdf`
- `.zip` → `chatgpt`
- `.json` → `"ambiguous"` (could be `json` or `meta` export — both use
  `.json`)

Unrecognized extensions default to `"ambiguous"` too, so the UI always has
something sensible to pre-select and let the user override, rather than
failing to stage the file at all.

### Staged upload list
`import-form.tsx` replaces its single `file` state with a list of staged
rows:

```ts
interface StagedFile {
  id: string                 // crypto.randomUUID(), for React keys + updates
  file: File
  sourceType: SourceType
  status: "pending" | "uploading" | "done" | "duplicate" | "error"
  error?: string              // set when status is "duplicate" or "error"
  sourceId?: string           // set when status is "done"
}
```

- The file input gains `multiple`. Selecting or dropping files **appends**
  to the staged list rather than replacing it, so multiple drop actions
  accumulate.
- Each newly-added file gets `sourceType` pre-filled via
  `detectSourceType`; `"ambiguous"` results default to `json` but every
  row's dropdown is always editable, not just ambiguous ones.
- The staged list renders as rows: filename, editable type dropdown, a
  status indicator, and a remove button (only enabled while `status ===
  "pending"`).
- An "Upload All" button is disabled when there are no pending rows or an
  upload is already in flight.

### Upload sequencing
On "Upload All", walk the pending rows **sequentially** (not
`Promise.all`):

1. Mark the row `"uploading"`.
2. Call the existing `uploadSource(row.sourceType, row.file)`.
3. On success: mark `"done"`, store `sourceId`.
4. On `ApiError` with `status === 409`: mark `"duplicate"`, store the
   error message.
5. On `ApiError` with `status === 401`: stop the loop immediately (don't
   touch remaining pending rows) and show one page-level error banner —
   a dead session will 401 on every subsequent call too, so retrying
   per-row would just repeat the same error N times.
6. On any other error: mark `"error"`, store the message, continue to the
   next row.

### Progress bar
A 2px accent-colored progress bar sits above the staged list once upload
starts, matching the existing "2px amber progress bar" pattern already
used for background job panels in `DESIGN.md`'s Meridian screen spec. It
fills based on `(done + duplicate + error) / total` staged rows. A text
line above it reads e.g. "3 of 5 uploaded" while in progress, and a
final summary once complete: "3 uploaded, 1 duplicate, 1 failed."

### What doesn't change
- `backend/app/api/sources.py`'s `upload_source` endpoint — untouched.
- `frontend/src/lib/api.ts`'s `uploadSource` signature — untouched, called
  once per file exactly as it is today.
- The per-format cards section and drop-zone visuals lower on the page —
  untouched.

## Testing
Extend `frontend/src/app/(app)/import/import-form.test.tsx`:
- Selecting multiple files populates the staged list with correct
  auto-detected types (one assertion per extension case, including the
  `.json` → ambiguous → defaults-to-`json`-but-editable case).
- Dropping additional files appends to, rather than replaces, the
  existing staged list.
- "Upload All" calls `uploadSource` once per pending row, in order.
- A `409` on one row marks it `"duplicate"` and continues uploading the
  remaining rows.
- A `401` on one row stops the loop, leaves remaining rows `"pending"`,
  and shows one error banner (not per-row).
- The progress bar's fill percentage and the "X of N" text update as
  each row resolves.

## Out of Scope
- Any backend/API changes — this is purely a frontend batching UX over
  the existing single-file endpoint.
- Parallel/concurrent uploads (explicitly rejected in favor of sequential,
  for simpler progress reporting and to avoid bursting the job queue).
- A full manual per-file type picker with no auto-detection — auto-detect
  covers the common cases; only truly ambiguous/unrecognized extensions
  need a manual look.
