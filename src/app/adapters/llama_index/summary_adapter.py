from __future__ import annotations

import logging
from typing import Sequence

from ...application.interfaces import SummaryGenerator
from ...prompts.loader import load_prompt
from ...config import PromptSettings
from .utils import extract_response_text

logger = logging.getLogger(__name__)


class LlamaIndexSummaryAdapter(SummaryGenerator):
    """LLM-backed summary generator using the shared LlamaIndex client."""

    def __init__(self, llm: object, prompt_settings: PromptSettings) -> None:
        self._llm = llm
        # Load all prompt templates
        self._generic_prompt = load_prompt(prompt_settings.summary_prompt_path)
        self._document_summary_prompt = load_prompt("docs/prompts/summarization/document_summary.md")
        self._chunk_summary_prompt = load_prompt("docs/prompts/summarization/chunk_summary.md")

    def summarize(self, text: str) -> str:
        """Generic summarization (backwards compatibility)."""
        if not text.strip():
            return ""
        try:
            completion = self._llm.complete(f"{self._generic_prompt}\n\n{text.strip()}")
            completion_text = extract_response_text(completion)
            return completion_text.strip()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("LLM summary failed, falling back to truncate: %s", exc)
            return text[:280].strip()
    
    def summarize_document(
        self,
        filename: str,
        file_type: str,
        page_count: int,
        page_summaries: Sequence[tuple[int, str]],
    ) -> str:
        """Generate document-level summary from page summaries using prompt template."""
        if not page_summaries:
            return ""
        
        # Format page summaries
        formatted_summaries = "\n\n".join(
            f"**Page {page_num}**: {summary}" 
            for page_num, summary in page_summaries
        )
        
        # Build complete prompt
        user_content = f"""Document: {filename}
File Type: {file_type}
Total Pages: {page_count}

Page Summaries:
{formatted_summaries}
"""
        
        try:
            completion = self._llm.complete(f"{self._document_summary_prompt}\n\n{user_content}")
            completion_text = extract_response_text(completion)
            summary = completion_text.strip()
            
            logger.debug(
                "Generated document summary for %s (%d pages): %s",
                filename,
                page_count,
                summary[:100],
            )
            
            return summary
        except Exception as exc:
            logger.warning("Document summary generation failed: %s", exc)
            # Fallback: concatenate page summaries
            return " ".join(s for _, s in page_summaries)[:500]
    
    def summarize_chunk(
        self,
        chunk_text: str,
        document_title: str,
        document_summary: str,
        page_summary: str | None,
        component_type: str | None,
    ) -> str:
        """Generate chunk summary with hierarchical context using prompt template."""
        if not chunk_text.strip():
            return ""
        
        # Build context section
        user_content = f"""Context:
- Document title: {document_title}
- Document summary: {document_summary}
- Page summary: {page_summary or 'N/A'}
- Component type: {component_type or 'text'}

Chunk Text:
{chunk_text}
"""
        
        try:
            completion = self._llm.complete(f"{self._chunk_summary_prompt}\n\n{user_content}")
            completion_text = extract_response_text(completion)
            summary = completion_text.strip()
            
            logger.debug(
                "Generated chunk summary (type=%s): %s",
                component_type or "text",
                summary[:80],
            )
            
            return summary
        except Exception as exc:
            logger.warning("Chunk summary generation failed: %s", exc)
            # Fallback: simple truncation
            return chunk_text[:120].strip()
