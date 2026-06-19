from __future__ import annotations

import os

import dramatiq
from dramatiq.brokers.redis import RedisBroker

_broker: dramatiq.Broker | None = None


def get_broker() -> dramatiq.Broker:
    global _broker
    if _broker is None:
        _broker = RedisBroker(url=os.environ.get("REDIS_URL", "redis://localhost:6379"))
        dramatiq.set_broker(_broker)
    return _broker
