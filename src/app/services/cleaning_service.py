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
        profile: str = "default",
        normalizer: Callable[[str], str] | None = None,
        latency: float = 0.0,
        observability: ObservabilityRecorder,
    ) -> None:
        self.profile = profile
        self.normalizer = normalizer or self._default_normalizer
        self.latency = latency
        self.observability = observability

    @staticmethod
    def _default_normalizer(text: str) -> str:
        return " ".join(text.split())

    def clean(self, document: Document) -> Document:
        if self.latency > 0:
            time.sleep(self.latency)
        page_summaries: list[dict[str, int]] = []
        updated_pages = []
        
        for page in document.pages:
            cleaned_page_text = self.normalizer(page.text or "")
            updated_page = page.model_copy(update={"cleaned_text": cleaned_page_text})
            updated_pages.append(updated_page)
            
            token_count = len(cleaned_page_text.split())
            diff_hash_input = f"{page.text or ''}::{cleaned_page_text}"
            diff_hash = hashlib.sha256(diff_hash_input.encode("utf-8")).hexdigest()
            page_summaries.append(
                {
                    "page_number": page.page_number,
                    "cleaned_tokens": token_count,
                    "characters": len(cleaned_page_text),
                    "diff_hash": diff_hash,
                }
            )

        updated_metadata = document.metadata.copy()
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
