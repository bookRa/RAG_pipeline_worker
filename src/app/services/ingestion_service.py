from __future__ import annotations

from datetime import datetime
import hashlib
import time

from ..application.interfaces import ObservabilityRecorder
from ..domain.models import Document
from ..observability.logger import NullObservabilityRecorder
from ..persistence.ports import IngestionRepository


class IngestionService:
    """Handles receipt of a document and records ingestion metadata."""

    def __init__(
        self,
        latency: float = 0.0,
        repository: IngestionRepository | None = None,
        observability: ObservabilityRecorder | None = None,
    ) -> None:
        self.latency = latency
        self.repository = repository
        self.observability = observability or NullObservabilityRecorder()

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def ingest(self, document: Document, file_bytes: bytes | None = None) -> Document:
        self._simulate_latency()
        if self.repository and file_bytes:
            stored_path = self.repository.store(
                document_id=document.id,
                filename=document.filename,
                data=file_bytes,
            )
            document.metadata["raw_file_path"] = stored_path
            document.metadata["raw_file_checksum"] = hashlib.sha256(file_bytes).hexdigest()
        document.metadata.pop("raw_file_inline", None)
        document.status = "ingested"
        document.metadata["ingested_at"] = datetime.utcnow().isoformat()
        self.observability.record_event(
            stage="ingestion",
            details={
                "document_id": document.id,
                "filename": document.filename,
                "file_type": document.file_type,
                "size_bytes": document.size_bytes,
            },
        )
        return document
