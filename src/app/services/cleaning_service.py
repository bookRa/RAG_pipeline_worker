from __future__ import annotations

import hashlib
import time
from typing import Callable

from ..application.interfaces import ObservabilityRecorder
from ..domain.models import Document


class CleaningService:
    """Normalizes text and records cleaning metadata."""

    def __init__(
        self,
        observability: ObservabilityRecorder,
        profile: str = "default",
        normalizer: Callable[[str], str] | None = None,
        latency: float = 0.0,
    ) -> None:
        self.observability = observability
        self.profile = profile
        self.normalizer = normalizer or self._default_normalizer
        self.latency = latency

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
        
        # Store page-level cleaning metadata for chunking to attach to chunks
        # Keyed by page_number so chunking can look it up
        updated_metadata["cleaning_metadata_by_page"] = {}
        
        for page in document.pages:
            raw_text = page.text or ""
            cleaned_page_text = self.normalizer(raw_text)
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
            updated_metadata["cleaning_metadata_by_page"][page.page_number] = {
                "cleaned_tokens_count": cleaned_tokens_count,
                "diff_hash": diff_hash,
                "cleaning_ops": cleaning_ops,
                "needs_review": False,  # Can be enhanced with quality checks
                "profile": self.profile,
            }
            
            page_summaries.append(
                {
                    "page_number": page.page_number,
                    "cleaned_tokens": cleaned_tokens_count,
                    "characters": len(cleaned_page_text),
                    "diff_hash": diff_hash,
                }
            )

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
