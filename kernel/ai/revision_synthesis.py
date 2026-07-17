from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RevisionSynthesisSettings:
    active_ai_provider: str
    openai_api_key: str | None
    openai_revision_model: str

    @classmethod
    def from_env(cls) -> RevisionSynthesisSettings:
        return cls(
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_revision_model=os.environ.get("OPENAI_REVISION_MODEL", "gpt-5.4-mini"),
        )


@dataclass(frozen=True, slots=True)
class RevisionSynthesis:
    new_description: str
    rationale: str


def _parse_revision_payload(payload: str) -> RevisionSynthesis:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("revision synthesis response must be a JSON object")
    new_description = str(data.get("new_description", "")).strip()
    if not new_description:
        raise ValueError("new_description cannot be empty")
    rationale = str(data.get("rationale", "")).strip()
    if not rationale:
        raise ValueError("rationale cannot be empty")
    return RevisionSynthesis(new_description=new_description, rationale=rationale)


class OpenAIRevisionSynthesizer:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def synthesize(
        self,
        previous_description: str | None,
        claim_a_text: str,
        claim_a_assertion_type: str,
        claim_b_text: str,
        claim_b_assertion_type: str,
    ) -> RevisionSynthesis:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "A user has classified two claims as an evolution in "
                        "understanding of a concept, not a conflict — the second "
                        "claim supersedes or refines the first, it doesn't just "
                        "disagree with it. Given the concept's current description "
                        "(if any) and both claims, write an updated description "
                        "that incorporates the new understanding, and briefly "
                        "explain what changed."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "previous_description": previous_description,
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
                    "name": "revision_synthesis",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["new_description", "rationale"],
                        "properties": {
                            "new_description": {"type": "string"},
                            "rationale": {"type": "string"},
                        },
                    },
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise ValueError("OpenAI response did not include output_text")
        return _parse_revision_payload(output_text)


def get_revision_synthesizer(
    settings: RevisionSynthesisSettings | None = None,
) -> OpenAIRevisionSynthesizer:
    settings = settings or RevisionSynthesisSettings.from_env()
    if settings.active_ai_provider != "openai":
        raise ValueError(f"unsupported ACTIVE_AI_PROVIDER: {settings.active_ai_provider}")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when ACTIVE_AI_PROVIDER=openai")
    return OpenAIRevisionSynthesizer(settings.openai_api_key, settings.openai_revision_model)
