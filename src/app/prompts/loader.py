from __future__ import annotations

from functools import lru_cache
from pathlib import Path


class PromptNotFoundError(FileNotFoundError):
    """Raised when a prompt file is missing."""


@lru_cache(maxsize=32)
def load_prompt(path: Path | str) -> str:
    """Load a prompt file from disk with lightweight caching."""

    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise PromptNotFoundError(f"Prompt file not found: {resolved}")
    return resolved.read_text(encoding="utf-8").strip()
