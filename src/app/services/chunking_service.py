import time
from uuid import uuid4

from ..domain.models import Chunk, Document, Metadata
from ..observability.logger import log_event


class ChunkingService:
    """Splits document pages into smaller, retrievable chunks."""

    def __init__(self, latency: float = 0.0) -> None:
        self.latency = latency

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def chunk(self, document: Document, size: int = 200, overlap: int = 50) -> Document:
        self._simulate_latency()
        normalized_overlap = min(overlap, size - 1) if size > 1 else 0

        for page in document.pages:
            if page.chunks:
                continue

            text = page.text or ""
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
                    start_offset=start,
                    end_offset=end,
                    metadata=metadata,
                )
                document.add_chunk(page.page_number, chunk)

                if end == len(text):
                    break

                start = max(end - normalized_overlap, 0)
                chunk_index += 1

        document.status = "chunked"
        log_event(
            stage="chunking",
            details={
                "document_id": document.id,
                "page_count": len(document.pages),
                "chunk_count": sum(len(page.chunks) for page in document.pages),
            },
        )
        return document
