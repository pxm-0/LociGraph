from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kernel.db.concepts import ConceptRepository
from kernel.db.session import session


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_create_manual_revision_updates_concept_and_records_history(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).find_or_create(
            user_id=seeded_user,
            concept_type="idea",
            concept_name="Manual Concept",
            description="Original.",
        )

    await _login(client)
    r = await client.post(
        f"/concepts/{concept.id}/revisions",
        json={"new_description": "Rewritten by hand.", "rationale": "I know better."},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "manual"
    assert body["contradiction_id"] is None
    assert body["previous_description"] == "Original."
    assert body["new_description"] == "Rewritten by hand."
    assert body["rationale"] == "I know better."

    concept_r = await client.get(f"/concepts/{concept.id}")
    assert concept_r.json()["description"] == "Rewritten by hand."

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM revisions"))
        await conn.execute(text("DELETE FROM concepts"))


@pytest.mark.asyncio
async def test_create_manual_revision_404s_for_unknown_concept(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/concepts/00000000-0000-0000-0000-000000000000/revisions",
        json={"new_description": "x", "rationale": None},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_revisions_returns_newest_first(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).find_or_create(
            user_id=seeded_user,
            concept_type="idea",
            concept_name="History Concept",
            description=None,
        )

    await _login(client)
    first = await client.post(
        f"/concepts/{concept.id}/revisions",
        json={"new_description": "First.", "rationale": None},
    )
    second = await client.post(
        f"/concepts/{concept.id}/revisions",
        json={"new_description": "Second.", "rationale": None},
    )
    listing = await client.get(f"/concepts/{concept.id}/revisions")

    assert first.status_code == 200
    assert second.status_code == 200
    assert listing.status_code == 200
    body = listing.json()
    assert [r["new_description"] for r in body] == ["Second.", "First."]

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM revisions"))
        await conn.execute(text("DELETE FROM concepts"))
