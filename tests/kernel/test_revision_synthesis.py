from __future__ import annotations

import json

import pytest

from kernel.ai.revision_synthesis import RevisionSynthesisSettings, _parse_revision_payload


def test_parses_valid_synthesis_response():
    payload = json.dumps(
        {
            "new_description": "The project moved from a monolith to microservices.",
            "rationale": "The second claim describes a completed migration.",
        }
    )
    result = _parse_revision_payload(payload)
    assert result.new_description == "The project moved from a monolith to microservices."
    assert result.rationale == "The second claim describes a completed migration."


def test_raises_when_new_description_empty():
    with pytest.raises(ValueError, match="new_description"):
        _parse_revision_payload(json.dumps({"new_description": "  ", "rationale": "x"}))


def test_raises_when_rationale_empty():
    with pytest.raises(ValueError, match="rationale"):
        _parse_revision_payload(json.dumps({"new_description": "x", "rationale": "  "}))


def test_raises_when_response_is_not_a_json_object():
    with pytest.raises(ValueError, match="JSON object"):
        _parse_revision_payload(json.dumps([1, 2, 3]))


def test_settings_from_env_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_REVISION_MODEL", raising=False)

    settings = RevisionSynthesisSettings.from_env()

    assert settings.openai_revision_model == "gpt-5.4-mini"
