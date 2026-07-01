from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    jwt_secret: str
    locigraph_email: str
    locigraph_password: str
    raw_storage_path: str
    cookie_secure: bool
    active_ai_provider: str
    openai_api_key: str | None
    openai_extraction_model: str
    claim_extraction_autorun: bool
    claim_extraction_batch_size: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ["DATABASE_URL"],
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379"),
            jwt_secret=os.environ["JWT_SECRET"],
            locigraph_email=os.environ["LOCIGRAPH_EMAIL"],
            locigraph_password=os.environ["LOCIGRAPH_PASSWORD"],
            raw_storage_path=os.environ.get("RAW_STORAGE_PATH", "/data/raw"),
            cookie_secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_extraction_model=os.environ.get(
                "OPENAI_EXTRACTION_MODEL", "gpt-4o-mini"
            ),
            claim_extraction_autorun=os.environ.get(
                "CLAIM_EXTRACTION_AUTORUN", "false"
            ).lower()
            == "true",
            claim_extraction_batch_size=max(
                1, int(os.environ.get("CLAIM_EXTRACTION_BATCH_SIZE", "12"))
            ),
        )
