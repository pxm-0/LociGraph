# Custodian Logging — Design

## Summary
Phase 3, Plan 2 of the roadmap (follows Custodian Core, precedes
Custodian-assisted contradiction classification). Per
`implementation/05_Custodian_Logging.md`, Custodian conversations aren't only
interface events — a user should be able to say "log this as an observation,"
"mark this as perception, not reality," or "pin this as important" and have
it become real archive data. This plan adds the generic proposed-item
workflow (`custodian_logged_items`) on top of Custodian Core's chat: the
Custodian can *propose* nine kinds of memory, but nothing is canonical until
the user explicitly accepts it — "The Custodian can suggest memory. The user
grants memory." All nine item types from the source doc are in scope, split
into two shapes: five freestanding creates (`observation`, `note`, `claim`,
`task`, `concept_candidate`) and four actions on an existing row
(`reality_assertion`, `perception_assertion`, `contradiction`,
`importance_signal`).

This plan assumes Custodian Core (Phase 3 Plan 1) is implemented — it reuses
that plan's `custodian_sessions`/`custodian_messages` tables and extends its
conversation engine's tool list. It claims migration `0012` (the next after
Custodian Core's `0011`); if Plan 1 hasn't merged by the time this one is
implemented, renumber accordingly.

## Design

### Data model
Three new tables, RLS-scoped exactly like every other table, in
`migrations/versions/0012_custodian_logging.py`:

- `custodian_logged_items`: `id, user_id, session_id, message_id, item_type,
  target_id, content, status, created_at, resolved_at`. `item_type` is one of
  the nine values below; `target_id` is nullable — populated at proposal time
  for the four "acts on an existing row" types, left `NULL` until acceptance
  for the five "creates something new" types (then set to the newly-created
  row's id). `content JSONB NOT NULL DEFAULT '{}'` holds the type-specific
  payload the Custodian filled in when proposing. `status TEXT NOT NULL
  DEFAULT 'proposed'` — `proposed`, `accepted`, `rejected`, `superseded`
  (validated in Python, matching `classification`/`assertion_type`
  elsewhere — no DB `CHECK`). `resolved_at TIMESTAMPTZ` (nullable, set when
  status moves off `proposed`). `message_id UUID REFERENCES
  custodian_messages(id)` (nullable) traces back to the tool-call row that
  proposed it — nullable because of a real ordering constraint: the tool
  executes (creating this row) *before* its own `custodian_messages` row is
  persisted (Custodian Core persists tool-call messages only after the full
  reply completes), so `message_id` starts `NULL` at proposal time and is
  backfilled by the API layer once that message row exists.
- `notes`: `id, user_id, content, created_at` — backs the `note` item type.
  No update/delete in v1, matching this codebase's existing preference for
  append-only records (`revisions`).
- `importance_signals`: `id, user_id, target_type, target_id, created_at` —
  backs `importance_signal`. `target_type` is one of `claim`, `concept`,
  `observation` (validated in Python). Append-only — pinning is a signal you
  add, not a toggle you flip back; there's no un-pin in v1.

`SOURCE_TYPES` (currently `json, markdown, html, pdf, chatgpt, meta`) gains
`custodian`. The first time a user accepts a `claim` or `task` proposal, a
single verified `Source` with `source_type="custodian"` is created for that
user (lazily, reused for every subsequent one) — this is what lets
Custodian-created claims satisfy `claims.source_id`'s existing `NOT NULL` FK
without inventing a parallel claims pipeline. It shows up on `/sources` like
any other source, just with a distinct type badge.

`kernel/models.py` gains `CustodianLoggedItem`, `Note`, `ImportanceSignal`
dataclasses (same `frozen=True, slots=True` + `from_row` shape as every
other model).

### Per-item-type behavior at proposal vs. acceptance

**Freestanding creates** — proposed with `target_id = NULL`, content only;
the real row is created only when accepted:

| item_type | content shape | on accept |
|---|---|---|
| `observation` | `{content, speaker?, observed_at?}` | `ObservationRepository` insert with `source_id=NULL` (observations don't require a source) |
| `note` | `{content}` | insert into `notes` |
| `claim` | `{claim_text, claim_type, assertion_type}` | create a fresh `Observation` *and* `Claim` together, both attached to the lazy `custodian` `Source` — a claim can't exist without an observation, so this stays one action instead of requiring the user to log an observation first |
| `task` | `{claim_text}` | identical to `claim`, with `claim_type` fixed to `"task"` and `assertion_type` fixed to `"reality"` — matching `CLAIM_TYPE_TO_ASSERTION_TYPE_BACKFILL`'s existing `task → reality` mapping, so the model isn't asked to guess a value that's already deterministic elsewhere in this codebase |
| `concept_candidate` | `{candidate_name, concept_type, rationale?}` + **`target_id` = an existing claim** | `ConceptCandidateRepository.create` (concept candidates are structurally claim-linked in this schema — unlike the other four freestanding types, this one needs a target claim from the start, either one already in the archive or one just logged and accepted earlier in the same conversation); `source_id` is read off the target claim itself (`ClaimRepository.get(target_id).source_id`) — every claim already has one, so there's nothing new to supply |

**Acts on an existing row** — `target_id` required at proposal time,
nothing new is created, an existing row is updated or a link/record added:

| item_type | target_id | content shape | on accept |
|---|---|---|---|
| `reality_assertion` | an existing claim | `{}` | sets that claim's `assertion_type = "reality"` via a new `ClaimRepository.set_assertion_type` method (doesn't exist yet) |
| `perception_assertion` | an existing claim | `{}` | same, `assertion_type = "perception"` |
| `contradiction` | claim A | `{claim_b_id, concept_id, rationale}` | validates both claim A and `claim_b_id` are linked to `concept_id` via `claim_concept_edges`; if not, acceptance fails with 422 rather than creating an orphaned row. If they are, calls the existing `ContradictionRepository.create` with `similarity=1.0` — a sentinel meaning "user-asserted," never measured, distinguishing it from detection-created rows without adding a new column |
| `importance_signal` | an existing claim/concept/observation | `{target_type}` | insert into `importance_signals` |

### Conversation engine
`kernel/ai/custodian.py` (Custodian Core) grows from 2 tools to 11: the
existing `search_archive`/`search_concepts` plus 9 `propose_*` tools
(`propose_observation`, `propose_note`, `propose_claim`, `propose_task`,
`propose_concept_candidate`, `propose_reality_assertion`,
`propose_perception_assertion`, `propose_contradiction`,
`propose_importance_signal`), each a separately-typed `strict: true` JSON
schema matching exactly the content shape in the tables above (one tool per
type, not one generic tool with a polymorphic payload, per the existing
`search_archive`/`search_concepts` precedent — strict mode validates a
specific shape far more reliably than a loosely-typed blob). Executing a
`propose_*` tool only inserts a `proposed` `custodian_logged_items` row and
returns its id as the tool output — no canonical write happens until the
user accepts. The system prompt is extended to explain the propose/accept
model, so the Custodian frames these as suggestions ("I can log this as an
observation if you'd like") rather than claiming they're already saved.

### API
`backend/app/api/custodian.py` (Custodian Core's router) gains:
- `GET /custodian/sessions/{id}/logged-items` — list proposals for a
  session (so the chat panel can render them inline alongside messages),
  404 if the session isn't found or isn't this tenant's.
- `POST /custodian/logged-items/{id}/accept` — runs the per-type acceptance
  logic above inside one transaction, sets `status="accepted"`,
  `resolved_at=now()`, and (for the five freestanding types) `target_id` to
  the newly-created row. 404 if not found/not visible, 409 if not currently
  `proposed`, 422 if a `contradiction` proposal fails the shared-concept
  check.
- `POST /custodian/logged-items/{id}/reject` — sets `status="rejected"`,
  `resolved_at=now()`. 404/409 same as accept.

### Frontend
In `CustodianPanel` (Custodian Core), a logged item renders as a distinct
card inline in the message thread — not a plain text line like a
`search_archive` tool-call indicator — showing the item type, a short
human-readable summary of its content (e.g. `Log as observation: "..."`,
`Mark as perception, not reality`), and Accept/Reject buttons while
`status="proposed"`. Accepting calls the accept endpoint and flips the card
to a small confirmation (`Logged as an observation ✓`, linking to the new
row where a page for it exists — e.g. `/observations/{id}` isn't a route
today, so link only for types that do have one, like a future
`/concepts/{id}` for an accepted `concept_candidate`'s eventual promotion —
that promotion step itself is unchanged, still the existing Approve flow on
`/claims`). Rejecting grays the card out with "Rejected." No new page — this
lives entirely inside the existing chat panel.

### Testing
- Repository tests for `CustodianLoggedItemRepository`, `NoteRepository`,
  `ImportanceSignalRepository` CRUD, plus tenant isolation cases.
- Repository test for the new `ClaimRepository.set_assertion_type`.
- Engine tests for each of the 9 `propose_*` tools — dispatch routes to the
  right insert, payload shape matches the table above.
- API tests for accept/reject across all nine item types, including the
  409 (already resolved) and 422 (contradiction concept mismatch) cases.
- Frontend tests for the proposal card (renders, accept/reject call the
  right endpoint, confirmation/rejected states render).
- Same 80%-minimum coverage bar as the rest of the codebase.

## Out of Scope
- A standalone review inbox outside the chat panel — proposals are only
  reviewable inline, in the session that produced them. Add a cross-session
  inbox later if reviewing days-old proposals turns out to matter in
  practice.
- Un-pinning an `importance_signal` or editing/deleting a `note` — both are
  append-only in v1, matching `revisions`.
- Custodian-assisted contradiction *classification* (setting `unresolved` →
  `true_conflict`/`evolution`/etc. on an existing contradiction) — the next
  Phase 3 plan. This plan only covers the Custodian *creating* a new
  contradiction row directly, which is a different action.
- Retroactively linking an accepted `concept_candidate` into a canonical
  concept — unchanged, still goes through the existing `/claims` page
  Approve/Reject flow.
- Skipping the accept step for user-initiated requests — every proposal,
  regardless of who initiated it, requires one explicit accept action.
- Librarian roles — still no scope defined anywhere.
