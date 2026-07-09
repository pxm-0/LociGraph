from __future__ import annotations

import json

import pytest

from kernel.ai.custodian import (
    CustodianSettings,
    OpenAICustodian,
    ToolCallRecord,
    _run_search_archive,
    _run_search_concepts,
)
from kernel.db.concepts import ConceptRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.session import session


def _pad_vector(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


class FakeEmbedder:
    async def embed(self, texts):  # type: ignore[no-untyped-def]
        return [_pad_vector([float(len(t)), 0.0]) for t in texts]


class _Delta:
    def __init__(self, delta: str) -> None:
        self.type = "response.output_text.delta"
        self.delta = delta


class _FunctionCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.type = "function_call"
        self.call_id = call_id
        self.name = name
        self.arguments = arguments


class _FakeResponse:
    def __init__(self, id_: str, output: list[object]) -> None:
        self.id = id_
        self.output = output


class _FakeStream:
    def __init__(self, events: list[object], response: _FakeResponse) -> None:
        self._events = events
        self._response = response

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def _aiter(self):  # type: ignore[no-untyped-def]
        for event in self._events:
            yield event

    def __aiter__(self):  # type: ignore[no-untyped-def]
        return self._aiter()

    async def get_final_response(self) -> _FakeResponse:
        return self._response


class _FakeResponsesClient:
    def __init__(self, rounds: list[tuple[list[object], _FakeResponse]]) -> None:
        self._rounds = list(rounds)
        self.calls: list[dict[str, object]] = []

    def stream(self, **kwargs: object) -> _FakeStream:
        self.calls.append(kwargs)
        events, response = self._rounds.pop(0)
        return _FakeStream(events, response)


class FakeOpenAIClient:
    def __init__(self, rounds: list[tuple[list[object], _FakeResponse]]) -> None:
        self.responses = _FakeResponsesClient(rounds)


_TEST_SESSION_ID = "00000000-0000-0000-0000-000000000000"


async def _collect_reply(custodian, conn, user_id, history):  # type: ignore[no-untyped-def]
    tokens: list[str] = []
    tool_calls: list[ToolCallRecord] = []

    async def on_token(delta: str) -> None:
        tokens.append(delta)

    async def on_tool_call(record: ToolCallRecord) -> None:
        tool_calls.append(record)

    reply = await custodian.reply(
        conn, user_id, _TEST_SESSION_ID, history, on_token, on_tool_call
    )
    return reply, tokens, tool_calls


@pytest.mark.asyncio
async def test_reply_with_no_tool_call_streams_and_assembles_content(make_user):
    user_id = await make_user()
    fake_client = FakeOpenAIClient(
        [([_Delta("Hello"), _Delta(" there.")], _FakeResponse("resp_1", []))]
    )
    custodian = OpenAICustodian(api_key="x", model="gpt-4o-mini", client=fake_client)

    async with session(user_id) as conn:
        reply, tokens, tool_calls = await _collect_reply(
            custodian, conn, user_id, [{"role": "user", "content": "hi"}]
        )

    assert tokens == ["Hello", " there."]
    assert reply.content == "Hello there."
    assert tool_calls == []
    assert fake_client.responses.calls[0]["previous_response_id"] is None


@pytest.mark.asyncio
async def test_reply_executes_search_concepts_tool_and_continues(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        await ConceptRepository(conn).create(
            user_id=user_id,
            concept_name="Sovereignty",
            concept_type="value",
            description="Self-determination.",
        )

    call_args = json.dumps({"query": "Sovereignty", "limit": 5})
    fake_client = FakeOpenAIClient(
        [
            (
                [],
                _FakeResponse(
                    "resp_1",
                    [_FunctionCall("call_1", "search_concepts", call_args)],
                ),
            ),
            ([_Delta("It means self-determination.")], _FakeResponse("resp_2", [])),
        ]
    )
    custodian = OpenAICustodian(api_key="x", model="gpt-4o-mini", client=fake_client)

    async with session(user_id) as conn:
        reply, tokens, tool_calls = await _collect_reply(
            custodian, conn, user_id, [{"role": "user", "content": "What is Sovereignty?"}]
        )

    assert reply.content == "It means self-determination."
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "search_concepts"
    output = json.loads(tool_calls[0].tool_output)
    assert output[0]["concept_name"] == "Sovereignty"
    second_call = fake_client.responses.calls[1]
    assert second_call["previous_response_id"] == "resp_1"
    assert second_call["input"][0]["call_id"] == "call_1"


@pytest.mark.asyncio
async def test_run_search_archive_returns_matching_claims(make_user, monkeypatch):
    from kernel.db.claims import ClaimRepository
    from kernel.db.observations import ObservationRepository
    from kernel.db.sources import SourceRepository

    user_id = await make_user()
    monkeypatch.setattr("kernel.ai.custodian.get_embedder", lambda settings: FakeEmbedder())

    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "custodian-engine-1")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "It rained yesterday."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="It rained yesterday.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        from kernel.db.semantic_vectors import SemanticVectorRepository

        await SemanticVectorRepository(conn).create(
            user_id=user_id,
            claim_id=claim.id,
            model_name="fake",
            embedding=_pad_vector([1.0, 0.0]),
        )

        output = json.loads(await _run_search_archive(conn, "weather", 5))

    assert output[0]["claim_text"] == "It rained yesterday."


@pytest.mark.asyncio
async def test_run_search_concepts_includes_revision_history(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=user_id,
            concept_name="Sovereignty",
            concept_type="value",
            description="Self-determination.",
        )
        assert concept is not None
        await RevisionRepository(conn).create(
            user_id=user_id,
            concept_id=concept.id,
            contradiction_id=None,
            source="manual",
            previous_description=None,
            new_description="Self-determination, updated.",
            rationale="Clarified wording.",
        )

        output = json.loads(await _run_search_concepts(conn, "sovereign", 5))

    assert output[0]["concept_name"] == "Sovereignty"
    assert output[0]["recent_revisions"][0]["new_description"] == "Self-determination, updated."


def test_settings_from_env_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_CUSTODIAN_MODEL", raising=False)
    monkeypatch.delenv("CUSTODIAN_MAX_MESSAGES_PER_SESSION", raising=False)

    settings = CustodianSettings.from_env()

    assert settings.openai_custodian_model == "gpt-4o-mini"
    assert settings.custodian_max_messages_per_session == 100
