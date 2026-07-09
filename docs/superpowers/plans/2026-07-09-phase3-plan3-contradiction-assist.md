# Custodian-Assisted Contradiction Classification (Phase 3 Plan 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Custodian find unresolved contradictions, discuss them, and propose a classification through the existing propose/accept flow — the ADR-005 callback ("assisted by the Custodian").

**Architecture:** One more read-only tool (`search_contradictions`) and one more `custodian_logged_items` item type (`contradiction_classification`), both following the exact shape Custodian Logging (Plan 2) already established. The one new piece of machinery: the existing `/contradictions` classify endpoint's evolution→auto-enqueue-revision-synthesis logic gets extracted into a shared function so the Custodian's accept path triggers it too, instead of silently skipping revision synthesis on that path.

**Tech Stack:** Python 3.12, FastAPI, OpenAI Responses API function tools, Next.js/React/TypeScript, pytest + vitest.

**Depends on:** Phase 3 Plan 1 (Custodian Core) and Phase 3 Plan 2 (Custodian Logging) — reuses their conversation engine, `custodian_logged_items` table, and `ProposalCard` component. Also reuses Phase 2 Plan 2's `ContradictionRepository`/`CLASSIFICATIONS` and Phase 2 Plan 3's `create_revision` auto-enqueue.

## Global Constraints

- No DB migration in this plan — `contradiction_classification` is just one more value in the existing `ITEM_TYPES` Python set (no DB `CHECK` constraint backs it, same as every other item type).
- `classification` content is validated against `kernel.db.contradictions.CLASSIFICATIONS` minus `"unresolved"` — you classify *into* a resolution, matching the existing `/contradictions` page's own rule.
- The evolution→auto-enqueue-revision call happens *after* the accept transaction commits, never inside the same `session()` block — sending the dramatiq message before commit risks `create_revision` reading a row that isn't visible yet under READ COMMITTED isolation (the exact bug already fixed once, in Phase 2 Plan 2's own auto-enqueue wiring — don't reintroduce it here).
- Design reference: `docs/superpowers/specs/2026-07-09-custodian-contradiction-assist-design.md`.

---

### Task 1: Retrieval and propose tools

**Files:**
- Modify: `kernel/db/custodian_logged_items.py` (add `"contradiction_classification"` to `ITEM_TYPES`)
- Modify: `kernel/ai/custodian.py` (add `search_contradictions`, `propose_classify_contradiction`)
- Modify: `tests/kernel/test_custodian_engine.py`

**Interfaces:**
- Produces: `SEARCH_CONTRADICTIONS_TOOL`, `PROPOSE_CLASSIFY_CONTRADICTION_TOOL` constants; `OpenAICustodian.reply(...)`'s tool list grows to 13 and its dispatch routes `search_contradictions` to a new `_run_search_contradictions(conn, concept_id, limit)` and `propose_classify_contradiction` through the existing `_run_propose_tool` dispatch table.
- Consumes: `kernel.db.contradictions.ContradictionRepository.list`/`CLASSIFICATIONS`, `kernel.db.claims.ClaimRepository.get` (for both claims' text), `kernel.db.custodian_logged_items.CustodianLoggedItemRepository` (Plan 2).

- [ ] **Step 1: Extend ITEM_TYPES**

In `kernel/db/custodian_logged_items.py`, add one line to the existing set:

```python
ITEM_TYPES = {
    "observation",
    "note",
    "claim",
    "task",
    "concept_candidate",
    "reality_assertion",
    "perception_assertion",
    "contradiction",
    "importance_signal",
    "contradiction_classification",
}
```

- [ ] **Step 2: Add the tools**

In `kernel/ai/custodian.py`, add the import (`from kernel.db.contradictions import CLASSIFICATIONS, ContradictionRepository`) and, after `SEARCH_CONCEPTS_TOOL`:

```python
_RESOLVABLE_CLASSIFICATIONS = sorted(CLASSIFICATIONS - {"unresolved"})

SEARCH_CONTRADICTIONS_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "search_contradictions",
    "description": (
        "List unresolved contradictions — pairs of claims linked to the "
        "same concept that conflict. Returns both claims' text and the "
        "original detection rationale."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["concept_id", "limit"],
        "properties": {
            "concept_id": {
                "type": ["string", "null"],
                "description": "Restrict to one concept's contradictions, or null for all.",
            },
            "limit": {"type": "integer", "description": "Max results, 1-20."},
        },
    },
}

PROPOSE_CLASSIFY_CONTRADICTION_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_classify_contradiction",
    "description": (
        "Propose a classification for an existing unresolved contradiction "
        "(found via search_contradictions). Requires user acceptance."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["contradiction_id", "classification"],
        "properties": {
            "contradiction_id": {"type": "string"},
            "classification": {"type": "string", "enum": _RESOLVABLE_CLASSIFICATIONS},
        },
    },
}
```

`SEARCH_CONTRADICTIONS_TOOL` joins `SEARCH_ARCHIVE_TOOL`/`SEARCH_CONCEPTS_TOOL` as a third read-only tool passed directly in `reply()`'s `tools=[...]` list (updated below). `PROPOSE_CLASSIFY_CONTRADICTION_TOOL` joins the `_PROPOSE_TOOLS` tuple — replace Plan 2's 9-element tuple definition with this 10-element one:

```python
_PROPOSE_TOOLS = (
    PROPOSE_OBSERVATION_TOOL,
    PROPOSE_NOTE_TOOL,
    PROPOSE_CLAIM_TOOL,
    PROPOSE_TASK_TOOL,
    PROPOSE_CONCEPT_CANDIDATE_TOOL,
    PROPOSE_REALITY_ASSERTION_TOOL,
    PROPOSE_PERCEPTION_ASSERTION_TOOL,
    PROPOSE_CONTRADICTION_TOOL,
    PROPOSE_IMPORTANCE_SIGNAL_TOOL,
    PROPOSE_CLASSIFY_CONTRADICTION_TOOL,
)
```

and `_PROPOSE_TOOL_ITEM_TYPES` (Plan 2's dict) gains one more entry:

```python
    "propose_classify_contradiction": ("contradiction_classification", "contradiction_id"),
```

Update `reply()`'s `tools=[...]` line:

```python
                tools=[
                    SEARCH_ARCHIVE_TOOL,
                    SEARCH_CONCEPTS_TOOL,
                    SEARCH_CONTRADICTIONS_TOOL,
                    *_PROPOSE_TOOLS,
                ],
```

and add one more dispatch branch (alongside `search_archive`/`search_concepts`/the propose-tools check):

```python
                elif call.name == "search_contradictions":
                    output = await _run_search_contradictions(
                        conn, args["concept_id"], args["limit"]
                    )
```

- [ ] **Step 3: Add the retrieval executor**

Near `_run_search_concepts`, add:

```python
async def _run_search_contradictions(
    conn: Any, concept_id: str | None, limit: int
) -> str:
    contradictions = await ContradictionRepository(conn).list(
        concept_id=concept_id, classification="unresolved", limit=max(1, min(limit, 20))
    )
    claims = ClaimRepository(conn)
    payload = []
    for c in contradictions:
        claim_a = await claims.get(c.claim_a_id)
        claim_b = await claims.get(c.claim_b_id)
        if claim_a is None or claim_b is None:
            continue
        payload.append(
            {
                "contradiction_id": str(c.id),
                "concept_id": str(c.concept_id),
                "claim_a_text": claim_a.claim_text,
                "claim_b_text": claim_b.claim_text,
                "rationale": c.rationale,
            }
        )
    return json.dumps(payload)
```

Add `from kernel.db.claims import ClaimRepository` to the file's imports if not already present (check — `_run_search_archive` doesn't need it since `SemanticVectorRepository.search_similar` already returns claim objects inline, so this is likely a new import for this file).

- [ ] **Step 4: Write the failing tests**

In `tests/kernel/test_custodian_engine.py`, add:

```python
@pytest.mark.asyncio
async def test_reply_executes_search_contradictions_tool(make_user):
    from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
    from kernel.db.concept_candidates import ConceptCandidateRepository
    from kernel.db.contradictions import ContradictionRepository
    from kernel.db.observations import ObservationRepository
    from kernel.db.sources import SourceRepository

    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "engine-contra-1")
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Weather", concept_type="idea"
        )
        [obs_a, obs_b] = await ObservationRepository(conn).bulk_insert(
            [{"content": "It rained."}, {"content": "It was sunny."}], source.id, user_id
        )
        claim_repo = ClaimRepository(conn)
        claim_a = await claim_repo.create(
            user_id=user_id, source_id=source.id, observation_id=obs_a,
            claim_text="It rained.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        claim_b = await claim_repo.create(
            user_id=user_id, source_id=source.id, observation_id=obs_b,
            claim_text="It was sunny.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        assert claim_a is not None and claim_b is not None
        candidate_repo = ConceptCandidateRepository(conn)
        edge_repo = ClaimConceptEdgeRepository(conn)
        for claim in (claim_a, claim_b):
            candidate = await candidate_repo.create(
                user_id=user_id, source_id=source.id, claim_id=claim.id,
                candidate_name="Weather", concept_type="idea", rationale=None,
                confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
            )
            await edge_repo.create(
                user_id=user_id, claim_id=claim.id, concept_id=concept.id,
                concept_candidate_id=candidate.id, confidence=0.9,
            )
        await ContradictionRepository(conn).create(
            user_id=user_id, concept_id=concept.id, claim_a_id=claim_a.id,
            claim_b_id=claim_b.id, similarity=0.8, rationale="They disagree.",
        )

    call_args = json.dumps({"concept_id": None, "limit": 5})
    fake_client = FakeOpenAIClient(
        [
            (
                [],
                _FakeResponse(
                    "resp_1",
                    [_FunctionCall("call_1", "search_contradictions", call_args)],
                ),
            ),
            ([_Delta("Found one.")], _FakeResponse("resp_2", [])),
        ]
    )
    custodian = OpenAICustodian(api_key="x", model="gpt-4o-mini", client=fake_client)

    async with session(user_id) as conn:
        reply, tokens, tool_calls = await _collect_reply(
            custodian, conn, user_id, [{"role": "user", "content": "any contradictions?"}]
        )

    assert reply.content == "Found one."
    output = json.loads(tool_calls[0].tool_output)
    assert output[0]["claim_a_text"] == "It rained."
    assert output[0]["claim_b_text"] == "It was sunny."


@pytest.mark.asyncio
async def test_reply_executes_propose_classify_contradiction_tool(make_user):
    from uuid import uuid4

    user_id = await make_user()
    contradiction_id = uuid4()
    call_args = json.dumps(
        {"contradiction_id": str(contradiction_id), "classification": "evolution"}
    )
    fake_client = FakeOpenAIClient(
        [
            (
                [],
                _FakeResponse(
                    "resp_1",
                    [_FunctionCall("call_1", "propose_classify_contradiction", call_args)],
                ),
            ),
            ([], _FakeResponse("resp_2", [])),
        ]
    )
    custodian = OpenAICustodian(api_key="x", model="gpt-4o-mini", client=fake_client)

    async with session(user_id) as conn:
        from kernel.db.custodian import CustodianRepository
        from kernel.db.custodian_logged_items import CustodianLoggedItemRepository

        custodian_session = await CustodianRepository(conn).create_session(
            user_id=user_id, model="gpt-4o-mini", provider="openai"
        )
        tool_calls: list[ToolCallRecord] = []

        async def on_token(delta: str) -> None:
            pass

        async def on_tool_call(record: ToolCallRecord) -> None:
            tool_calls.append(record)

        await custodian.reply(
            conn, user_id, custodian_session.id, [{"role": "user", "content": "classify it"}],
            on_token, on_tool_call,
        )
        proposal_id = json.loads(tool_calls[0].tool_output)["proposal_id"]
        item = await CustodianLoggedItemRepository(conn).get(proposal_id)

    assert item is not None
    assert item.item_type == "contradiction_classification"
    assert item.target_id == contradiction_id
    assert item.content == {"classification": "evolution"}
```

Check the top of `tests/kernel/test_custodian_engine.py` for its existing `ConceptRepository`/`ClaimRepository`/`session` imports before adding these — they should already be there from Plan 1/2's tests in this file.

- [ ] **Step 5: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_custodian_engine.py -k "contradiction" -v`
Expected: FAIL — `KeyError`/`AttributeError` (tool not yet recognized).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_custodian_engine.py -v`
Expected: all pass (9 total: 5 from Plan 1, 2 from Plan 2, these 2).

- [ ] **Step 7: Commit**

```bash
git add kernel/db/custodian_logged_items.py kernel/ai/custodian.py tests/kernel/test_custodian_engine.py
git commit -m "feat: add search_contradictions and propose_classify_contradiction tools"
```

---

### Task 2: Accept orchestration

**Files:**
- Modify: `kernel/custodian_logging.py` (add the `contradiction_classification` branch)
- Modify: `tests/kernel/test_custodian_logging.py`

**Interfaces:**
- Produces: `accept_logged_item` handles `item_type == "contradiction_classification"`.
- Consumes: `kernel.db.contradictions.ContradictionRepository.classify` (Phase 2 Plan 2).

- [ ] **Step 1: Add the branch**

In `kernel/custodian_logging.py`, add the import (`from kernel.db.contradictions import ContradictionRepository`) and, in `accept_logged_item`'s `if/elif` chain, add:

```python
    elif item.item_type == "contradiction_classification":
        classified = await ContradictionRepository(conn).classify(
            item.target_id, item.content["classification"]
        )
        if classified is None:
            raise LoggedItemNotResolvable(
                message="target contradiction not found", reason="not_found"
            )
```

(No `new_target_id` assignment needed — `target_id` was already set at proposal time, same as `reality_assertion`/`perception_assertion`.)

- [ ] **Step 2: Write the failing tests**

In `tests/kernel/test_custodian_logging.py`, add the import (`from kernel.db.contradictions import ContradictionRepository`) and:

```python
@pytest.mark.asyncio
async def test_accept_contradiction_classification_classifies_it(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "logging-classify-1")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Weather", description=None
        )
        [obs_a, obs_b] = await ObservationRepository(conn).bulk_insert(
            [{"content": "It rained."}, {"content": "It was sunny."}], source.id, user_id
        )
        claim_a = await ClaimRepository(conn).create(
            user_id=user_id, source_id=source.id, observation_id=obs_a,
            claim_text="It rained.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        claim_b = await ClaimRepository(conn).create(
            user_id=user_id, source_id=source.id, observation_id=obs_b,
            claim_text="It was sunny.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        assert claim_a is not None and claim_b is not None
        contradiction = await ContradictionRepository(conn).create(
            user_id=user_id, concept_id=concept.id, claim_a_id=claim_a.id,
            claim_b_id=claim_b.id, similarity=0.8, rationale="They disagree.",
        )
        assert contradiction is not None
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "contradiction_classification",
            {"classification": "evolution"}, target_id=contradiction.id,
        )
        accepted = await accept_logged_item(conn, item.id)
        classified = await ContradictionRepository(conn).get(contradiction.id)

    assert accepted.status == "accepted"
    assert classified is not None
    assert classified.classification == "evolution"


@pytest.mark.asyncio
async def test_accept_contradiction_classification_raises_not_found_for_bad_target(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "contradiction_classification",
            {"classification": "evolution"},
            target_id="00000000-0000-0000-0000-000000000000",
        )

        with pytest.raises(LoggedItemNotResolvable) as exc_info:
            await accept_logged_item(conn, item.id)

    assert exc_info.value.reason == "not_found"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_custodian_logging.py -k contradiction_classification -v`
Expected: FAIL — no branch handles this `item_type`, `accept_logged_item` falls through every `if/elif` without raising or assigning, then `items.resolve(...)` still runs and "succeeds" with no real effect, so the assertion on `classified.classification == "evolution"` fails (the row was never classified).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_custodian_logging.py -v`
Expected: all pass (13 total: 11 from Plan 2, these 2).

- [ ] **Step 5: Commit**

```bash
git add kernel/custodian_logging.py tests/kernel/test_custodian_logging.py
git commit -m "feat: accept a contradiction_classification proposal via ContradictionRepository.classify"
```

---

### Task 3: Shared auto-enqueue and the API wiring

**Files:**
- Modify: `backend/app/api/contradictions.py` (extract `maybe_enqueue_revision_synthesis`)
- Modify: `backend/app/api/custodian.py` (call it after accepting a `contradiction_classification`)
- Modify: `tests/backend/test_contradictions_api.py` (existing tests still pass — no new ones needed here, since behavior is unchanged for this endpoint)
- Modify: `tests/backend/test_custodian_api.py`

**Interfaces:**
- Produces: `maybe_enqueue_revision_synthesis(user_id: str, contradiction_id: str, classification: str) -> None`, exported from `backend/app/api/contradictions.py`.
- Consumes: `kernel.custodian_logging.accept_logged_item` (Plan 2/Task 2 above), `kernel.db.jobs.JobRepository`, `worker.tasks.create_revision.create_revision`.

- [ ] **Step 1: Extract the function**

In `backend/app/api/contradictions.py`, replace the inline block inside `classify_contradiction` with a call to a new standalone function. Add the function right after `_serialize_contradiction`:

```python
async def maybe_enqueue_revision_synthesis(
    user_id: str, contradiction_id: str, classification: str
) -> None:
    """Auto-enqueue revision synthesis when a contradiction is classified
    'evolution'. Must be called AFTER the classify transaction commits, never
    from inside the same session() block that performed the classify —
    sending the dramatiq message before commit risks create_revision reading
    a contradiction row that isn't visible yet under READ COMMITTED
    isolation (the bug Phase 2 Plan 2's auto-enqueue wiring already fixed
    once). Called from both this module's classify endpoint and the
    Custodian Logging accept endpoint, so both classify paths behave
    identically."""
    if classification != "evolution":
        return
    try:
        async with session(user_id) as conn:
            revision_job = await JobRepository(conn).create(
                user_id, "create_revision", payload={"contradiction_id": contradiction_id}
            )
        create_revision.send(contradiction_id, user_id, str(revision_job.id))
    except Exception as exc:
        logger.warning(
            "failed to auto-enqueue create_revision for contradiction %s: %s",
            contradiction_id,
            exc,
        )
```

Replace the endpoint's tail:

```python
@router.post("/contradictions/{contradiction_id}/classify")
async def classify_contradiction(
    contradiction_id: str,
    body: ClassifyBody,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    if body.classification not in CLASSIFICATIONS:
        raise HTTPException(
            status_code=422,
            detail=f"classification must be one of {sorted(CLASSIFICATIONS)}",
        )
    async with session(user_id) as conn:
        contradiction = await ContradictionRepository(conn).classify(
            contradiction_id, body.classification
        )
        if contradiction is None:
            raise HTTPException(status_code=404, detail="not found")
        claims = ClaimRepository(conn)
        serialized = await _serialize_contradiction(contradiction, claims)
    assert serialized is not None
    await maybe_enqueue_revision_synthesis(user_id, contradiction_id, body.classification)
    return serialized
```

Run: `pytest tests/backend/test_contradictions_api.py -v`
Expected: all pass unchanged — this is a pure refactor, `test_classify_evolution_auto_enqueues_revision_creation` and `test_classify_non_evolution_does_not_enqueue_revision_creation` (Phase 2 Plan 2's existing tests) should still pass exactly as before since `monkeypatch.setattr("backend.app.api.contradictions.create_revision.send", ...)` still patches the same call site, just one function deeper.

- [ ] **Step 2: Wire it into the Custodian accept endpoint**

In `backend/app/api/custodian.py`, add the import (`from backend.app.api.contradictions import maybe_enqueue_revision_synthesis`) and change `accept_logged_item_endpoint`:

```python
@router.post("/custodian/logged-items/{item_id}/accept")
async def accept_logged_item_endpoint(
    item_id: str, user_id: str = Depends(get_current_user)
) -> dict[str, Any]:
    async with session(user_id) as conn:
        try:
            item = await accept_logged_item(conn, item_id)
        except LoggedItemNotResolvable as exc:
            raise HTTPException(
                status_code=_RESOLVE_STATUS_CODES[exc.reason], detail=exc.message
            ) from None
    if item.item_type == "contradiction_classification":
        await maybe_enqueue_revision_synthesis(
            user_id, str(item.target_id), item.content["classification"]
        )
    return _serialize_logged_item(item)
```

- [ ] **Step 3: Write the failing tests**

In `tests/backend/test_custodian_api.py`, add:

```python
@pytest.mark.asyncio
async def test_accepting_evolution_classification_enqueues_revision_creation(  # type: ignore[no-untyped-def]
    client, seeded_user, monkeypatch
):
    from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
    from kernel.db.concept_candidates import ConceptCandidateRepository
    from kernel.db.concepts import ConceptRepository
    from kernel.db.contradictions import ContradictionRepository
    from kernel.db.custodian import CustodianRepository
    from kernel.db.observations import ObservationRepository

    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.contradictions.create_revision.send",
        lambda *args: sent.append(args),
    )

    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "custodian-classify-1")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=seeded_user, concept_type="idea", concept_name="Weather", description=None
        )
        [obs_a, obs_b] = await ObservationRepository(conn).bulk_insert(
            [{"content": "It rained."}, {"content": "It was sunny."}], source.id, seeded_user
        )
        claim_repo = ClaimRepository(conn)
        claim_a = await claim_repo.create(
            user_id=seeded_user, source_id=source.id, observation_id=obs_a,
            claim_text="It rained.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        claim_b = await claim_repo.create(
            user_id=seeded_user, source_id=source.id, observation_id=obs_b,
            claim_text="It was sunny.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        assert claim_a is not None and claim_b is not None
        candidate_repo = ConceptCandidateRepository(conn)
        edge_repo = ClaimConceptEdgeRepository(conn)
        for claim in (claim_a, claim_b):
            candidate = await candidate_repo.create(
                user_id=seeded_user, source_id=source.id, claim_id=claim.id,
                candidate_name="Weather", concept_type="idea", rationale=None,
                confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
            )
            await edge_repo.create(
                user_id=seeded_user, claim_id=claim.id, concept_id=concept.id,
                concept_candidate_id=candidate.id, confidence=0.9,
            )
        contradiction = await ContradictionRepository(conn).create(
            user_id=seeded_user, concept_id=concept.id, claim_a_id=claim_a.id,
            claim_b_id=claim_b.id, similarity=0.8, rationale="They disagree.",
        )
        assert contradiction is not None
        custodian_session = await CustodianRepository(conn).create_session(
            user_id=seeded_user, model="gpt-4o-mini", provider="openai"
        )
        item = await CustodianLoggedItemRepository(conn).create(
            user_id=seeded_user, session_id=custodian_session.id,
            item_type="contradiction_classification", content={"classification": "evolution"},
            target_id=contradiction.id,
        )

    await _login(client)
    r = await client.post(f"/custodian/logged-items/{item.id}/accept")

    assert r.status_code == 200
    assert len(sent) == 1

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_logged_items"))
        await conn.execute(text("DELETE FROM custodian_sessions"))
        await conn.execute(text("DELETE FROM contradictions"))
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_accepting_non_evolution_classification_does_not_enqueue(  # type: ignore[no-untyped-def]
    client, seeded_user, monkeypatch
):
    from kernel.db.custodian import CustodianRepository

    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.contradictions.create_revision.send",
        lambda *args: sent.append(args),
    )

    async with session(seeded_user) as conn:
        custodian_session = await CustodianRepository(conn).create_session(
            user_id=seeded_user, model="gpt-4o-mini", provider="openai"
        )
        item = await CustodianLoggedItemRepository(conn).create(
            user_id=seeded_user, session_id=custodian_session.id,
            item_type="contradiction_classification",
            content={"classification": "true_conflict"},
            target_id="00000000-0000-0000-0000-000000000000",
        )

    await _login(client)
    r = await client.post(f"/custodian/logged-items/{item.id}/accept")

    assert r.status_code == 404
    assert sent == []

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_logged_items"))
        await conn.execute(text("DELETE FROM custodian_sessions"))
```

`test_accepting_non_evolution_classification_does_not_enqueue` deliberately targets a nonexistent contradiction (simpler fixture than seeding a real one, since the point of this test is "no enqueue," and a 404 from `accept_logged_item`'s own not-found check proves the enqueue call is never reached — the classification value itself doesn't matter for that assertion).

- [ ] **Step 4: Run the tests to verify they fail**

Run: `pytest tests/backend/test_custodian_api.py -k "revision" -v`
Expected: FAIL — `sent` stays empty for the evolution case (the accept endpoint doesn't call `maybe_enqueue_revision_synthesis` yet).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/backend/test_custodian_api.py tests/backend/test_contradictions_api.py -v`
Expected: all pass.

- [ ] **Step 6: Run the full backend suite**

Run: `pytest tests/kernel/ tests/backend/ -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/contradictions.py backend/app/api/custodian.py \
  tests/backend/test_custodian_api.py
git commit -m "feat: enqueue revision synthesis when Custodian-accepted classification is evolution"
```

---

### Task 4: Frontend

**Files:**
- Modify: `frontend/src/components/custodian/ProposalCard.tsx` (add the `contradiction_classification` case)
- Modify: `frontend/src/components/custodian/custodian.test.tsx`

**Interfaces:** none new — extends `summarize()`'s existing `switch`.

- [ ] **Step 1: Add the case**

In `frontend/src/components/custodian/ProposalCard.tsx`'s `summarize` function, add one more `case` before `default`:

```tsx
    case "contradiction_classification":
      return `Classify contradiction as ${c.classification}`
```

- [ ] **Step 2: Write the failing test**

In `frontend/src/components/custodian/custodian.test.tsx`, add:

```tsx
it("summarizes a contradiction_classification proposal", async () => {
  mockCreate.mockResolvedValueOnce({
    id: "s1",
    title: null,
    startedAt: "2024-05-12T14:32:01Z",
    endedAt: null,
    model: "gpt-4o-mini",
    provider: "openai",
  })
  const proposal = {
    id: "p1",
    sessionId: "s1",
    itemType: "contradiction_classification",
    targetId: "c1",
    content: { classification: "evolution" },
    status: "proposed" as const,
    createdAt: "2024-05-12T14:32:01Z",
    resolvedAt: null,
  }
  vi.mocked(listLoggedItems).mockResolvedValueOnce([]).mockResolvedValueOnce([proposal])
  mockStream.mockImplementationOnce(async (_id, _content, handlers) => {
    handlers.onDone()
  })

  renderOrb()
  await userEvent.click(screen.getByLabelText("Open the Custodian"))
  await userEvent.type(screen.getByPlaceholderText("Ask the Custodian..."), "classify it")
  await userEvent.keyboard("{Enter}")

  await waitFor(() => {
    expect(screen.getByText("Classify contradiction as evolution")).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the tests**

Run: `cd frontend && npx vitest run src/components/custodian/custodian.test.tsx`
Expected: 4 passed (3 from Plan 2, this one).

- [ ] **Step 4: Run the full frontend suite and type-check**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/custodian
git commit -m "feat: render contradiction_classification proposals in the chat panel"
```

---

### Task 5: Docs

**Files:**
- Modify: `README.md` (add a "Phase 3 Custodian-Assisted Contradiction Classification" section)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add the README section**

After the "Phase 3 Custodian Logging" section (added by Plan 2), add:

```markdown
## Phase 3 Custodian-Assisted Contradiction Classification

Per ADR-005 ("the user, assisted by the Custodian, can classify [contradictions]
later"), the Custodian can find unresolved contradictions
(`search_contradictions`) and propose a classification for one
(`propose_classify_contradiction`) — the tenth `custodian_logged_items` item
type, going through the same accept/reject review as everything else
Custodian Logging proposes. Accepting one calls the same
`ContradictionRepository.classify` the `/contradictions` page's button
calls, including the `evolution` → auto-enqueued revision synthesis, via a
`maybe_enqueue_revision_synthesis` helper shared between both classify
paths so they behave identically regardless of which one a user takes. This
completes Phase 3 (Custodian). See
[docs/superpowers/specs/2026-07-09-custodian-contradiction-assist-design.md](docs/superpowers/specs/2026-07-09-custodian-contradiction-assist-design.md).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document Custodian-assisted contradiction classification"
```

---

## Final Verification

- [ ] Run the full test suite: `pytest && (cd frontend && npx vitest run && npx tsc --noEmit)`
- [ ] Run `ruff check kernel/ backend/ worker/` and `mypy kernel/ backend/ worker/`.
- [ ] Manually smoke-test: find an unresolved contradiction via `/contradictions`, ask the Custodian about it, accept a proposed classification, confirm it shows up classified on `/contradictions` and (for `evolution`) a revision appears on the concept's `/concepts/{id}` page.
