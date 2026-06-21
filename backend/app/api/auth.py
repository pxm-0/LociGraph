from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.jwt import create_token
from backend.app.config import Settings
from kernel.auth.passwords import verify_password
from kernel.db.engine import get_engine
from kernel.db.users import UserRepository

router = APIRouter()


class LoginBody(BaseModel):
    password: str


@router.post("/auth/login")
async def login(body: LoginBody, response: Response) -> dict[str, str]:
    settings = Settings.from_env()
    engine = get_engine()
    async with engine.begin() as conn:
        repo = UserRepository(conn)
        user = await repo.get_by_email(settings.locigraph_email)
        stored_hash = await repo.verify_password_hash(settings.locigraph_email)
    if user is None or stored_hash is None or not verify_password(body.password, stored_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_token(str(user.id), settings.jwt_secret, now=datetime.now(UTC))
    response.set_cookie(
        "locigraph_token", token, httponly=True, samesite="lax",
        secure=settings.cookie_secure, path="/",
    )
    return {"user_id": str(user.id)}


@router.post("/auth/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("locigraph_token", path="/")
    return {"status": "logged out"}


@router.get("/auth/me")
async def me(user_id: str = Depends(get_current_user)) -> dict[str, str]:
    return {"user_id": user_id}
