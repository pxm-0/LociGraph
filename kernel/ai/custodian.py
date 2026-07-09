from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from kernel.ai.embeddings import EmbeddingSettings, get_embedder
from kernel.db.concepts import ConceptRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.semantic_vectors import SemanticVectorRepository

SYSTEM_PROMPT = (
    "You are the Custodian, a conversational guide to the user's personal "
    "knowledge archive (LociGraph). Use the search_archive tool to find "
    "relevant claims and the search_concepts tool to look up what the "
    "archive knows about a named concept, including how that understanding "
    "has changed over time. Answer only from what these tools return — if "
    "nothing relevant turns up, say so plainly rather than guessing. Be "
    "concise."
)

SEARCH_ARCHIVE_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "search_archive",
    "description": (
        "Semantic search over the user's claims — atomic statements "
        "extracted from their sources. Returns the most relevant claims."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["query", "limit"],
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "limit": {"type": "integer", "description": "Max results, 1-20."},
        },
    },
}

SEARCH_CONCEPTS_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "search_concepts",
    "description": (
        "Look up concepts by name (substring match). Returns each match's "
        "description and recent revision history."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["query", "limit"],
        "properties": {
            "query": {"type": "string", "description": "Concept name or part of it."},
            "limit": {"type": "integer", "description": "Max results, 1-20."},
        },
    },
}

# ponytail: bounded to 5 tool-call rounds — comfortably above any real chat
# turn (each round can batch multiple parallel tool calls); raise if a real
# conversation ever needs more back-and-forth than this.
_MAX_TOOL_ROUNDS = 5


@dataclass(frozen=True, slots=True)
class CustodianSettings:
    active_ai_provider: str
    openai_api_key: str | None
    openai_custodian_model: str
    custodian_max_messages_per_session: int

    @classmethod
    def from_env(cls) -> CustodianSettings:
        return cls(
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_custodian_model=os.environ.get("OPENAI_CUSTODIAN_MODEL", "gpt-4o-mini"),
            custodian_max_messages_per_session=max(
                1, int(os.environ.get("CUSTODIAN_MAX_MESSAGES_PER_SESSION", "100"))
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    tool_name: str
    tool_input: str
    tool_output: str


@dataclass(frozen=True, slots=True)
class CustodianReply:
    content: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


OnToken = Callable[[str], Awaitable[None]]
OnToolCall = Callable[[ToolCallRecord], Awaitable[None]]


async def _run_search_archive(conn: Any, query: str, limit: int) -> str:
    embedder = get_embedder(EmbeddingSettings.from_env())
    [query_embedding] = await embedder.embed([query])
    results = await SemanticVectorRepository(conn).search_similar(
        query_embedding, limit=max(1, min(limit, 20))
    )
    return json.dumps(
        [
            {
                "claim_text": r.claim.claim_text,
                "claim_type": r.claim.claim_type,
                "assertion_type": r.claim.assertion_type,
                "similarity": r.similarity,
            }
            for r in results
        ]
    )


async def _run_search_concepts(conn: Any, query: str, limit: int) -> str:
    concepts = await ConceptRepository(conn).search_by_name(query, limit=max(1, min(limit, 20)))
    revisions = RevisionRepository(conn)
    payload = []
    for concept in concepts:
        recent = await revisions.list(concept_id=concept.id, limit=5)
        payload.append(
            {
                "concept_name": concept.concept_name,
                "concept_type": concept.concept_type,
                "description": concept.description,
                "recent_revisions": [
                    {
                        "new_description": r.new_description,
                        "rationale": r.rationale,
                        "source": r.source,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in recent
                ],
            }
        )
    return json.dumps(payload)


class OpenAICustodian:
    def __init__(self, api_key: str, model: str, *, client: Any | None = None) -> None:
        self.api_key = api_key
        self.model = model
        # Injected in tests; created lazily in reply() otherwise — every
        # other kernel/ai/*.py module constructs AsyncOpenAI() inline per
        # call instead of storing it, but this module's tool-call loop is
        # non-trivial new logic worth unit-testing directly, so it accepts
        # an injected client the way no prior module here needed to.
        self._client = client

    async def reply(
        self,
        conn: Any,
        user_id: str | UUID,
        session_id: str | UUID,
        history: list[dict[str, str]],
        on_token: OnToken,
        on_tool_call: OnToolCall,
    ) -> CustodianReply:
        # session_id is unused by this plan's two read-only tools, but a
        # future plan (Custodian Logging) adds write-proposal tools that
        # need to know which session they're proposing into — accepting it
        # here now avoids a signature change once that plan lands.
        client = self._client
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)

        tool_calls: list[ToolCallRecord] = []
        content_parts: list[str] = []
        input_items: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
        ]
        previous_response_id: str | None = None

        for _ in range(_MAX_TOOL_ROUNDS):
            # input_items/tools are plain dicts (matching the fake-client tests'
            # duck-typed style) rather than the SDK's precise TypedDicts; the
            # real API accepts this shape at runtime, mypy just can't see it.
            async with client.responses.stream(
                model=self.model,
                input=input_items,  # type: ignore[arg-type]
                tools=[SEARCH_ARCHIVE_TOOL, SEARCH_CONCEPTS_TOOL],  # type: ignore[list-item]
                previous_response_id=previous_response_id,
            ) as stream:
                async for event in stream:
                    # Real SDK events are one of ~50 discriminated types; the
                    # fake-client tests use plain duck-typed objects too, so
                    # treat this as the dynamic value it actually is.
                    ev: Any = event
                    if ev.type == "response.output_text.delta":
                        content_parts.append(ev.delta)
                        await on_token(ev.delta)
                response = await stream.get_final_response()

            function_calls: list[Any] = [
                item for item in response.output if item.type == "function_call"
            ]
            if not function_calls:
                break

            follow_up: list[dict[str, Any]] = []
            for call in function_calls:
                args = json.loads(call.arguments)
                if call.name == "search_archive":
                    output = await _run_search_archive(conn, args["query"], args["limit"])
                elif call.name == "search_concepts":
                    output = await _run_search_concepts(conn, args["query"], args["limit"])
                else:
                    output = json.dumps({"error": f"unknown tool {call.name}"})
                record = ToolCallRecord(
                    tool_name=call.name,
                    tool_input=call.arguments,
                    tool_output=output,
                )
                tool_calls.append(record)
                await on_tool_call(record)
                follow_up.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output,
                    }
                )
            input_items = follow_up
            previous_response_id = response.id

        return CustodianReply(content="".join(content_parts), tool_calls=tool_calls)


def get_custodian(settings: CustodianSettings | None = None) -> OpenAICustodian:
    settings = settings or CustodianSettings.from_env()
    if settings.active_ai_provider != "openai":
        raise ValueError(f"unsupported ACTIVE_AI_PROVIDER: {settings.active_ai_provider}")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when ACTIVE_AI_PROVIDER=openai")
    return OpenAICustodian(settings.openai_api_key, settings.openai_custodian_model)
