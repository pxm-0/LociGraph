"""Shared tuning for dramatiq's on_retry_exhausted self-healing hooks.

Once a job's own dramatiq-level retries are exhausted, its healer starts a
fresh job for the same source rather than leaving it permanently failed.
Capped so a genuinely broken source (bad API key, corrupted data) still
surfaces as failed eventually instead of retrying forever.
"""

MAX_HEAL_GENERATIONS = 5
HEAL_DELAY_MS = 30_000
