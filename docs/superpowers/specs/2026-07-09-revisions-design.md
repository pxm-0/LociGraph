# Revisions — Design

## Summary
Phase 2, Plan 3 of the roadmap (final plan — completes Phase 2). Per ADR-004,
concepts carry provenance including "revision history." This plan gives
concepts their first mutable field (`description`) and a `revisions` table
recording every change to it. There are two ways a revision gets created:
automatically, when a contradiction is classified `evolution` (an LLM
synthesizes the updated understanding from both conflicting claims), or
manually, by the user directly writing a new description for any concept at
any time — the "sideload cognition" path, independent of the contradiction
pipeline entirely. Both paths converge on the same table and the same
concept mutation, so "override an LLM synthesis you don't like" is just
"write another revision on top" — no separate edit/accept/reject mechanism
needed, since revisions are append-only and a concept's current description
is always whatever its latest revision says.

## Design

### Data model
New table `revisions`, RLS-scoped exactly like every other table:

- `id, user_id, concept_id` — `concept_id` references `concepts(id)`.
- `contradiction_id UUID REFERENCES contradictions(id)` — **nullable**: set
  for LLM-synthesized revisions, `NULL` for manual ones. This is the only
  column distinguishing the two paths' data shape (the `source` column below
  is the explicit, readable flag).
- `source TEXT NOT NULL` — `'llm_synthesis'` or `'manual'`. Unlike
  `classification` on `contradictions`, this value is never user-supplied —
  both call sites (the manual endpoint, the worker) pass a hardcoded literal
  — so there's no external input to validate and no `REVISION_SOURCES`
  constant needed, just the two literal strings used consistently.
- `previous_description TEXT` — nullable, mirrors `concepts.description`
  being nullable (a concept created without a description has `NULL` here
  for its first revision).
- `new_description TEXT NOT NULL`.
- `rationale TEXT` — nullable. The LLM's explanation for `llm_synthesis`
  revisions; optional free text the user can supply for `manual` ones.
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`.

`kernel/models.py` gains a `Revision` dataclass (same `frozen=True,
slots=True` + `from_row` pattern as every other model).

`ConceptRepository` (`kernel/db/concepts.py`) gains its first mutation
method: `update_description(concept_id, new_description) -> Concept | None`
(`UPDATE concepts SET description = :description WHERE id = :id RETURNING
...`). Nothing before this plan ever changes a concept after creation.

### Manual path (synchronous, no AI)
New endpoint `POST /concepts/{concept_id}/revisions`
(`backend/app/api/concepts.py`, alongside the existing `/concepts/{id}/claims`
nested-resource endpoint): body `{"new_description": str, "rationale":
str | None}`. Inside one `session(user_id)` block: look up the concept (404
if missing), call `ConceptRepository.update_description`, then
`RevisionRepository.create(source="manual", contradiction_id=None,
previous_description=<concept's description before the update>,
new_description=body.new_description, rationale=body.rationale)`. Returns
the serialized revision. This works on any concept at any time — it does not
require a contradiction, a claim, or any prior revision to exist. It does
**not** create new concepts; a concept must already exist (via the existing
extraction/approval pipeline) before it can be revised.

### Automatic path (async, LLM-synthesized)
`POST /contradictions/{id}/classify` (`backend/app/api/contradictions.py`)
gains one addition: when `body.classification == "evolution"`, after the
existing `session(user_id)` block that performs the classification has
closed and committed, auto-enqueue a new `create_revision` job — deliberately
*after* that commit, not inside it, per the lesson from Phase 2 Plan 2 Task
4 (a job enqueued before its referencing row commits risks the worker
reading state that isn't visible yet under READ COMMITTED). Payload is just
`{"contradiction_id": str(contradiction.id)}` — unlike `detect_contradictions`,
the worker doesn't need `concept_id`/`claim_id` passed separately, because by
this point a persisted `contradictions` row already holds `concept_id`,
`claim_a_id`, and `claim_b_id`. Wrapped in the same try/except-log-warning
shape as every other auto-enqueue in this codebase — a broker/config failure
must never break the classify response. **No `*_AUTORUN` flag** gates this:
classification is already a single, deliberate human action (unlike
extraction/embedding/contradiction-detection, which process many items
automatically), so there's no bulk-cost/consistency reason to add an opt-in
toggle on top of it.

New `worker/tasks/create_revision.py`, mirroring `detect_contradictions.py`'s
shape exactly:
1. Load the contradiction, its concept, and both claims.
2. Call `get_revision_synthesizer(settings).synthesize(concept.description,
   claim_a.claim_text, claim_a.assertion_type, claim_b.claim_text,
   claim_b.assertion_type)` → `RevisionSynthesis(new_description, rationale)`.
3. `ConceptRepository.update_description(concept.id, new_description)`.
4. `RevisionRepository.create(source="llm_synthesis",
   contradiction_id=contradiction.id, previous_description=concept's
   description before step 3, new_description=..., rationale=...)`.
5. Mark the job completed.

**Reliability tolerances mirror every other AI worker in this codebase**:
`@dramatiq.actor(queue_name="extraction", max_retries=3,
on_retry_exhausted="heal_create_revision")`, no custom `time_limit` (one LLM
call, comfortably inside dramatiq's default). Self-healing reuses
`worker/tasks/healing.py` unchanged.

### Synthesis
New `kernel/ai/revision_synthesis.py`, mirroring
`kernel/ai/contradiction_detection.py`'s shape: `RevisionSynthesisSettings`
(`from_env`, new env var `OPENAI_REVISION_MODEL` default `gpt-4o-mini`),
`RevisionSynthesis` dataclass (`new_description: str, rationale: str`),
`_parse_revision_payload`, `OpenAIRevisionSynthesizer.synthesize(...)` (one
structured-output `responses.create` call — system prompt: the two claims
were classified by a human as an *evolution* of understanding, not a
conflict; given the concept's current description and both claims, write an
updated description and briefly explain what changed), `get_revision_synthesizer`.

### API
- `POST /concepts/{concept_id}/revisions` — manual path, described above.
- `GET /concepts/{concept_id}/revisions?limit=&offset=` — lists a concept's
  revision history, newest first. Same file, same nested-resource pattern as
  `/concepts/{id}/claims`.

### Frontend
First-ever concept detail page: `frontend/src/app/(app)/concepts/[id]/page.tsx`.
Shows the concept's name/type/current description, its claims (via the
existing `getConceptClaims` — currently defined but unused by any page), and
its revision history (via new `getConceptRevisions`) rendered newest-first,
each entry tagged by `source` (`llm_synthesis` vs `manual`) with
previous → new description and rationale. A form (textarea + optional
rationale field + submit) calls new `createConceptRevision(conceptId,
newDescription, rationale?)` for the manual path. `/concepts/page.tsx`'s
list rows become links into this detail page.

## Out of Scope
- Any revision trigger other than `evolution` classification —
  `true_conflict`/`contextual_difference`/`both` never touch a concept.
- Concept merging — ADR-004 names "merge history" as a separate concern from
  revision history; not this plan.
- Editing or deleting an existing revision once created — revisions are
  immutable and append-only; correcting one means writing a new one on top.
- Creating a brand-new concept via a revision — a concept must already exist
  (through the existing extraction/candidate-approval pipeline) before it
  can be revised.
- Any Custodian involvement (Phase 3, including the concurrently-being-scoped
  Custodian Core plan on a separate branch).
