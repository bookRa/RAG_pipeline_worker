from __future__ import annotations

from datetime import datetime
import hashlib
import time

from ..application.interfaces import ObservabilityRecorder
from ..domain.models import Document
from ..persistence.ports import IngestionRepository


class IngestionService:
    """Handles receipt of a document and records ingestion metadata."""

    def __init__(
        self,
        latency: float = 0.0,
        repository: IngestionRepository | None = None,
        observability: ObservabilityRecorder,
    ) -> None:
        self.latency = latency
        self.repository = repository
        self.observability = observability

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def ingest(self, document: Document, file_bytes: bytes | None = None) -> Document:
        self._simulate_latency()
        updated_metadata = document.metadata.copy()
        
        if self.repository and file_bytes:
            stored_path = self.repository.store(
                document_id=document.id,
                filename=document.filename,
                data=file_bytes,
            )
            updated_metadata["raw_file_path"] = stored_path
            updated_metadata["raw_file_checksum"] = hashlib.sha256(file_bytes).hexdigest()
        
        updated_metadata.pop("raw_file_inline", None)
        updated_metadata["ingested_at"] = datetime.utcnow().isoformat()
        
        updated_document = document.model_copy(
            update={
                "status": "ingested",
                "metadata": updated_metadata,
            }
        )
        
        self.observability.record_event(
            stage="ingestion",
            details={
                "document_id": updated_document.id,
                "filename": updated_document.filename,
                "file_type": updated_document.file_type,
                "size_bytes": updated_document.size_bytes,
            },
        )
        return updated_document
