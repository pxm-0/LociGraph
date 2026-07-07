from __future__ import annotations

import re


def public_error(message: str) -> str:
    redacted = re.sub(r"sk-[A-Za-z0-9_*\\-]+", "sk-REDACTED", message)
    if "Incorrect API key provided" in redacted:
        return "OpenAI rejected the configured API key"
    return redacted
