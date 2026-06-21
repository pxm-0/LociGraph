import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.auth.passwords import hash_password
from kernel.db.engine import dispose_engine, get_engine
from kernel.db.session import session
from worker.tasks.ingest_source import _ingest


@pytest.mark.asyncio
async def test_upload_then_ingest_then_query(monkeypatch):  # type: ignore[no-untyped-def]
    email = os.environ["LOCIGRAPH_EMAIL"]
    # seed the login user
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email=:e"), {"e": email})
        await conn.execute(
            text("INSERT INTO users (email, password_hash) VALUES (:e,:p)"),
            {"e": email, "p": hash_password(os.environ["LOCIGRAPH_PASSWORD"])},
        )

    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "backend.app.api.sources.submit_ingest",
        lambda sid, uid, jid: captured.update(sid=sid, uid=uid, jid=jid),
    )

    from backend.app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})
        up = await ac.post(
            "/sources/upload",
            data={"source_type": "json"},
            files={"file": ("c.json", b'[{"text":"gamma"},{"text":"delta"}]', "application/json")},
        )
        assert up.status_code == 202

        # run the worker pipeline directly (no live broker in tests)
        await _ingest(captured["sid"], captured["uid"], captured["jid"])

        status = await ac.get(f"/sources/{captured['sid']}")
        assert status.json()["import_status"] == "VERIFIED"

        obs = await ac.get("/observations")
        contents = {o["content"] for o in obs.json()}
    assert any("gamma" in c for c in contents) and any("delta" in c for c in contents)

    # cleanup: RLS-gated tables must be deleted inside session(user_id) so that
    # FORCE RLS resolves the current_user_id; users table has no RLS so it uses
    # the raw engine directly.
    uid = captured["uid"]
    async with session(uid) as conn:
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM fragments"))
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email=:e"), {"e": email})
    await dispose_engine()
