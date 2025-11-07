"""Placeholder adapter for LLM-based summarization or enrichment."""

from __future__ import annotations

from ..application.interfaces import SummaryGenerator


class LLMSummaryAdapter(SummaryGenerator):
    """Stub summary generator that truncates text."""

    def summarize(self, text: str) -> str:
        return text[:120].strip()
