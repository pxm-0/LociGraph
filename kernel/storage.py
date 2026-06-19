from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID


def save_raw(root: Path, user_id: str | UUID, source_id: str | UUID,
             filename: str, data: bytes) -> str:
    safe = os.path.basename(filename) or "upload"
    target_dir = Path(root) / str(user_id) / str(source_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe
    target.write_bytes(data)
    return str(target)
