from ..domain.models import Document
from ..observability.logger import log_event


class EnrichmentService:
    """Adds lightweight metadata such as titles and summaries to chunks."""

    def enrich(self, document: Document) -> Document:
        summaries: list[str] = []
        for page in document.pages:
            for chunk in page.chunks:
                if chunk.metadata is None:
                    continue

                if not chunk.metadata.title:
                    chunk.metadata.title = f"{document.filename}#p{page.page_number}"
                if not chunk.metadata.summary:
                    chunk.metadata.summary = chunk.text[:120].strip()
                summaries.append(chunk.metadata.summary)

        if summaries and not document.summary:
            document.summary = " ".join(summaries)[:280]

        document.status = "enriched"
        log_event(
            stage="enrichment",
            details={
                "document_id": document.id,
                "chunk_count": sum(len(page.chunks) for page in document.pages),
            },
        )
        return document
