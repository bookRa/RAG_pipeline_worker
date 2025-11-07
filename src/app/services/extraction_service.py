from ..domain.models import Document, Page
from ..observability.logger import log_event


class ExtractionService:
    """Converts an ingested document into a structured set of pages."""

    def extract(self, document: Document) -> Document:
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
