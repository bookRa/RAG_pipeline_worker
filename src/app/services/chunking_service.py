from __future__ import annotations

import time
from uuid import uuid4

from typing import Any

from ..application.interfaces import ObservabilityRecorder
from ..domain.models import Chunk, Document, Metadata


class ChunkingService:
    """Splits document pages into smaller, retrievable chunks."""

    def __init__(
        self,
        observability: ObservabilityRecorder,
        latency: float = 0.0,
        chunk_size: int = 200,
        chunk_overlap: int = 50,
        text_splitter: Any | None = None,
    ) -> None:
        self.observability = observability
        self.latency = latency
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = text_splitter

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def chunk(self, document: Document, size: int | None = None, overlap: int | None = None) -> Document:
        self._simulate_latency()
        size = size or self.chunk_size
        overlap = overlap if overlap is not None else self.chunk_overlap
        normalized_overlap = min(overlap, size - 1) if size > 1 else 0
        updated_document = document
        parsed_pages_meta = document.metadata.get("parsed_pages", {})

        for page in document.pages:
            if page.chunks:
                continue

            raw_text = page.text or ""
            if not raw_text:
                continue

            cleaned_text = page.cleaned_text
            parsed_page = parsed_pages_meta.get(str(page.page_number)) or parsed_pages_meta.get(str(page.page_number))

            segments = self._split_text(raw_text, size, normalized_overlap)
            cursor = 0
            chunk_index = 0

            for segment in segments:
                start = self._find_segment_start(raw_text, segment, cursor)
                end = start + len(segment)
                cursor = end

                chunk_id = str(uuid4())
                chunk_raw_text = raw_text[start:end]
                chunk_cleaned_text = cleaned_text[start:end] if cleaned_text else None
                if chunk_cleaned_text is not None:
                    chunk_cleaned_text = chunk_cleaned_text.rstrip()

                # Attach cleaning metadata from document metadata if available
                # Cleaning service stores metadata keyed by page_number
                chunk_extra = {}
                cleaning_metadata_by_page = document.metadata.get("cleaning_metadata_by_page", {})
                if page.page_number in cleaning_metadata_by_page:
                    page_cleaning_meta = cleaning_metadata_by_page[page.page_number].copy()
                    # Add segment_id (chunk.id) to link metadata to this chunk
                    page_cleaning_meta["segment_id"] = chunk_id
                    chunk_extra["cleaning"] = page_cleaning_meta

                parsed_matches = self._match_parsed_segments(chunk_raw_text, parsed_page)
                if parsed_matches:
                    chunk_extra["parsed_segments"] = parsed_matches

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

                chunk_index += 1
                if not self.text_splitter and end < len(raw_text):
                    next_cursor = max(end - normalized_overlap, 0)
                    if next_cursor <= start:
                        next_cursor = start + 1
                    cursor = next_cursor

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

    @staticmethod
    def _match_parsed_segments(chunk_text: str, parsed_page: dict | None) -> list[dict[str, str]]:
        if not parsed_page:
            return []
        matches: list[dict[str, str]] = []
        paragraphs = parsed_page.get("paragraphs", [])
        for paragraph in paragraphs:
            text = (paragraph.get("text") or "").strip()
            if text and text in chunk_text:
                matches.append({"id": paragraph.get("id", ""), "order": str(paragraph.get("order", ""))})
        return matches

    def _split_text(self, text: str, size: int, overlap: int) -> list[str]:
        if self.text_splitter:
            try:
                return [segment for segment in self.text_splitter.split_text(text) if segment.strip()]
            except AttributeError:
                # Fallback to manual logic if the injected splitter does not support split_text
                pass

        segments: list[str] = []
        cursor = 0
        while cursor < len(text):
            end = min(len(text), cursor + size)
            segments.append(text[cursor:end])
            if end == len(text):
                break
            next_cursor = max(end - overlap, 0)
            if next_cursor <= cursor:
                next_cursor = cursor + 1
            cursor = next_cursor
        return segments

    @staticmethod
    def _find_segment_start(text: str, segment: str, cursor: int) -> int:
        idx = text.find(segment, cursor)
        if idx == -1:
            return cursor
        return idx
