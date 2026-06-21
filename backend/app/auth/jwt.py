from __future__ import annotations

from datetime import datetime, timedelta

import jwt

_ALG = "HS256"


def create_token(user_id: str, secret: str, *, now: datetime, ttl_days: int = 7) -> str:
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(days=ttl_days)}
    return jwt.encode(payload, secret, algorithm=_ALG)


def decode_token(token: str, secret: str) -> str:
    payload = jwt.decode(token, secret, algorithms=[_ALG])
    return str(payload["sub"])
