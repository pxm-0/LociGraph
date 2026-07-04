from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from worker.broker import HEARTBEAT_TIMEOUT_MS, get_broker, run_actor


async def _noop() -> None:
    return None


async def _boom() -> None:
    raise ValueError("boom")


def test_run_actor_disposes_engine_after_success(monkeypatch):
    fake_dispose = AsyncMock()
    monkeypatch.setattr("worker.broker.dispose_engine", fake_dispose)
    run_actor(_noop())
    fake_dispose.assert_called_once()


def test_run_actor_disposes_engine_even_when_the_coroutine_raises(monkeypatch):
    fake_dispose = AsyncMock()
    monkeypatch.setattr("worker.broker.dispose_engine", fake_dispose)
    with pytest.raises(ValueError, match="boom"):
        run_actor(_boom())
    fake_dispose.assert_called_once()


def test_heartbeat_timeout_exceeds_extract_claims_time_limit():
    from worker.tasks.extract_claims import EXTRACT_CLAIMS_TIME_LIMIT_MS

    assert get_broker().heartbeat_timeout == HEARTBEAT_TIMEOUT_MS
    assert HEARTBEAT_TIMEOUT_MS > EXTRACT_CLAIMS_TIME_LIMIT_MS
