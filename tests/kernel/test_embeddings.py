import pytest

from kernel.ai.embeddings import EmbeddingSettings, OpenAIEmbedder, get_embedder


def test_embedding_settings_from_env_reads_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.delenv("EMBEDDING_AUTORUN", raising=False)
    monkeypatch.delenv("EMBEDDING_BATCH_SIZE", raising=False)

    settings = EmbeddingSettings.from_env()

    assert settings.openai_embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimensions == 1536
    assert settings.embedding_autorun is False
    assert settings.embedding_batch_size == 100


def test_embedding_settings_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "custom-model")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "256")
    monkeypatch.setenv("EMBEDDING_AUTORUN", "true")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "50")

    settings = EmbeddingSettings.from_env()

    assert settings.openai_embedding_model == "custom-model"
    assert settings.embedding_dimensions == 256
    assert settings.embedding_autorun is True
    assert settings.embedding_batch_size == 50


def test_get_embedder_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ACTIVE_AI_PROVIDER", "openai")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_embedder()


def test_get_embedder_raises_for_unsupported_provider(monkeypatch):
    monkeypatch.setenv("ACTIVE_AI_PROVIDER", "anthropic")

    with pytest.raises(ValueError, match="unsupported ACTIVE_AI_PROVIDER"):
        get_embedder()


@pytest.mark.asyncio
async def test_openai_embedder_returns_empty_list_for_empty_input():
    embedder = OpenAIEmbedder(api_key="sk-fake", model="text-embedding-3-small", dimensions=1536)
    result = await embedder.embed([])
    assert result == []
