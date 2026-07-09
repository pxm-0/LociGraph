# Custodian Core — Design

## Summary
Phase 3, Plan 1 of the roadmap (first of three Custodian plans: Core, then
Logging, then Custodian-assisted contradiction classification). Per
`implementation/03_AI_Architecture.md`, the Custodian is a user-facing
conversational AI guide that explains the archive and retrieves evidence.
This plan builds the conversational core: chat sessions, streamed replies,
and archive retrieval via LLM tool-calling — read-only, no writes to the
archive. Custodian Logging (proposing observations/claims/concepts/tasks
from chat) and contradiction-classification assistance are explicitly out of
scope; both build on this plan's session/message infrastructure. Librarian
roles (`implementation/03_AI_Architecture.md`) have no defined scope and are
untouched.

Unlike every existing AI call in this codebase (`extract_claims`,
`embed_claims`, `detect_contradictions`, and `create_revision`), the Custodian
is not a background dramatiq job gated behind an autorun flag — it's a
direct, synchronous conversation triggered by normal use, so it introduces
this codebase's first streaming endpoint and its first per-session cost
guardrail.

## Design

### Data model
Two new tables, RLS-scoped exactly like every other table
(`ENABLE`/`FORCE ROW LEVEL SECURITY`, `<table>_user_isolation` policy,
`GRANT` to `locigraph_app`), added in `migrations/versions/0011_custodian.py`
(the next revision after `0010_revisions.py`, Phase 2 Plan 3's migration,
which landed after this design was first drafted):

- `custodian_sessions`: `id, user_id, title, started_at, ended_at, model,
  provider`. `title` is nullable, set from the first user message (truncated)
  so the session switcher has something to show; `ended_at` is set when the
  message cap is hit or the user explicitly ends the session.
- `custodian_messages`: `id, session_id, user_id, role, content, tool_name,
  tool_input, tool_output, created_at`. `role` is one of `user`, `assistant`,
  `tool`, `system` — the last for cap/error notices. `tool_name`/`tool_input`/
  `tool_output` are nullable and only populated on `role="tool"` rows (one row
  per `search_archive` call), giving a complete, replayable transcript.
  `user_id` is denormalized onto messages (not just sessions) so RLS can scope
  the messages table directly without a join, matching how every other
  child table in this schema carries its own `user_id`.

`kernel/models.py` gains `CustodianSession` and `CustodianMessage` dataclasses
(same `frozen=True, slots=True` + `from_row` pattern as every other model).
`kernel/db/custodian.py` gains `CustodianRepository` with
`create_session`, `get_session`, `list_sessions`, `end_session`,
`add_message`, `list_messages`, `count_messages` — same
already-open-`AsyncConnection` pattern as `BaseRepository`.

### Conversation engine
New `kernel/ai/custodian.py`, mirroring `kernel/ai/claim_extraction.py`'s
shape: `CustodianSettings.from_env()` (`active_ai_provider`,
`openai_api_key`, `openai_custodian_model` default `gpt-4o-mini`,
`custodian_max_messages_per_session` default `100`), and a provider class
(`OpenAICustodian`) built the same
`if settings.active_ai_provider != "openai": raise ValueError(...)` way as
`get_claim_extractor`.

`OpenAICustodian.stream_reply(messages, on_token, on_tool_call)` calls
OpenAI's Responses API in streaming mode with one tool declared:
`search_archive(query: str, limit: int = 10)`. The model may call it zero or
more times per turn; each call is executed against the exact same
`SemanticVectorRepository.search_similar` path `backend/app/api/search.py`
already uses (embed the query via `get_embedder`, then cosine search), and
the result is fed back to the model as the tool's output before it continues
generating. Every tool call/result is persisted as a `role="tool"` message
via the callback, and streamed token deltas are persisted as a single
`role="assistant"` message once generation completes.

### Cost guardrail
Before accepting a new message, the endpoint checks
`CustodianRepository.count_messages(session_id)` against
`custodian_max_messages_per_session`. Once hit, the session is marked
`ended_at = now()` and further messages to it return 409 with a message
telling the user to start a new conversation. This is the same
tunable-env-var-limit shape as `CONTRADICTION_CANDIDATE_LIMIT`/
`CLAIM_EXTRACTION_BATCH_SIZE` elsewhere in this codebase, sized for a
guardrail rather than a UX-facing quota.

### API
`backend/app/api/custodian.py` (new router), all endpoints RLS-scoped via
the existing `get_current_user` cookie-auth dependency:
- `POST /custodian/sessions` — creates a session, returns it. Body optional
  (`{"title": str | None}`).
- `GET /custodian/sessions?limit=&offset=` — list, newest first.
- `GET /custodian/sessions/{id}/messages` — full transcript for one session,
  404 if not found or not visible to this tenant.
- `POST /custodian/sessions/{id}/messages` — body `{"content": str}`.
  Persists the user message, then returns a `text/event-stream` response:
  each SSE event is one token delta (`event: token`) or a tool-call notice
  (`event: tool_call`, `{"tool_name": "search_archive", "query": "..."}`),
  terminated by `event: done`. If the OpenAI call raises, emits
  `event: error` with a sanitized message and persists a `role="system"`
  message recording the failure — no auto-retry. 409 if the session has
  already hit its message cap.
- `POST /custodian/sessions/{id}/end` — explicit end, sets `ended_at`.

If the client disconnects mid-stream, generation continues to completion
server-side (the persist happens regardless of whether anyone is still
listening), so reloading the page shows the full reply rather than a
truncated one.

### Frontend
A new `Orb` component (client component) rendered inside
`frontend/src/components/layout/AppChrome.tsx` (the shell that already wraps
`Sidebar` + page content, per `frontend/src/app/(app)/layout.tsx`) so it's
present on every authenticated page — a fixed-position floating circle with
the DESIGN.md breathing-pulse
animation (1.4s infinite), teal/soft and bottom-corner in Hearth mode,
ember/scanning-ring and bottom-center in Meridian mode, driven by the
existing `data-mode` toggle. Clicking it expands a chat panel overlay
containing:
- a session switcher (list from `GET /custodian/sessions`, "New
  conversation" action),
- the message thread for the active session (user/assistant bubbles; a
  `role="tool"` message renders as a small "Searched the archive for
  '...'" indicator rather than raw JSON),
- a text input that POSTs a message and streams the reply in.

Since the streaming endpoint is POST (not GET), the client consumes it via
`fetch()` + a `ReadableStream` reader parsing SSE-formatted chunks rather
than `EventSource` (which can't carry a POST body). `frontend/src/lib/api.ts`
gains `createCustodianSession`, `listCustodianSessions`,
`getCustodianMessages`, and `streamCustodianMessage(sessionId, content,
{onToken, onToolCall, onDone, onError})`.

Scope note: the Orb's only job in this plan is opening the Custodian chat.
DESIGN.md's separate "Archivist's Dock" / "Instrument Panel" navigation-dock
behavior is a distinct nav feature with no defined scope in the Phase 3
roadmap and stays out of scope here.

### Testing
- `tests/kernel/test_custodian_repository.py` — session/message CRUD, same
  shape as `test_contradictions_repository.py`.
- `tests/kernel/test_tenant_isolation.py` — add Custodian session/message
  isolation cases.
- `tests/kernel/test_custodian_engine.py` — conversation engine with a mocked
  OpenAI streaming client: token-delta assembly, the tool-call loop
  (`search_archive` invoked, result fed back, second turn generated),
  message-cap enforcement.
- Backend API tests hitting `/api/custodian/*` with a mocked provider,
  covering auth (401), the cap (409), and SSE event framing.
- Frontend RTL tests for the Orb (pulse renders, click expands panel),
  session switcher, and streamed-message rendering (mocked fetch stream).
- Same 80%-minimum coverage bar as the rest of the codebase.

## Out of Scope
- Custodian Logging (proposing observations/claims/concepts/tasks from
  chat) — the next Phase 3 plan, built on this plan's session/message
  tables.
- Custodian-assisted contradiction classification — the Phase 3 plan after
  that.
- Librarian roles of any kind — no scope defined yet anywhere in the
  design docs.
- Concept retrieval (`search_archive` only searches claims via the existing
  embedding index; concepts have no embeddings yet, per Phase 1 Plan 3).
- The "Archivist's Dock" / "Instrument Panel" navigation-dock behavior
  described in DESIGN.md — a distinct nav feature, not part of the Custodian
  work.
- Multi-provider support — same single-active-provider policy as every
  other AI call in this codebase (`ACTIVE_AI_PROVIDER`, OpenAI only today).
- Editing or deleting past messages, exporting a transcript, session
  renaming after creation, voice/multimodal input.
- Retrying a failed generation automatically — the user re-sends.
