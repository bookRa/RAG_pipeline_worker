from __future__ import annotations

import logging

from ...application.interfaces import SummaryGenerator
from ...prompts.loader import load_prompt
from ...config import PromptSettings
from .utils import extract_response_text

logger = logging.getLogger(__name__)


class LlamaIndexSummaryAdapter(SummaryGenerator):
    """LLM-backed summary generator using the shared LlamaIndex client."""

    def __init__(self, llm: object, prompt_settings: PromptSettings) -> None:
        self._llm = llm
        self._prompt = load_prompt(prompt_settings.summary_prompt_path)

    def summarize(self, text: str) -> str:
        if not text.strip():
            return ""
        try:
            completion = self._llm.complete(f"{self._prompt}\n\n{text.strip()}")
            completion_text = extract_response_text(completion)
            return completion_text.strip()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("LLM summary failed, falling back to truncate: %s", exc)
            return text[:280].strip()
