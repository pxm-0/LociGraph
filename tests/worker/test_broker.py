from __future__ import annotations

import pytest

from worker.broker import run_actor


async def _noop() -> None:
    return None


async def _boom() -> None:
    raise ValueError("boom")


def test_run_actor_disposes_engine_after_success(monkeypatch):
    disposed = []
    monkeypatch.setattr(
        "worker.broker.dispose_engine",
        lambda: _record(disposed),
    )
    run_actor(_noop())
    assert disposed == [1]


def test_run_actor_disposes_engine_even_when_the_coroutine_raises(monkeypatch):
    disposed = []
    monkeypatch.setattr(
        "worker.broker.dispose_engine",
        lambda: _record(disposed),
    )
    with pytest.raises(ValueError, match="boom"):
        run_actor(_boom())
    assert disposed == [1]


async def _record(sink: list[int]) -> None:
    sink.append(1)
