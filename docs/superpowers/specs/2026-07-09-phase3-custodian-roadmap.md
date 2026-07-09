# Phase 3 Roadmap — Custodian

## Summary

Per `implementation/06_Roadmap.md`, Phase 3 is "Custodian, Custodian logging."
Per `implementation/03_AI_Architecture.md` and `implementation/05_Custodian_Logging.md`,
the Custodian is a user-facing conversational AI guide that explains the
archive, retrieves evidence, helps classify contradictions, and can log new
observations/claims/concepts/tasks — with the rule that nothing it proposes
becomes canonical until the user grants it ("The Custodian can suggest
memory. The user grants memory.").

This phase is scoped to the Custodian only. The "Librarians" (Claim, Concept,
Revision, Contradiction, Planetarium, Janitor) named in
`implementation/03_AI_Architecture.md` are future AI roles with no scope
defined yet — deferred entirely, not touched by any Phase 3 plan.

**Recalibration (2026-07-09, post Phase 2 completion):** Phase 2 is now fully
merged to `main` — all three plans (Reality/Perception Separation #13,
Contradictions #14, Revisions #15) are done. This roadmap was originally
written while Contradictions was still mid-implementation and Revisions was
unplanned; that framing is now moot. Plan 3 below (contradiction-classification
assist) reads the final, shipped `contradictions` API
(`GET /api/contradictions`, `POST /api/contradictions/{id}/classify`) — its
assumptions held. Revisions' own design doc
(`docs/superpowers/specs/2026-07-09-revisions-design.md`) explicitly deferred
"any Custodian involvement" to this phase, so no scope collision there either.
The one concrete casualty: Revisions claimed migration `0010`
(`migrations/versions/0010_revisions.py`), which Plan 1 below had reserved for
Custodian's tables — bumped to `0011`.

## Plans

### Plan 1: Custodian Core

Conversational chat interface: `custodian_sessions`/`custodian_messages`
persistence, an LLM conversation loop, and retrieval-augmented answers over
the user's own claims/concepts/observations ("explains the archive,
retrieves evidence"). Read-only — the Custodian can discuss and cite the
archive but cannot yet write to it. This is the foundation every later plan
builds on (chat UI, session lifecycle, provider integration, retrieval).

### Plan 2: Custodian Logging

Generic tool-calling / proposed-item workflow on top of Plan 1:
`custodian_logged_items` with `item_type` (observation, claim,
concept_candidate, reality_assertion, perception_assertion,
importance_signal, task, note) and `status` (proposed, accepted, rejected,
superseded). The user reviews and grants/rejects what the Custodian
proposes during a chat session; nothing is auto-canonical.

### Plan 3: Custodian-assisted contradiction classification

The specific ADR-005 callback ("assisted by the Custodian") — wires Plans 1
and 2 into the existing Contradictions feature. Adds `contradiction` as a
loggable item type whose `target_id` references an existing
`contradictions` row, and lets the Custodian discuss a pair of conflicting
claims and propose a classification (`true_conflict`, `evolution`,
`contextual_difference`, `both`) the user can accept.

## Out of scope (all of Phase 3)

- Librarians (any role) — no scope defined, future phase or later Phase 3 follow-up.
- Custodian creating brand-new contradictions unprompted (only classifying existing ones).
- Revisions (Phase 2 Plan 3) — Plan 3 here only sets `classification`, it does not consume `evolution` classifications into a revision history.
- Voice/multimodal input, multi-session memory beyond a single `custodian_sessions` row, proactive/unprompted Custodian messages.

## Ordering

Plan 1 → Plan 2 → Plan 3, strictly sequential (each is a prerequisite for the next). Each gets its own design doc and implementation plan, written and executed one at a time — matching how Phase 1 and Phase 2 plans were done.
