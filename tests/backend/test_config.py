from backend.app.config import Settings


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x/y")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("LOCIGRAPH_EMAIL", "a@b.com")
    monkeypatch.setenv("LOCIGRAPH_PASSWORD", "pw")
    monkeypatch.setenv("RAW_STORAGE_PATH", "/data/raw")
    s = Settings.from_env()
    assert s.database_url == "postgresql+asyncpg://x/y"
    assert s.jwt_secret == "secret"
    assert s.cookie_secure is False  # default in non-prod


def test_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    import pytest

    with pytest.raises(KeyError):
        Settings.from_env()
