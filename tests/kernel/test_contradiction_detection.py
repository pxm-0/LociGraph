from __future__ import annotations

import json

import pytest

from kernel.ai.contradiction_detection import ContradictionSettings, _parse_contradiction_payload


def test_parses_valid_contradiction_response():
    payload = json.dumps(
        {"is_contradiction": True, "rationale": "They disagree about the weather."}
    )
    result = _parse_contradiction_payload(payload)
    assert result.is_contradiction is True
    assert result.rationale == "They disagree about the weather."


def test_parses_non_contradiction_response():
    payload = json.dumps({"is_contradiction": False, "rationale": "Different topics."})
    result = _parse_contradiction_payload(payload)
    assert result.is_contradiction is False


def test_raises_when_is_contradiction_missing():
    with pytest.raises(ValueError, match="is_contradiction"):
        _parse_contradiction_payload(json.dumps({"rationale": "x"}))


def test_raises_when_rationale_empty():
    with pytest.raises(ValueError, match="rationale"):
        _parse_contradiction_payload(json.dumps({"is_contradiction": True, "rationale": "  "}))


def test_raises_when_response_is_not_a_json_object():
    with pytest.raises(ValueError, match="JSON object"):
        _parse_contradiction_payload(json.dumps([1, 2, 3]))


def test_settings_from_env_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_CONTRADICTION_MODEL", raising=False)
    monkeypatch.delenv("CONTRADICTION_CANDIDATE_LIMIT", raising=False)
    monkeypatch.delenv("CONTRADICTION_SIMILARITY_FLOOR", raising=False)
    monkeypatch.delenv("CONTRADICTION_AUTORUN", raising=False)

    settings = ContradictionSettings.from_env()

    assert settings.openai_contradiction_model == "gpt-5.4-mini"
    assert settings.contradiction_candidate_limit == 5
    assert settings.contradiction_similarity_floor == 0.75
    assert settings.contradiction_autorun is False
