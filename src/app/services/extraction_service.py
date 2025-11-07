import time

from ..domain.models import Document, Page
from ..observability.logger import log_event


class ExtractionService:
    """Converts an ingested document into a structured set of pages."""

    def __init__(self, latency: float = 0.0) -> None:
        self.latency = latency

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def extract(self, document: Document) -> Document:
        self._simulate_latency()
        if document.pages:
            return document

        placeholder_text = (
            f"Extracted placeholder text for {document.filename}. "
            f"Approximate size: {document.size_bytes} bytes."
        )
        page = Page(document_id=document.id, page_number=1, text=placeholder_text)
        document.add_page(page)
        document.status = "extracted"

        log_event(
            stage="extraction",
            details={
                "document_id": document.id,
                "page_count": len(document.pages),
            },
        )
        return document
