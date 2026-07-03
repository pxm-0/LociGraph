"""Shared tuning for dramatiq's on_retry_exhausted self-healing hooks.

Once a job's own dramatiq-level retries are exhausted, its healer starts a
fresh job for the same source rather than leaving it permanently failed.
Capped so a genuinely broken source (bad API key, corrupted data) still
surfaces as failed eventually instead of retrying forever.
"""

# A large source can take many hours of real wall-clock processing time
# (thousands of sequential batches, one OpenAI call each), so a modest
# generation cap could exhaust itself on legitimate long-running work, not
# just genuinely broken sources. Generous enough to comfortably outlast any
# realistic source size; a truly broken source (bad API key, corrupted
# data) fails fast each attempt and still burns through this quickly.
MAX_HEAL_GENERATIONS = 50
HEAL_DELAY_MS = 30_000
