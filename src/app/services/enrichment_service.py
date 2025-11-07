from __future__ import annotations

import time

from ..application.interfaces import SummaryGenerator, ObservabilityRecorder
from ..domain.models import Document


class EnrichmentService:
    """Adds lightweight metadata such as titles and summaries to chunks."""

    def __init__(
        self,
        latency: float = 0.0,
        summary_generator: SummaryGenerator | None = None,
        observability: ObservabilityRecorder,
    ) -> None:
        self.latency = latency
        self.summary_generator = summary_generator
        self.observability = observability

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def enrich(self, document: Document) -> Document:
        self._simulate_latency()
        summaries: list[str] = []
        updated_pages = []
        
        for page in document.pages:
            updated_chunks = []
            for chunk in page.chunks:
                if chunk.metadata is None:
                    updated_chunks.append(chunk)
                    continue

                updated_metadata = chunk.metadata.model_copy()
                if not updated_metadata.title:
                    updated_metadata = updated_metadata.model_copy(update={"title": f"{document.filename}#p{page.page_number}"})
                if not updated_metadata.summary:
                    summary = self._summarize_chunk(chunk.cleaned_text or chunk.text or "")
                    updated_metadata = updated_metadata.model_copy(update={"summary": summary})
                    summaries.append(updated_metadata.summary)
                else:
                    summaries.append(updated_metadata.summary)
                
                updated_chunk = chunk.model_copy(update={"metadata": updated_metadata})
                updated_chunks.append(updated_chunk)

            updated_page = page.model_copy(update={"chunks": updated_chunks})
            updated_pages.append(updated_page)

        document_summary = document.summary
        if summaries and not document_summary:
            document_summary = " ".join(summaries)[:280]

        updated_document = document.model_copy(
            update={
                "pages": updated_pages,
                "summary": document_summary,
                "status": "enriched",
            }
        )
        
        self.observability.record_event(
            stage="enrichment",
            details={
                "document_id": updated_document.id,
                "chunk_count": sum(len(page.chunks) for page in updated_document.pages),
            },
        )
        return updated_document

    def _summarize_chunk(self, text: str) -> str:
        if not text:
            return ""
        if self.summary_generator:
            return self.summary_generator.summarize(text)
        return text[:120].strip()
