from __future__ import annotations

from typing import Any


def extract_response_text(response: Any) -> str:
    """Normalize LlamaIndex response objects into raw text."""

    if isinstance(response, str):
        return response
    if hasattr(response, "text"):
        return getattr(response, "text")
    if hasattr(response, "output_text"):
        return getattr(response, "output_text")
    if hasattr(response, "message") and hasattr(response.message, "content"):
        return response.message.content or ""
    if hasattr(response, "messages"):
        messages = getattr(response, "messages")
        if messages:
            last = messages[-1]
            if hasattr(last, "content"):
                return last.content or ""
    # Fallback to string representation
    return str(response)
