# Phase 1 - Plan 3: Embeddings & Semantic Search

## Summary
Generate OpenAI embeddings for claims, store them in a new pgvector-backed
`semantic_vectors` table, and expose a semantic search endpoint + `/search`
page that ranks claims by cosine similarity to a query. Concepts are not
embedded in this plan — claims are the only embedded entity.

## Task Briefs

### Task 1: schema foundation
- Add Alembic migration `0004` for RLS-protected `semantic_vectors`: `id,
  user_id, claim_id (UNIQUE, references claims(id)), embedding vector(1536),
  model_name, created_at`. pgvector's `vector` extension is already enabled
  (migration `0001`); the installed version is 0.8.3, which supports HNSW —
  add `CREATE INDEX semantic_vectors_embedding_hnsw_idx ON semantic_vectors
  USING hnsw (embedding vector_cosine_ops)`. RLS enable+force+policy and
  grants must match the `claims`/`concepts` pattern from migrations `0002`/
  `0003` exactly.
- Add a `SemanticVector` dataclass to `kernel/models.py` (same
  `frozen=True, slots=True` + `from_row` style as `Claim`/`Concept`).
- Add `kernel/db/semantic_vectors.py`'s `SemanticVectorRepository`:
  `create(*, user_id, claim_id, embedding, model_name)` (idempotent —
  `ON CONFLICT (claim_id) DO NOTHING`, matching the existing
  `ON CONFLICT DO NOTHING RETURNING` idiom), `get_for_claim(claim_id)`,
  and `claim_ids_without_vector(source_id)` (for the backfill worker —
  claims for a source that have no row in `semantic_vectors` yet). Storing
  and reading the vector: pgvector has no asyncpg codec installed in this
  project, so pass/read it as its literal text form — `CAST(:embedding AS
  vector)` on write (`:embedding` bound as `"[0.1,0.2,...]"`), and cast to
  text on read (`embedding::text`) then parse back into `list[float]` in
  `from_row`.
- Add tenant-isolation tests mirroring `tests/kernel/test_tenant_isolation.py`.

### Task 2: embedding provider and worker
- Add `kernel/ai/embeddings.py`, mirroring `kernel/ai/claim_extraction.py`'s
  shape: `EmbeddingSettings.from_env()` reading `OPENAI_EMBEDDING_MODEL`
  (default `text-embedding-3-small`), `EMBEDDING_DIMENSIONS` (default
  `1536`), and `EMBEDDING_AUTORUN` (default `false`, same
  `.lower() == "true"` parsing as `CLAIM_EXTRACTION_AUTORUN`). Add
  `OpenAIEmbedder.embed(texts: Sequence[str]) -> list[list[float]]` using
  `AsyncOpenAI().embeddings.create(model=..., input=texts,
  dimensions=...)`, and `get_embedder(settings=None) -> OpenAIEmbedder`
  (same provider-validation shape as `get_claim_extractor` — no `Protocol`,
  since there's exactly one provider, same as Plan 2's review finding on
  `claim_extraction.py`).
- Add `worker/tasks/embed_claims.py`'s `embed_claims` Dramatiq actor
  (`queue_name="extraction"`, `max_retries=3`, same shape as
  `worker/tasks/extract_claims.py`): given `source_id, user_id, job_id`,
  find claims for the source with no `semantic_vectors` row
  (`claim_ids_without_vector`), batch them (reuse `itertools.batched`,
  same `settings.claim_extraction_batch_size`-style batch size — read the
  actual batch-size setting name you add in this task), embed each batch,
  and `create()` a `semantic_vectors` row per claim. Mark the job
  completed/failed via `JobRepository`, redacting API-key fragments in
  errors the same way `worker/tasks/extract_claims.py:_public_error` does
  (reuse that function or an equivalent — don't duplicate the regex).
- Auto-enqueue: in `worker/tasks/extract_claims.py`'s `_extract_claims`,
  after claims are successfully persisted, if `EMBEDDING_AUTORUN` is true
  and at least one claim was created, enqueue `embed_claims` the same way
  `worker/tasks/ingest_source.py` auto-enqueues `extract_claims` behind
  `CLAIM_EXTRACTION_AUTORUN`.
- Unit tests with a fake embedder (mirroring `tests/worker/test_extract_claims.py`'s
  `FakeExtractor`): embeds only claims lacking a vector, is idempotent
  (running twice doesn't duplicate rows), auto-enqueue fires only when the
  flag is set and claims exist, error path redacts API keys.

### Task 3: API
- Add `POST /sources/{source_id}/embed-claims`, mirroring
  `POST /sources/{source_id}/extract-claims` in `backend/app/api/sources.py`
  exactly: 404 if source missing, 409 if source isn't `VERIFIED`, creates a
  job via `JobRepository`, enqueues `embed_claims`, returns
  `{"job_id": ..., "status": "pending"}`.
- Add `GET /search?q=...&limit=20`: embed `q` via the Task 2 embedder,
  query `semantic_vectors` for the nearest claims by cosine distance
  (`embedding <=> CAST(:query_embedding AS vector)`, ascending — pgvector's
  `<=>` operator is cosine distance, smaller is more similar), joined back
  to `claims` for the claim fields, scoped by RLS like every other query in
  this codebase. Add this as a repository method
  (`SemanticVectorRepository.search_similar(query_embedding, limit)`
  returning claims + a similarity score), not an inline join in the router
  — same rule Plan 2's Task 3 brief set for `claim_count`. Return each
  result's claim fields plus a `similarity` field (`1 - cosine_distance`,
  so higher is more similar, easier for a frontend to reason about than a
  distance).
- Tests: embed-claims endpoint auth/404/409 paths (mock the embedder, don't
  call OpenAI), search endpoint ranks a semantically close claim above an
  unrelated one (mock the embedder to return a fixed vector per input so
  the ranking is deterministic in the test), tenant isolation on search
  (a user never sees another tenant's claims in results, even ranked as
  the top hit).

### Task 4: frontend
- Add to `frontend/src/lib/types.ts`/`api.ts`:
  `search(query, limit?)` client function calling `GET /search`, following
  the existing `toClaim`/`req`/`readError` conventions. Add an
  `embedClaims(sourceId)` client function mirroring `extractClaims`.
- Add a `/search` page: a search input, results list reusing the claim-card
  rendering already established in `/claims` (claim text, type badge,
  confidence), plus a similarity indicator per result. No polling — search
  is a single synchronous request/response, same correction as Plan 2's
  approve/reject (don't build a job-polling pattern for a request that
  already completes synchronously).
- Add a "Search" entry to `Sidebar.tsx`'s `NAV_ITEMS`.
- Optionally surface an "Embed claims" control on `/sources` next to the
  existing "Extract"/"Retry" button, following `SourceRow.tsx`'s existing
  action-button pattern — implementer's call whether this fits cleanly or
  should wait for a later plan; note the decision in the report.
- Preserve `DESIGN.md`'s Hearth/Meridian visual language. Tests following
  existing `vi.mock("@/lib/api", ...)` conventions.

### Task 5: docs, review, publish
- Update README/docs to describe the embedding + search flow, and add
  `OPENAI_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `EMBEDDING_AUTORUN` to
  `.env.example` under the existing "AI" section.
- Run backend/frontend gates (pytest, ruff, mypy, vitest, tsc, eslint) and
  browser QA covering: embed-claims job completes, semantic search returns
  ranked results, tenant isolation on search.
- Commit. Do not push or open a PR — that decision belongs to the
  controller/human, same as Plan 2's Task 5.

## Out of Scope
- Concept embeddings — only claims are embedded in this plan.
- Hybrid keyword+semantic search, query rewriting, or re-ranking beyond
  raw cosine similarity.
- Re-embedding on claim edit or versioning (claims are currently
  immutable once created; revisit if that changes).
- Contradiction detection (Phase 2), Custodian (Phase 3), Planetarium
  (Phase 4).
- Multi-provider embeddings beyond the OpenAI implementation (same
  carried-over constraint as Plans 1 and 2).
