# Phase 1 - Plan 1: Claim Extraction & Concept Candidate Foundation

## Summary
Implement the first Phase 1 slice as a real observation-to-claim pipeline. Add
durable claim storage, proposed concept candidates, an AI extraction worker,
auto-after-ingest extraction, manual extraction controls, and browse UI. Do not
create canonical concepts in this plan.

## Task Briefs
- Task 1: schema foundation.
  - Add Alembic migration for RLS-protected `claims` and `concept_candidates`.
  - Add grants, indexes, model dataclasses, repositories, and isolation tests.
- Task 2: provider and worker.
  - Add provider-agnostic extraction interface and OpenAI Structured Outputs implementation.
  - Add `extract_claims` Dramatiq task with idempotent default behavior and force retry.
  - Auto-enqueue extraction after successful ingest when enabled.
- Task 3: API.
  - Add manual `POST /sources/{source_id}/extract-claims`.
  - Add `GET /claims`, `GET /claims/{claim_id}`, and `GET /concept-candidates`.
  - Extend source responses with claim count and extraction readiness.
- Task 4: frontend.
  - Add `/claims` browse route.
  - Add claim counts and extraction controls to `/sources`.
  - Preserve the accepted `DESIGN.md` Hearth/Meridian visual language.
- Task 5: docs, review, publish.
  - Update README/env/deployment docs.
  - Run backend/frontend gates and Caddy browser QA.
  - Commit, push, and open a draft PR.

## Out of Scope
- Canonical concepts and concept approval flows.
- Graph nodes/edges, contradiction detection, embeddings, Custodian, and Planetarium.
- Multi-provider extraction beyond the OpenAI implementation behind the provider interface.
