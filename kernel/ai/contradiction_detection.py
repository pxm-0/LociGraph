from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContradictionSettings:
    active_ai_provider: str
    openai_api_key: str | None
    openai_contradiction_model: str
    contradiction_candidate_limit: int
    contradiction_similarity_floor: float
    contradiction_autorun: bool

    @classmethod
    def from_env(cls) -> ContradictionSettings:
        return cls(
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_contradiction_model=os.environ.get(
                "OPENAI_CONTRADICTION_MODEL", "gpt-5.4-mini"
            ),
            contradiction_candidate_limit=max(
                1, int(os.environ.get("CONTRADICTION_CANDIDATE_LIMIT", "5"))
            ),
            contradiction_similarity_floor=float(
                os.environ.get("CONTRADICTION_SIMILARITY_FLOOR", "0.75")
            ),
            contradiction_autorun=os.environ.get("CONTRADICTION_AUTORUN", "false").lower()
            == "true",
        )


@dataclass(frozen=True, slots=True)
class ContradictionCheck:
    is_contradiction: bool
    rationale: str


def _parse_contradiction_payload(payload: str) -> ContradictionCheck:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("contradiction detection response must be a JSON object")
    is_contradiction = data.get("is_contradiction")
    if not isinstance(is_contradiction, bool):
        raise ValueError("is_contradiction must be a boolean")
    rationale = str(data.get("rationale", "")).strip()
    if not rationale:
        raise ValueError("rationale cannot be empty")
    return ContradictionCheck(is_contradiction=is_contradiction, rationale=rationale)


class OpenAIContradictionDetector:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def check(
        self,
        claim_a_text: str,
        claim_a_assertion_type: str,
        claim_b_text: str,
        claim_b_assertion_type: str,
    ) -> ContradictionCheck:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Given two claims, decide whether they contradict each other — "
                        "state opposing facts, incompatible beliefs, or conflicting "
                        "accounts of the same thing. Two claims about different topics, "
                        "or a fact alongside an unrelated feeling, are not contradictions. "
                        "Explain your reasoning briefly."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "claim_a": {
                                "text": claim_a_text,
                                "assertion_type": claim_a_assertion_type,
                            },
                            "claim_b": {
                                "text": claim_b_text,
                                "assertion_type": claim_b_assertion_type,
                            },
                        }
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "contradiction_check",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["is_contradiction", "rationale"],
                        "properties": {
                            "is_contradiction": {"type": "boolean"},
                            "rationale": {"type": "string"},
                        },
                    },
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise ValueError("OpenAI response did not include output_text")
        return _parse_contradiction_payload(output_text)


def get_contradiction_detector(
    settings: ContradictionSettings | None = None,
) -> OpenAIContradictionDetector:
    settings = settings or ContradictionSettings.from_env()
    if settings.active_ai_provider != "openai":
        raise ValueError(f"unsupported ACTIVE_AI_PROVIDER: {settings.active_ai_provider}")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when ACTIVE_AI_PROVIDER=openai")
    return OpenAIContradictionDetector(
        settings.openai_api_key, settings.openai_contradiction_model
    )
