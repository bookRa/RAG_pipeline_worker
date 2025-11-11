from __future__ import annotations

from typing import Any


def strip_code_fences(text: str) -> str:
    """Remove leading/trailing Markdown code fences (```json ... ```)."""

    stripped = text.strip()
    if stripped.startswith("```"):
        parts = stripped.split("```", 2)
        if len(parts) >= 3:
            # parts[1] might be a language hint (e.g., 'json')
            content = parts[2 if parts[1].strip() else 1]
            return content.strip()
    if stripped.startswith("`") and stripped.endswith("`"):
        return stripped.strip("`").strip()
    return stripped


def extract_response_text(response: Any) -> str:
    """Normalize LlamaIndex response objects into raw text."""

    if isinstance(response, str):
        return strip_code_fences(response)
    if hasattr(response, "text"):
        return strip_code_fences(getattr(response, "text"))
    if hasattr(response, "output_text"):
        return strip_code_fences(getattr(response, "output_text"))
    if hasattr(response, "message") and hasattr(response.message, "content"):
        content = getattr(response.message, "content") or ""
        return strip_code_fences(content)
    if hasattr(response, "messages"):
        messages = getattr(response, "messages")
        if messages:
            last = messages[-1]
            if hasattr(last, "content"):
                return strip_code_fences(last.content or "")
    # Fallback to string representation
    return strip_code_fences(str(response))
