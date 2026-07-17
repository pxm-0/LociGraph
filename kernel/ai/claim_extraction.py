from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from kernel.models import Observation

logger = logging.getLogger(__name__)

PROMPT_VERSION = "claim-extraction-v2"
CLAIM_TYPES = {
    "fact",
    "event",
    "belief",
    "preference",
    "definition",
    "relationship",
    "emotion",
    "interpretation",
    "decision",
    "task",
}
ASSERTION_TYPES = {"reality", "perception", "interpretation"}

# ponytail: backfill-only map mirroring migration 0008's SQL CASE statement —
# new claims are always LLM-classified via ASSERTION_TYPES above, never
# derived from this table. Kept here only so a test can assert every
# CLAIM_TYPES value has an entry, catching drift if the taxonomy grows.
CLAIM_TYPE_TO_ASSERTION_TYPE_BACKFILL: dict[str, str] = {
    "fact": "reality",
    "event": "reality",
    "relationship": "reality",
    "decision": "reality",
    "task": "reality",
    "emotion": "perception",
    "preference": "perception",
    "belief": "interpretation",
    "interpretation": "interpretation",
    "definition": "interpretation",
}
CONCEPT_TYPES = {
    "idea",
    "person",
    "place",
    "object",
    "event",
    "system",
    "value",
    "belief",
    "theme",
    "project",
}


@dataclass(frozen=True, slots=True)
class ClaimExtractionSettings:
    active_ai_provider: str
    openai_api_key: str | None
    openai_extraction_model: str
    claim_extraction_autorun: bool
    claim_extraction_batch_size: int

    @classmethod
    def from_env(cls) -> ClaimExtractionSettings:
        return cls(
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_extraction_model=os.environ.get(
                "OPENAI_EXTRACTION_MODEL", "gpt-5.4-nano"
            ),
            claim_extraction_autorun=os.environ.get(
                "CLAIM_EXTRACTION_AUTORUN", "false"
            ).lower()
            == "true",
            claim_extraction_batch_size=max(
                1, int(os.environ.get("CLAIM_EXTRACTION_BATCH_SIZE", "12"))
            ),
        )


@dataclass(frozen=True, slots=True)
class ExtractedConceptCandidate:
    candidate_name: str
    concept_type: str
    confidence: float
    rationale: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    observation_id: UUID
    claim_text: str
    claim_type: str
    assertion_type: str
    confidence: float
    concept_candidates: list[ExtractedConceptCandidate] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClaimExtractionResult:
    claims: list[ExtractedClaim]
    extraction_method: str
    model_name: str | None
    prompt_version: str


def _as_float(value: object, field_name: str) -> float:
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    raise ValueError(f"{field_name} must be numeric")


def _parse_claim(raw_claim: object, observation_ids: set[UUID]) -> ExtractedClaim:
    if not isinstance(raw_claim, dict):
        raise ValueError("each claim must be an object")
    observation_id = UUID(str(raw_claim.get("observation_id")))
    if observation_id not in observation_ids:
        raise ValueError(f"unknown observation_id in extraction: {observation_id}")
    claim_text = str(raw_claim.get("claim_text", "")).strip()
    if not claim_text:
        raise ValueError("claim_text cannot be empty")
    claim_type = str(raw_claim.get("claim_type", "")).strip()
    if claim_type not in CLAIM_TYPES:
        raise ValueError(f"invalid claim_type: {claim_type}")
    assertion_type = str(raw_claim.get("assertion_type", "")).strip()
    if assertion_type not in ASSERTION_TYPES:
        raise ValueError(f"invalid assertion_type: {assertion_type}")

    candidates: list[ExtractedConceptCandidate] = []
    raw_candidates = raw_claim.get("concept_candidates", [])
    if not isinstance(raw_candidates, list):
        raise ValueError("concept_candidates must be an array")
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            raise ValueError("each concept candidate must be an object")
        candidate_name = str(raw_candidate.get("candidate_name", "")).strip()
        if not candidate_name:
            raise ValueError("candidate_name cannot be empty")
        concept_type = str(raw_candidate.get("concept_type", "")).strip()
        if concept_type not in CONCEPT_TYPES:
            raise ValueError(f"invalid concept_type: {concept_type}")
        candidates.append(
            ExtractedConceptCandidate(
                candidate_name=candidate_name,
                concept_type=concept_type,
                rationale=raw_candidate.get("rationale"),
                confidence=_as_float(raw_candidate.get("confidence"), "confidence"),
                metadata={"raw": raw_candidate},
            )
        )

    return ExtractedClaim(
        observation_id=observation_id,
        claim_text=claim_text,
        claim_type=claim_type,
        assertion_type=assertion_type,
        confidence=_as_float(raw_claim.get("confidence"), "confidence"),
        concept_candidates=candidates,
        metadata={"raw": raw_claim},
    )


def _parse_extraction_payload(
    payload: str,
    observation_ids: set[UUID],
    *,
    extraction_method: str,
    model_name: str | None,
) -> ClaimExtractionResult:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("claim extraction response must be a JSON object")
    raw_claims = data.get("claims")
    if not isinstance(raw_claims, list):
        raise ValueError("claim extraction response must include claims[]")

    # A single malformed claim (most commonly a hallucinated observation_id
    # the model failed to echo back verbatim) must not discard the rest of an
    # otherwise-valid batch or abort the whole extraction job — skip just
    # that claim and keep going.
    claims: list[ExtractedClaim] = []
    for raw_claim in raw_claims:
        try:
            claims.append(_parse_claim(raw_claim, observation_ids))
        except ValueError as exc:
            logger.warning("skipping malformed claim in extraction response: %s", exc)
    return ClaimExtractionResult(
        claims=claims,
        extraction_method=extraction_method,
        model_name=model_name,
        prompt_version=PROMPT_VERSION,
    )


class OpenAIClaimExtractor:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def extract(self, observations: Sequence[Observation]) -> ClaimExtractionResult:
        if not observations:
            return ClaimExtractionResult(
                claims=[],
                extraction_method="openai_structured_outputs",
                model_name=self.model,
                prompt_version=PROMPT_VERSION,
            )
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Extract atomic claims from observations. Return only claims "
                        "grounded in the supplied text. Suggest concept candidates as "
                        "non-canonical proposals. If an observation has no useful claim, "
                        "return no claim for it. For each claim, also classify "
                        "assertion_type: 'reality' for something that happened or is "
                        "objectively true, 'perception' for a felt or subjective "
                        "experience (an emotion or preference), or 'interpretation' for "
                        "an inferred belief or conclusion drawn from reality."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        [
                            {
                                "observation_id": str(obs.id),
                                "content": obs.content,
                                "speaker": obs.speaker,
                                "observed_at": obs.observed_at.isoformat()
                                if obs.observed_at
                                else None,
                            }
                            for obs in observations
                        ]
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "claim_extraction",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["claims"],
                        "properties": {
                            "claims": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "observation_id",
                                        "claim_text",
                                        "claim_type",
                                        "assertion_type",
                                        "confidence",
                                        "concept_candidates",
                                    ],
                                    "properties": {
                                        "observation_id": {"type": "string"},
                                        "claim_text": {"type": "string"},
                                        "claim_type": {
                                            "type": "string",
                                            "enum": sorted(CLAIM_TYPES),
                                        },
                                        "assertion_type": {
                                            "type": "string",
                                            "enum": sorted(ASSERTION_TYPES),
                                        },
                                        "confidence": {
                                            "type": "number",
                                            "minimum": 0,
                                            "maximum": 1,
                                        },
                                        "concept_candidates": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "required": [
                                                    "candidate_name",
                                                    "concept_type",
                                                    "confidence",
                                                    "rationale",
                                                ],
                                                "properties": {
                                                    "candidate_name": {"type": "string"},
                                                    "concept_type": {
                                                        "type": "string",
                                                        "enum": sorted(CONCEPT_TYPES),
                                                    },
                                                    "confidence": {
                                                        "type": "number",
                                                        "minimum": 0,
                                                        "maximum": 1,
                                                    },
                                                    "rationale": {
                                                        "type": ["string", "null"]
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                            }
                        },
                    },
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise ValueError("OpenAI response did not include output_text")
        return _parse_extraction_payload(
            output_text,
            {obs.id for obs in observations},
            extraction_method="openai_structured_outputs",
            model_name=self.model,
        )


def get_claim_extractor(settings: ClaimExtractionSettings | None = None) -> OpenAIClaimExtractor:
    settings = settings or ClaimExtractionSettings.from_env()
    if settings.active_ai_provider != "openai":
        raise ValueError(f"unsupported ACTIVE_AI_PROVIDER: {settings.active_ai_provider}")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when ACTIVE_AI_PROVIDER=openai")
    return OpenAIClaimExtractor(settings.openai_api_key, settings.openai_extraction_model)
