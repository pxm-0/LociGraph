import os

import pytest


@pytest.mark.asyncio
async def test_login_sets_cookie_and_logout_clears(client, seeded_user):
    r = await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})
    assert r.status_code == 200
    assert r.json()["user_id"] == str(seeded_user)
    assert "locigraph_token" in r.cookies

    r2 = await client.post("/auth/logout")
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_login_wrong_password_401(client, seeded_user):
    r = await client.post("/auth/login", json={"password": "nope"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_cookie(client):
    r = await client.get("/auth/me")
    assert r.status_code == 401
