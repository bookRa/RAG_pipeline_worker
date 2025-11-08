from __future__ import annotations

import time
from uuid import uuid4

from ..application.interfaces import ObservabilityRecorder
from ..domain.models import Chunk, Document, Metadata


class ChunkingService:
    """Splits document pages into smaller, retrievable chunks."""

    def __init__(self, observability: ObservabilityRecorder, latency: float = 0.0) -> None:
        self.observability = observability
        self.latency = latency

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

            # Always use raw text for Chunk.text (preserves immutable source for navigation)
            raw_text = page.text or ""
            if not raw_text:
                continue

            # Get cleaned text if available (may be None if cleaning hasn't run)
            cleaned_text = page.cleaned_text

            start = 0
            chunk_index = 0
            while start < len(raw_text):
                end = min(len(raw_text), start + size)
                chunk_id = str(uuid4())
                
                # Slice raw text for Chunk.text (always preserves source)
                chunk_raw_text = raw_text[start:end]
                
                # Slice cleaned text for Chunk.cleaned_text (parallel slice if available)
                # Note: Offsets reference raw text positions, cleaned slice may differ in length
                chunk_cleaned_text = cleaned_text[start:end] if cleaned_text else None
                
                # Attach cleaning metadata from document metadata if available
                # Cleaning service stores metadata keyed by page_number
                chunk_extra = {}
                cleaning_metadata_by_page = document.metadata.get("cleaning_metadata_by_page", {})
                if page.page_number in cleaning_metadata_by_page:
                    page_cleaning_meta = cleaning_metadata_by_page[page.page_number].copy()
                    # Add segment_id (chunk.id) to link metadata to this chunk
                    page_cleaning_meta["segment_id"] = chunk_id
                    chunk_extra["cleaning"] = page_cleaning_meta
                
                metadata = Metadata(
                    document_id=document.id,
                    page_number=page.page_number,
                    chunk_id=chunk_id,
                    start_offset=start,
                    end_offset=end,
                    title=f"{document.filename}-p{page.page_number}-c{chunk_index}",
                    extra=chunk_extra,
                )
                chunk = Chunk(
                    id=chunk_id,
                    document_id=document.id,
                    page_number=page.page_number,
                    text=chunk_raw_text,  # Always raw text slice
                    cleaned_text=chunk_cleaned_text,  # Cleaned slice if available
                    start_offset=start,  # Offsets reference raw text positions
                    end_offset=end,
                    metadata=metadata,
                )
                updated_document = updated_document.add_chunk(page.page_number, chunk)

                if end == len(raw_text):
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
