from __future__ import annotations

import time
from typing import Callable

from ..domain.models import Document
from ..observability.logger import log_event


class CleaningService:
    """Normalizes text and records cleaning metadata."""

    def __init__(self, profile: str = "default", normalizer: Callable[[str], str] | None = None, latency: float = 0.0) -> None:
        self.profile = profile
        self.normalizer = normalizer or self._default_normalizer
        self.latency = latency

    @staticmethod
    def _default_normalizer(text: str) -> str:
        return " ".join(text.split())

    def clean(self, document: Document) -> Document:
        if self.latency > 0:
            time.sleep(self.latency)
        page_summaries: list[dict[str, int]] = []
        for page in document.pages:
            cleaned_page_text = self.normalizer(page.text or "")
            page.text = cleaned_page_text
            token_count = len(cleaned_page_text.split())
            page_summaries.append(
                {
                    "page_number": page.page_number,
                    "cleaned_tokens": token_count,
                    "characters": len(cleaned_page_text),
                }
            )

            for chunk in page.chunks:
                cleaned_chunk_text = self.normalizer(chunk.text)
                if chunk.metadata:
                    chunk.metadata.extra["cleaned_text"] = cleaned_chunk_text
                    chunk.metadata.extra["cleaned_tokens"] = len(cleaned_chunk_text.split())
                    chunk.metadata.extra["cleaning_profile"] = self.profile
                chunk.text = cleaned_chunk_text

        document.metadata["cleaning_profile"] = self.profile
        document.status = "cleaned"
        log_event(
            stage="cleaning",
            details={
                "document_id": document.id,
                "profile": self.profile,
                "pages_cleaned": len(page_summaries),
            },
        )
        document.metadata["cleaning_report"] = page_summaries
        return document
