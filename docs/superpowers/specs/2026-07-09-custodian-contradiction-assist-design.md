# Custodian-Assisted Contradiction Classification — Design

## Summary
Phase 3, Plan 3 of the roadmap (final Custodian plan — follows Custodian Core
and Custodian Logging). Per ADR-005, "the user, assisted by the Custodian,
can classify [contradictions] later." This plan wires that callback: the
Custodian can find unresolved contradictions, discuss them, and propose a
classification through the exact propose/accept flow Custodian Logging
already built — a 10th `custodian_logged_items` item type, not a new
mechanism. On accept, it calls the same `ContradictionRepository.classify`
the existing `/contradictions` page's button already calls, so behavior
(including `evolution`'s auto-enqueued revision synthesis) matches exactly
regardless of which path classified it.

## Design

### Retrieval: `search_contradictions`
A third read-only tool alongside Custodian Core's `search_archive`/
`search_concepts`: `search_contradictions(concept_id?, limit)`, backed by
the existing `ContradictionRepository.list(concept_id=..., classification=
"unresolved", limit=...)` — no new repository method needed. Without this,
the Custodian could only classify a contradiction the user already knows
the id of; this lets it discover ones worth discussing. Returns each
contradiction's id, both claims' text, and the LLM's original detection
rationale (already stored on the row) so the model has the same context a
human reviewing `/contradictions` would see.

### Propose/accept: `contradiction_classification`
`ITEM_TYPES` (from Custodian Logging) gains `contradiction_classification`.
`target_id` = the contradiction being classified; `content = {classification}`
where `classification` is one of `ContradictionRepository`'s existing
`CLASSIFICATIONS` (`true_conflict`, `evolution`, `contextual_difference`,
`both` — never `unresolved`, matching the existing `/contradictions` page's
own rule that you classify *into* a resolution, not back into unresolved).

New tool `propose_classify_contradiction(contradiction_id, classification)` in
`kernel/ai/custodian.py`'s tool list, dispatched the same way Custodian
Logging's other nine `propose_*` tools are.

`kernel/custodian_logging.py`'s `accept_logged_item` gains an
`item.item_type == "contradiction_classification"` branch: calls
`ContradictionRepository(conn).classify(item.target_id, item.content
["classification"])`. If the contradiction doesn't exist or isn't visible to
this tenant, `classify` already returns `None` (matching its existing
contract) — raise `LoggedItemNotResolvable(reason="not_found")`, same as
every other missing-target case in Custodian Logging.

### The evolution → revision-synthesis auto-enqueue
`backend/app/api/contradictions.py`'s existing `classify_contradiction`
endpoint auto-enqueues a `create_revision` job when `classification ==
"evolution"` — this logic (creating a `Job` row, calling `create_revision
.send(...)`, wrapped in try/except-log-warning-on-failure) touches
dramatiq, so it can't live in the pure `kernel/custodian_logging.py` module
(the same "kernel stays pure, the side effect belongs to the orchestrating
caller" rule Custodian Logging's own accept/reject already follows for its
nine item types). Left alone, a Custodian-proposed `evolution` classification
accepted through `backend/app/api/custodian.py` would silently skip revision
synthesis — a behavioral gap between the two classify paths, not just a
style issue.

Fix: extract the auto-enqueue block out of `contradictions.py`'s endpoint
into a standalone function, `maybe_enqueue_revision_synthesis(user_id: str,
contradiction_id: str, classification: str) -> None`, still living in
`backend/app/api/contradictions.py` (it's API-layer orchestration, not
kernel logic) but now callable from both places. The existing `/contradictions`
classify endpoint calls it after its own `classify()` call exactly as
today; the new Custodian accept endpoint
(`POST /custodian/logged-items/{id}/accept`) calls it too, after
`accept_logged_item` returns, when the resolved item's `item_type ==
"contradiction_classification"` and its `content["classification"] ==
"evolution"`.

### Frontend
No new component — `ProposalCard` (Custodian Logging) gains one more
`summarize()` case: `Classify contradiction as {classification}`. The
`item_type` string itself is the only new surface area on the frontend.

### Testing
- Engine test for `search_contradictions` (returns unresolved contradictions
  with both claims' text and rationale) and for the `propose_classify_
  contradiction` tool's dispatch (creates a `proposed` item with the right
  `target_id`/content).
- Orchestration test for `accept_logged_item`'s new branch: valid
  classification classifies the contradiction; invalid target 404s the same
  way every other item type's missing-target case does.
- API test that accepting an `evolution` classification through
  `/custodian/logged-items/{id}/accept` enqueues `create_revision` — same
  assertion shape as the existing test for the `/contradictions` classify
  endpoint's auto-enqueue, just through the other path.
- API test that a non-`evolution` classification does not enqueue anything,
  through the Custodian path.
- Frontend test for the new `summarize()` case.

## Out of Scope
- Custodian creating a brand-new contradiction from scratch — that's
  Custodian Logging's existing `contradiction` item type (Plan 2), a
  different action from classifying one that already exists.
- Reopening a classified contradiction back to `unresolved` — unchanged,
  still out of scope everywhere in this codebase.
- Any Librarian role.
- Automatically classifying without the user's accept — every proposal,
  from Custodian Logging through this plan, requires one explicit accept.
