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
        )
