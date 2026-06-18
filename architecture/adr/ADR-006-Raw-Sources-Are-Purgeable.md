# ADR-006: Raw Sources Are Purgeable

## Decision

Raw sources may be purged after ingestion, verification, and retention.

## Reason

The server has limited storage.

Purging also improves security by reducing exposure of original sensitive files.

## Consequence

The system preserves:
- source metadata
- checksum
- import time
- observation count
- purge status

But the raw file itself can be deleted.
