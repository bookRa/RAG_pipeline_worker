from datetime import datetime

from ..domain.models import Document
from ..observability.logger import log_event


class IngestionService:
    """Handles receipt of a document and records ingestion metadata."""

    def ingest(self, document: Document) -> Document:
        document.status = "ingested"
        document.metadata["ingested_at"] = datetime.utcnow().isoformat()
        log_event(
            stage="ingestion",
            details={
                "document_id": document.id,
                "filename": document.filename,
                "file_type": document.file_type,
                "size_bytes": document.size_bytes,
            },
        )
        return document
