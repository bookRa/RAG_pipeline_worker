from __future__ import annotations

import time
from uuid import uuid4

from ..application.interfaces import ObservabilityRecorder
from ..domain.models import Chunk, Document, Metadata


class ChunkingService:
    """Splits document pages into smaller, retrievable chunks."""

    def __init__(self, latency: float = 0.0, observability: ObservabilityRecorder) -> None:
        self.latency = latency
        self.observability = observability

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def chunk(self, document: Document, size: int = 200, overlap: int = 50) -> Document:
        self._simulate_latency()
        normalized_overlap = min(overlap, size - 1) if size > 1 else 0
        updated_document = document

        for page in document.pages:
            if page.chunks:
                continue

            text = page.cleaned_text or page.text or ""
            if not text:
                continue

            start = 0
            chunk_index = 0
            while start < len(text):
                end = min(len(text), start + size)
                chunk_id = str(uuid4())
                chunk_text = text[start:end]
                metadata = Metadata(
                    document_id=document.id,
                    page_number=page.page_number,
                    chunk_id=chunk_id,
                    start_offset=start,
                    end_offset=end,
                    title=f"{document.filename}-p{page.page_number}-c{chunk_index}",
                )
                chunk = Chunk(
                    id=chunk_id,
                    document_id=document.id,
                    page_number=page.page_number,
                    text=chunk_text,
                    cleaned_text=chunk_text,
                    start_offset=start,
                    end_offset=end,
                    metadata=metadata,
                )
                updated_document = updated_document.add_chunk(page.page_number, chunk)

                if end == len(text):
                    break

                start = max(end - normalized_overlap, 0)
                chunk_index += 1

        updated_document = updated_document.model_copy(update={"status": "chunked"})
        self.observability.record_event(
            stage="chunking",
            details={
                "document_id": updated_document.id,
                "page_count": len(updated_document.pages),
                "chunk_count": sum(len(page.chunks) for page in updated_document.pages),
            },
        )
        return updated_document
