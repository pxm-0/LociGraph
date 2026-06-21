from __future__ import annotations

from fastapi import HTTPException, Request
from jwt import InvalidTokenError

from backend.app.auth.jwt import decode_token
from backend.app.config import Settings


def get_current_user(request: Request) -> str:
    token = request.cookies.get("locigraph_token")
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        return decode_token(token, Settings.from_env().jwt_secret)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token") from None
