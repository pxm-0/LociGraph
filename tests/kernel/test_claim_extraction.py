from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from kernel.ai.claim_extraction import _parse_extraction_payload


def _payload(claims: list[dict]) -> str:
    return json.dumps({"claims": claims})


def _valid_claim(observation_id: UUID, text: str = "a claim") -> dict:
    return {
        "observation_id": str(observation_id),
        "claim_text": text,
        "claim_type": "fact",
        "confidence": 0.9,
        "concept_candidates": [],
    }


def test_parses_valid_claims():
    obs_a, obs_b = uuid4(), uuid4()
    result = _parse_extraction_payload(
        _payload([_valid_claim(obs_a, "first"), _valid_claim(obs_b, "second")]),
        {obs_a, obs_b},
        extraction_method="test",
        model_name="m",
    )
    assert [c.claim_text for c in result.claims] == ["first", "second"]


def test_skips_claim_with_unknown_observation_id_but_keeps_the_rest():
    known = uuid4()
    hallucinated = str(uuid4())
    payload = _payload(
        [
            {**_valid_claim(known, "good claim")},
            {
                "observation_id": hallucinated,
                "claim_text": "hallucinated claim",
                "claim_type": "fact",
                "confidence": 0.9,
                "concept_candidates": [],
            },
        ]
    )
    result = _parse_extraction_payload(
        payload, {known}, extraction_method="test", model_name="m"
    )
    assert [c.claim_text for c in result.claims] == ["good claim"]


def test_skips_claim_with_invalid_claim_type_but_keeps_the_rest():
    obs_a, obs_b = uuid4(), uuid4()
    bad = _valid_claim(obs_a, "bad type")
    bad["claim_type"] = "not-a-real-type"
    payload = _payload([bad, _valid_claim(obs_b, "good claim")])
    result = _parse_extraction_payload(
        payload, {obs_a, obs_b}, extraction_method="test", model_name="m"
    )
    assert [c.claim_text for c in result.claims] == ["good claim"]


def test_returns_empty_claims_when_every_claim_is_malformed():
    payload = _payload(
        [
            {
                "observation_id": str(uuid4()),
                "claim_text": "",
                "claim_type": "fact",
                "confidence": 0.9,
            }
        ]
    )
    result = _parse_extraction_payload(
        payload, {uuid4()}, extraction_method="test", model_name="m"
    )
    assert result.claims == []


def test_still_raises_when_claims_key_is_missing():
    with pytest.raises(ValueError, match="claims"):
        _parse_extraction_payload(
            json.dumps({}), {uuid4()}, extraction_method="test", model_name="m"
        )


def test_still_raises_when_response_is_not_a_json_object():
    with pytest.raises(ValueError, match="JSON object"):
        _parse_extraction_payload(
            json.dumps([1, 2, 3]), {uuid4()}, extraction_method="test", model_name="m"
        )
