from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from kernel.db.engine import dispose_engine

_broker: dramatiq.Broker | None = None

# dramatiq considers a worker "dead" (and its unacked messages eligible for
# reclaim) once this long has passed without a heartbeat. Heartbeats are
# only sent as a side effect of a worker issuing a Redis command, and a
# worker actively processing one long-running message (prefetch=1) issues
# none until it finishes — so this must comfortably exceed the longest
# actor's own time_limit (extract_claims: 3 hours), or a still-legitimately-
# running job looks dead and gets redelivered to a second worker mid-flight.
HEARTBEAT_TIMEOUT_MS = 4 * 60 * 60 * 1000


def get_broker() -> dramatiq.Broker:
    global _broker
    if _broker is None:
        _broker = RedisBroker(  # type: ignore[no-untyped-call]  # dramatiq ships no stubs
            url=os.environ.get("REDIS_URL", "redis://localhost:6379"),
            heartbeat_timeout=HEARTBEAT_TIMEOUT_MS,
        )
        dramatiq.set_broker(_broker)
    return _broker


def run_actor(coro: Coroutine[Any, Any, None]) -> None:
    """Run an actor's async body in a fresh event loop via asyncio.run(), then
    dispose the shared engine's connection pool.

    kernel.db.engine's AsyncEngine is a process-wide singleton, but this
    worker process handles many dramatiq messages over its lifetime, each
    via its own asyncio.run() call (a new event loop every time). asyncpg
    connections are bound to the loop that created them, so a pooled
    connection left open across actor invocations causes "attached to a
    different loop" errors the next time it's checked out. Disposing after
    every actor call forces the next one to open fresh connections instead.
    """
    try:
        asyncio.run(coro)
    finally:
        asyncio.run(dispose_engine())
