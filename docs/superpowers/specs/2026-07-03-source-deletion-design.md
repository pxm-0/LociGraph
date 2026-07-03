# Source Deletion — Design

## Summary
Let a source be deleted ("purged") before it has been extracted. Once claim
extraction has produced claims (and potentially concepts/edges downstream),
deleting the source would orphan that data, so deletion is blocked once
`claim_count > 0` — matching the app's own existing `PURGED` status and
`purged_at` column, which were defined in Phase 0 but never wired to an
endpoint.

## Design

### Rule
A source can be purged if and only if it currently has zero claims
(`claims.count_for_source(source_id) == 0`). This covers both "never
extracted" and "extraction ran but found nothing" — both are safe to
delete. Once even one claim exists, deletion is blocked with a 409 and a
clear message telling the user why (not silently ignored, not cascaded).

No cascade-delete option in this iteration — if you need to remove a
source that already has claims, that's out of scope here (see Out of
Scope).

### Backend
- `kernel/storage.py` gains `delete_raw(path: str) -> None`, mirroring the
  existing `save_raw` — removes the file at `path` if it exists
  (`Path(path).unlink(missing_ok=True)`), a no-op if the source never had
  a raw file written (e.g. failed before `update_storage_path`).
- `kernel/db/sources.py`'s `SourceRepository` gains
  `purge(source_id: str | UUID) -> bool`: `UPDATE sources SET
  import_status = 'PURGED', purged_at = now(), raw_storage_path = NULL
  WHERE id = :id RETURNING id` — returns `True`/`False` on
  found/not-found (RLS already scopes this to the caller's tenant, same
  as every other query in this codebase). This method does not check
  `claim_count` itself — that guard belongs in the API layer, which is
  the only place with visibility into both `SourceRepository` and
  `ClaimRepository` (mirrors how `sources.py`'s `serialize_source` already
  composes both repos, rather than teaching one repo about another
  table).
- `backend/app/api/sources.py` gains `POST /sources/{source_id}/purge`:
  404 if the source doesn't exist (or isn't visible to this tenant), 409
  if `claim_count > 0` (message: `"source has claims — cannot delete
  after extraction"`), otherwise delete the raw file via `delete_raw`
  (if `raw_storage_path` is set) then call `SourceRepository.purge`, and
  return `{"status": "purged"}`.

### Frontend
- `frontend/src/lib/api.ts` gains `purgeSource(sourceId: string):
  Promise<void>`, following the existing `extractClaims`-style POST
  pattern (no body).
- `SourceRow.tsx` gains a "Delete" button (ghost variant, next to the
  existing Extract/Retry button), enabled only when `source.claimCount
  === 0 && source.importStatus !== "PURGED"`. Clicking it asks for
  confirmation via `window.confirm()` (a destructive action needs a
  confirmation step; a full custom modal is unwarranted UI weight for a
  single-user local tool) before calling `purgeSource` and refreshing the
  sources list on success. A `409` (race: claims landed between page load
  and click, e.g. an in-flight extraction job finished) surfaces the
  server's message via the page's existing error-banner pattern rather
  than failing silently.
- Already-`PURGED` rows keep their existing strikethrough rendering
  (`SourceRow.tsx`'s `isPurged` branch, already implemented) — this
  design only adds the action that gets a row into that state.

## Out of Scope
- Deleting a source that already has claims (cascade-delete of
  claims/concepts/edges) — a real feature, but a materially bigger and
  riskier one (what happens to a `concept` that only exists because of
  claims from the deleted source, once other sources also feed the same
  concept?). Left for a future plan if actually needed.
- Undo / trash / restore for purged sources.
- Bulk delete (multi-select).
- Actually reclaiming the `PURGED` status's originally-intended broader
  lifecycle semantics (Phase 0 docs mention a deferred general "source
  quarantine/purge job" — this is deliberately narrower: a direct,
  user-triggered delete action, not an automated retention job).
