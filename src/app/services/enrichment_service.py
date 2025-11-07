from __future__ import annotations

import time

from ..application.interfaces import SummaryGenerator, ObservabilityRecorder
from ..domain.models import Document
from ..observability.logger import NullObservabilityRecorder


class EnrichmentService:
    """Adds lightweight metadata such as titles and summaries to chunks."""

    def __init__(
        self,
        latency: float = 0.0,
        summary_generator: SummaryGenerator | None = None,
        observability: ObservabilityRecorder | None = None,
    ) -> None:
        self.latency = latency
        self.summary_generator = summary_generator
        self.observability = observability or NullObservabilityRecorder()

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def enrich(self, document: Document) -> Document:
        self._simulate_latency()
        summaries: list[str] = []
        for page in document.pages:
            for chunk in page.chunks:
                if chunk.metadata is None:
                    continue

                if not chunk.metadata.title:
                    chunk.metadata.title = f"{document.filename}#p{page.page_number}"
                if not chunk.metadata.summary:
                    chunk.metadata.summary = self._summarize_chunk(chunk.cleaned_text or chunk.text or "")
                summaries.append(chunk.metadata.summary)

        if summaries and not document.summary:
            document.summary = " ".join(summaries)[:280]

        document.status = "enriched"
        self.observability.record_event(
            stage="enrichment",
            details={
                "document_id": document.id,
                "chunk_count": sum(len(page.chunks) for page in document.pages),
            },
        )
        return document

    def _summarize_chunk(self, text: str) -> str:
        if not text:
            return ""
        if self.summary_generator:
            return self.summary_generator.summarize(text)
        return text[:120].strip()
