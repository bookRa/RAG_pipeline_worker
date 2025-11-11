from __future__ import annotations

import hashlib
import time
from typing import Callable

from ..application.interfaces import CleaningLLM, ObservabilityRecorder
from ..parsing.schemas import CleanedPage, ParsedPage
from ..domain.models import Document


class CleaningService:
    """Normalizes text and records cleaning metadata."""

    def __init__(
        self,
        observability: ObservabilityRecorder,
        profile: str = "default",
        normalizer: Callable[[str], str] | None = None,
        latency: float = 0.0,
        structured_cleaner: CleaningLLM | None = None,
    ) -> None:
        self.observability = observability
        self.profile = profile
        self.normalizer = normalizer or self._default_normalizer
        self.latency = latency
        self.structured_cleaner = structured_cleaner

    @staticmethod
    def _default_normalizer(text: str) -> str:
        return " ".join(text.split())

    def clean(self, document: Document) -> Document:
        """
        Clean document pages and generate segment-level metadata.
        
        This method normalizes page text and stores cleaning metadata that will be
        attached to chunks during the chunking stage. Since cleaning runs before
        chunking, we store page-level segment metadata that chunking can map to chunks.
        """
        if self.latency > 0:
            time.sleep(self.latency)
        page_summaries: list[dict[str, int]] = []
        updated_pages = []
        updated_metadata = document.metadata.copy()

        updated_metadata["cleaning_metadata_by_page"] = {}
        llm_segments: dict[str, CleanedPage] = {}

        parsed_pages_meta = updated_metadata.get("parsed_pages", {})
        
        for page in document.pages:
            raw_text = page.text or ""
            cleaned_page_text = self.normalizer(raw_text)
            cleaned_segments: CleanedPage | None = None

            if self.structured_cleaner:
                parsed_payload = parsed_pages_meta.get(str(page.page_number)) or parsed_pages_meta.get(page.page_number)
                if parsed_payload:
                    parsed_page = ParsedPage.model_validate(parsed_payload)
                    cleaned_segments = self._run_structured_cleaner(parsed_page)
                    cleaned_page_text = "\n\n".join(segment.text for segment in cleaned_segments.segments).strip() or cleaned_page_text
                    llm_segments[str(page.page_number)] = cleaned_segments
            updated_page = page.model_copy(update={"cleaned_text": cleaned_page_text})
            updated_pages.append(updated_page)
            
            # Generate segment-level cleaning metadata for this page
            # This will be attached to chunks during chunking stage
            cleaned_tokens_count = len(cleaned_page_text.split())
            diff_hash_input = f"{raw_text}::{cleaned_page_text}"
            diff_hash = hashlib.sha256(diff_hash_input.encode("utf-8")).hexdigest()
            
            # Determine cleaning operations applied (simplified for now)
            cleaning_ops = []
            if raw_text != cleaned_page_text:
                # Detect whitespace normalization
                if " ".join(raw_text.split()) == cleaned_page_text:
                    cleaning_ops.append("whitespace")
                # Future: detect other operations (case normalization, etc.)
            
            # Store cleaning metadata keyed by page number for chunking to retrieve
            page_meta = {
                "cleaned_tokens_count": cleaned_tokens_count,
                "diff_hash": diff_hash,
                "cleaning_ops": cleaning_ops,
                "needs_review": False,  # Can be enhanced with quality checks
                "profile": self.profile,
            }
            if cleaned_segments:
                page_meta["llm_segments"] = cleaned_segments.model_dump()
            updated_metadata["cleaning_metadata_by_page"][page.page_number] = page_meta
            
            page_summaries.append(
                {
                    "page_number": page.page_number,
                    "cleaned_tokens": cleaned_tokens_count,
                    "characters": len(cleaned_page_text),
                    "diff_hash": diff_hash,
                }
            )

        if llm_segments:
            updated_metadata["cleaned_pages_llm"] = {k: v.model_dump() for k, v in llm_segments.items()}
        updated_metadata["cleaning_profile"] = self.profile
        updated_metadata["cleaning_report"] = page_summaries
        
        updated_document = document.model_copy(
            update={
                "pages": updated_pages,
                "status": "cleaned",
                "metadata": updated_metadata,
            }
        )
        
        self.observability.record_event(
            stage="cleaning",
            details={
                "document_id": updated_document.id,
                "profile": self.profile,
                "pages_cleaned": len(page_summaries),
            },
        )
        return updated_document

    def _run_structured_cleaner(self, parsed_page: ParsedPage) -> CleanedPage:
        assert self.structured_cleaner  # for mypy
        return self.structured_cleaner.clean_page(parsed_page)
