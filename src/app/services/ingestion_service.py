from datetime import datetime
import time

from ..domain.models import Document
from ..observability.logger import log_event


class IngestionService:
    """Handles receipt of a document and records ingestion metadata."""

    def __init__(self, latency: float = 0.0) -> None:
        self.latency = latency

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def ingest(self, document: Document) -> Document:
        self._simulate_latency()
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
