import threading

import pytest

from kernel.db.engine import dispose_engine, get_engine


@pytest.mark.asyncio
async def test_get_engine_returns_same_instance_within_a_thread():
    assert get_engine() is get_engine()


def test_get_engine_returns_different_instances_across_threads():
    engines: list[object] = []
    threads = [threading.Thread(target=lambda: engines.append(get_engine())) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert engines[0] is not engines[1]


@pytest.mark.asyncio
async def test_dispose_engine_only_clears_calling_threads_engine():
    other_engine: list[object] = []
    t = threading.Thread(target=lambda: other_engine.append(get_engine()))
    t.start()
    t.join()

    this_engine = get_engine()
    await dispose_engine()

    assert get_engine() is not this_engine
